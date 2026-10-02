"""Paper session for `multi_crypto_momentum` (PAPER ONLY; there is no live order path in this project).

    PAPER_MODE=true python3 -m paper_trading.mcm_runner --duration 604800      # ~7 days

Market data: Coinbase Advanced PUBLIC read-only REST (daily candles), through the same allowlisted transport as the
rest of the project (GET only; order endpoints are refused before any network I/O). No credentials are used.

Products: each coin is looked up as the Coinbase SPOT product `<COIN>-USD`. These spot prices are a PROXY for
perpetual trading (shorts are simulated paper shorts with 1x collateral). If a product is missing, offline or
trading-disabled, that coin is DISABLED and reported -- no other product is substituted.

Timing (same engine as the backtest): at each UTC day boundary, once the new daily candle exists, the just
COMPLETED candle's signals are evaluated and orders are filled (on paper) at the NEW candle's open. Decisions
are never taken at startup: the current candle already opened before the session started, so the first
decision is at the first 00:00 UTC boundary after startup.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal as _signal
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from config.settings import REPO_ROOT, PaperModeError, require_paper_mode
from exchange.client import MAX_CANDLES_PER_REQUEST, CoinbaseAdvancedClient
from exchange.errors import ExchangeAPIError, ForbiddenEndpointError
from exchange.transport import ReadOnlyTransport
from market_data.websocket_feed import SessionClock
from strategy.multi_crypto_momentum import UNIVERSE, MCMEngine, MCMParams, build_states, params_dict

log = logging.getLogger("mcm_paper")
MARKET_LABEL = ("Coinbase Advanced SPOT products (<COIN>-USD) used as a PRICE PROXY for perpetual trading; "
                "shorts are simulated paper shorts with 1x cash collateral; no funding modelled")
WARMUP_DAYS = 1000        # EMA200 needs a long history to converge (3 requests of <= 350 daily candles)
DAY = timedelta(days=1)
DECISION_GRACE = timedelta(minutes=30)   # after 00:00 UTC, wait up to this long for every coin's new candle
HEARTBEAT = timedelta(minutes=5)         # visible status line at most this often (one per poll at the default 300 s)


def utc_day(t: datetime) -> pd.Timestamp:
    return pd.Timestamp(t).tz_convert("UTC").floor("1D") if pd.Timestamp(t).tzinfo else pd.Timestamp(t, tz="UTC").floor("1D")


def candles_frame(candles) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], dtype=float)
    df = pd.DataFrame([{"time": pd.Timestamp(c.start).tz_convert("UTC"), "open": float(c.open), "high": float(c.high),
                        "low": float(c.low), "close": float(c.close), "volume": float(c.volume)} for c in candles])
    return df.drop_duplicates("time", keep="last").set_index("time").sort_index()


def split_completed(df: pd.DataFrame, now: datetime) -> tuple[pd.DataFrame, Optional[pd.Series]]:
    """(completed daily candles, the in-progress candle or None). A daily candle starting at S is complete only
    once now >= S + 1 day; anything later than today (clock skew) is dropped."""
    today = utc_day(now)
    completed = df[df.index + DAY <= pd.Timestamp(now)]
    current = df.loc[today] if today in df.index else None
    return completed[completed.index < today], current


class MCMPaperSession:
    def __init__(self, client, params: MCMParams = MCMParams(), start_equity: float = 200.0,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 sleep: Callable[[float], None] = time.sleep, universe=UNIVERSE, out_dir: Optional[Path] = None,
                 request_pause_s: float = 0.15):
        self.client, self.p, self.start_equity, self.now, self.sleep = client, params, start_equity, now, sleep
        self.universe = tuple(universe)
        self.pause = request_pause_s
        self.available: dict[str, str] = {}
        self.unavailable: dict[str, str] = {}
        self.frames: dict[str, pd.DataFrame] = {}
        self.engine: Optional[MCMEngine] = None
        self.last_decision_day: Optional[pd.Timestamp] = None
        self.md_messages = 0            # successful market-data REST responses
        self.candles_received = 0
        self.connection_errors: list[str] = []
        self.last_refresh_ok: Optional[datetime] = None      # last poll where EVERY available coin refreshed
        self.last_heartbeat: Optional[datetime] = None
        self.status = "starting"
        self.equity_marks: list[tuple[str, float]] = []
        self.startup_signals: list[dict] = []
        self.started_at: Optional[datetime] = None
        self.out_dir = out_dir

    # -- safety ---------------------------------------------------------------------------------------
    @property
    def transport(self) -> ReadOnlyTransport:
        return self.client._transport

    def order_endpoint_called(self) -> bool:
        return bool(self.transport.order_endpoint_called)

    # -- market data ------------------------------------------------------------------------------------
    def _candles(self, coin: str, start: datetime, end: datetime) -> pd.DataFrame:
        pid = self.available[coin]
        parts, t = [], start
        while t < end:
            t2 = min(end, t + DAY * (MAX_CANDLES_PER_REQUEST - 1))
            try:
                c = self.client.get_candles(pid, t, t2, "1d")
                self.md_messages += 1
                self.candles_received += len(c)
                parts.append(candles_frame(c))
            except ExchangeAPIError as exc:
                line = f"{pd.Timestamp(self.now()):%Y-%m-%d %H:%M:%S} UTC {coin} ({pid}): {exc}"
                self.connection_errors.append(line)
                print(f"MARKET-DATA ERROR {line}", flush=True)    # never silent
                raise
            finally:
                self.sleep(self.pause)
            t = t2
        df = pd.concat(parts) if parts else candles_frame([])
        return df[~df.index.duplicated(keep="last")].sort_index()

    def check_availability(self) -> None:
        for coin in self.universe:
            pid = f"{coin}-USD"
            try:
                spec = self.client.get_product(pid)
                self.md_messages += 1
            except ExchangeAPIError as exc:
                if exc.status in (400, 404):
                    self.unavailable[coin] = f"{pid}: product not found on Coinbase (HTTP {exc.status})"
                else:   # network/proxy/5xx: we could not check -- do not claim Coinbase lacks the product
                    self.unavailable[coin] = f"{pid}: could not be checked, Coinbase unreachable ({exc})"
                    self.connection_errors.append(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} {pid}: {exc}")
                continue
            finally:
                self.sleep(self.pause)
            if str(spec.status).lower() != "online" or spec.trading_disabled:
                self.unavailable[coin] = f"{pid}: status={spec.status}, trading_disabled={spec.trading_disabled}"
            else:
                self.available[coin] = pid
        if "BTC" not in self.available:
            for coin in list(self.available):
                self.unavailable[coin] = f"{self.available.pop(coin)}: disabled because BTC (regime filter) is unavailable"

    def warmup(self) -> None:
        now = self.now()
        for coin in list(self.available):
            try:
                self.frames[coin] = self._candles(coin, now - DAY * WARMUP_DAYS, now)
            except ExchangeAPIError:
                self.unavailable[coin] = f"{self.available.pop(coin)}: warm-up candles could not be fetched"
        if "BTC" not in self.available:
            for coin in list(self.available):
                self.unavailable[coin] = f"{self.available.pop(coin)}: disabled because BTC warm-up failed"

    def refresh(self) -> list[str]:
        """Fetch the latest daily candles (end = now: never a future end time). Returns the coins that failed;
        each failure has already been printed and recorded by _candles()."""
        now = self.now()
        failed = []
        for coin in list(self.available):
            try:
                new = self._candles(coin, now - DAY * 5, now)
            except ExchangeAPIError:
                failed.append(coin)
                continue
            df = pd.concat([self.frames.get(coin, candles_frame([])), new])
            self.frames[coin] = df[~df.index.duplicated(keep="last")].sort_index()
        if not failed:
            self.last_refresh_ok = now
        return failed

    # -- strategy steps -----------------------------------------------------------------------------------
    def _completed_frames(self, now) -> dict:
        return {c: split_completed(df, now)[0] for c, df in self.frames.items() if c in self.available}

    def startup(self) -> list[str]:
        self.started_at = self.now()
        self.engine = MCMEngine(self.start_equity, self.p, self.universe, enabled=set())
        self.check_availability()
        self.warmup()
        self.engine.enabled = set(self.available)
        now = self.now()
        comp = self._completed_frames(now)
        states = build_states(comp, self.p) if comp else {}
        last_day = max((df.index[-1] for df in comp.values() if len(df)), default=None)
        for c, s in states.items():
            if len(s) and s.index[-1] == last_day:
                r = s.iloc[-1]
                side = "long" if r.long_sig else "short" if r.short_sig else None
                if side:
                    self.startup_signals.append({"coin": c, "side": side, "ret40": float(r.ret), "day": str(last_day.date())})
        self.last_decision_day = utc_day(now)       # first decision: next UTC boundary (see module docstring)
        self.mark(now)
        return self.startup_report()

    def mark(self, now) -> None:
        prices = {}
        for c, df in self.frames.items():
            if c in self.available and len(df):
                prices[c] = float(df.close.iloc[-1])
        self.engine.mark(prices)
        self.equity_marks.append((pd.Timestamp(now).isoformat(), self.engine.equity()))

    def step(self) -> Optional[str]:
        """One poll. Returns a description if a daily decision was executed."""
        now = self.now()
        failed = self.refresh()
        today = utc_day(now)
        done = None
        self.status = f"next decision at {today + DAY:%Y-%m-%d} 00:00 UTC (after the {today:%Y-%m-%d} candle closes)"
        if today > self.last_decision_day:
            yesterday = today - DAY
            comp = self._completed_frames(now)
            have_close = {c for c, df in comp.items() if len(df) and df.index[-1] == yesterday}
            have_open = {c for c, df in self.frames.items() if c in self.available and today in df.index}
            all_ready = have_close >= set(self.available) and have_open >= set(self.available)
            grace_over = pd.Timestamp(now) >= today + DECISION_GRACE
            if "BTC" in have_close and have_open and (all_ready or grace_over):   # wait for the new candles
                states = build_states(comp, self.p)
                self.engine.on_close(yesterday, {c: states[c].loc[yesterday] for c in have_close})
                fills = self.engine.on_open(today, {c: float(self.frames[c].loc[today, "open"]) for c in have_open})
                self.last_decision_day = today
                done = f"{today:%Y-%m-%d}: evaluated {len(have_close)} completed candles, {len(fills)} paper fills"
                log.info(done)
                self.status = f"decided {today:%Y-%m-%d}; next decision at {today + DAY:%Y-%m-%d} 00:00 UTC"
            else:
                n = len(self.available)
                self.status = (f"WAITING for the {today:%Y-%m-%d} daily candle: completed {yesterday:%Y-%m-%d} candle for "
                               f"{len(have_close)}/{n} coins, {today:%Y-%m-%d} candle for {len(have_open)}/{n} coins"
                               + (f"; refresh failed for {', '.join(failed)}" if failed else ""))
                if grace_over:
                    self.status += f" -- WARNING: still not ready {DECISION_GRACE.seconds // 60} min after 00:00 UTC"
                print(f"{pd.Timestamp(now):%Y-%m-%d %H:%M:%S} UTC {self.status}", flush=True)
        self.mark(now)
        self.heartbeat(now)
        self.persist()
        return done

    def signal_states(self) -> dict:
        """Read-only view of each coin's indicators/signals on its latest COMPLETED daily candle, computed with the
        same build_states() the engine uses. Display only: it never creates orders or changes engine state."""
        if self.engine is None or not self.frames:
            return {}
        comp = {c: df for c, df in self._completed_frames(self.now()).items() if len(df)}
        if not comp:
            return {}
        states = build_states(comp, self.p)
        out = {}
        for c, st in states.items():
            r = st.iloc[-1]
            pos = self.engine.pf.positions.get(c)
            num = lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)
            out[c] = {"candle": str(st.index[-1].date()), "close": num(r.close), "ret40": num(r.ret), "ema200": num(r.ema),
                      "raw_long": bool(r.raw_long), "raw_short": bool(r.raw_short),
                      "regime_ok_long": bool(r.regime_ok_long), "regime_ok_short": bool(r.regime_ok_short),
                      "long_sig": bool(r.long_sig), "short_sig": bool(r.short_sig),
                      "exit_long": bool(r.exit_long), "exit_short": bool(r.exit_short),
                      "position": pos.side if pos else None}
        return out

    def heartbeat(self, now, force: bool = False) -> Optional[str]:
        if not force and self.last_heartbeat is not None and pd.Timestamp(now) - pd.Timestamp(self.last_heartbeat) < HEARTBEAT:
            return None
        self.last_heartbeat = now
        today = utc_day(now)
        held = sum(len(df) for c, df in self.frames.items() if c in self.available)
        with_today = sum(1 for c, df in self.frames.items() if c in self.available and today in df.index)
        pos = ", ".join(f"{c} {p.side}" for c, p in self.engine.pf.positions.items()) or "none"
        last_ok = f"{pd.Timestamp(self.last_refresh_ok):%Y-%m-%d %H:%M:%S} UTC" if self.last_refresh_ok else "never"
        line = (f"HEARTBEAT {pd.Timestamp(now):%Y-%m-%d %H:%M:%S} UTC | last successful market-data refresh: {last_ok} | "
                f"candles held: {held} ({with_today}/{len(self.available)} coins have today's candle) | "
                f"equity ${self.engine.equity():,.2f} | open positions: {pos} | "
                f"paper orders (filled): {self.engine.pf.paper_orders} | live orders: 0 | "
                f"order_endpoint_called: {'YES' if self.order_endpoint_called() else 'NO'} | "
                f"errors so far: {len(self.connection_errors)} | {self.status}")
        print(line, flush=True)
        return line

    # -- reports ----------------------------------------------------------------------------------------
    def startup_report(self) -> list[str]:
        p = self.p
        return [
            "=" * 78, "multi_crypto_momentum - PAPER SESSION STARTUP", "=" * 78,
            "Strategy     : daily; LONG if 40d return > +5% and close > EMA200; SHORT if 40d return < -5% and close < EMA200;",
            "               alts need BTC close > BTC EMA200 for longs (< for shorts); exits: 40d return crosses 0 or",
            "               close crosses EMA200; signal on the completed daily candle, fill at the next candle's open",
            f"Universe     : {', '.join(self.universe)}",
            f"Market data  : {MARKET_LABEL}",
            f"Available    : {', '.join(f'{c} ({pid})' for c, pid in self.available.items()) or 'NONE'}",
            f"Unavailable  : {'; '.join(f'{c}: {why}' for c, why in self.unavailable.items()) or 'none'} (disabled, NOT substituted)",
            f"Allocation   : max {p.max_per_coin:.0%} of equity per coin at entry, max {p.max_total:.0%} gross exposure, 1x, "
            "no leverage/borrowing; priority = |40d return| desc, then universe order",
            f"Fees         : {p.fee_rate:.3%} per side + {p.slippage_rate:.3%} slippage per side (configurable)",
            f"Starting bal.: ${self.start_equity:,.2f}",
            f"Signals now  : {self.startup_signals or 'none'} (not traded: their execution candle opened before startup)",
            "-" * 78,
            "PAPER MODE: ENABLED",
            f"order_endpoint_called: {'YES' if self.order_endpoint_called() else 'NO'}",
            f"paper orders: {self.engine.pf.paper_orders} | live orders: 0 (no live order path exists in this project)"
            " [values AT STARTUP; live counters are in every HEARTBEAT line and state.json]",
            f"starting equity: ${self.start_equity:,.2f}",
            "=" * 78,
        ]

    def final_report(self, end_reason: str) -> dict:
        eng = self.engine
        eq = pd.Series([v for _t, v in self.equity_marks], dtype=float)
        peak = np.maximum.accumulate(np.r_[self.start_equity, eq.to_numpy()])[1:] if len(eq) else np.array([1.0])
        mdd = float((1 - eq.to_numpy() / peak).max()) if len(eq) else 0.0
        trades = pd.DataFrame(eng.pf.trades)
        ev = pd.DataFrame(eng.events)
        sig = ev[ev.kind == "signal"] if len(ev) else ev
        rej = ev[ev.kind == "signal_rejected"] if len(ev) else ev
        end_eq = eng.equity()
        by_coin = {}
        if len(trades):
            for c, g in trades.groupby("coin"):
                by_coin[c] = {"trades": len(g), "wins": int((g.pnl > 0).sum()), "losses": int((g.pnl <= 0).sum()),
                              "pnl": float(g.pnl.sum()), "fees": float(g.fees.sum())}
        return {
            "strategy": "multi_crypto_momentum", "market_data": MARKET_LABEL, "end_reason": end_reason,
            "started_at": str(self.started_at), "ended_at": str(self.now()),
            "starting_equity": self.start_equity, "ending_equity": end_eq, "pnl": end_eq - self.start_equity,
            "return_pct": end_eq / self.start_equity - 1, "max_drawdown": mdd,
            "closed_trades": len(trades), "winning_trades": int((trades.pnl > 0).sum()) if len(trades) else 0,
            "losing_trades": int((trades.pnl <= 0).sum()) if len(trades) else 0, "trades_by_coin": by_coin,
            "fees_paid": eng.pf.fees_paid, "slippage_paid": eng.pf.slippage_paid,
            "current_positions": eng.snapshot()["positions"],
            "signals_generated": sig.to_dict("records") if len(sig) else [],
            "signals_rejected": rej.to_dict("records") if len(rej) else [],
            "startup_signals_not_traded": self.startup_signals,
            "available_symbols": self.available, "unavailable_symbols": self.unavailable,
            "market_data_messages": self.md_messages, "candles_received": self.candles_received,
            "connection_errors": self.connection_errors, "paper_orders": eng.pf.paper_orders, "live_orders": 0,
            "order_endpoint_called": self.order_endpoint_called(),
            "requests_refused_by_allowlist": sum(1 for _m, _p, ok in self.transport.request_log if not ok),
            "params": params_dict(self.p),
        }

    def persist(self, final: Optional[dict] = None) -> None:
        if self.out_dir is None:
            return
        self.out_dir.mkdir(parents=True, exist_ok=True)
        pf = self.engine.pf
        snap = {"schema": 2, "now": str(self.now()), "status": self.status,
                "last_successful_refresh": str(self.last_refresh_ok),
                "connection_errors_total": len(self.connection_errors),
                "connection_errors": self.connection_errors[-500:],
                # session facts and live safety counters (the dashboard reads these; nothing here is inferred)
                "paper_mode": True, "started_at": str(self.started_at), "start_equity": self.start_equity,
                "params": params_dict(self.p), "poll_seconds": getattr(self, "poll_s", None),
                "available_symbols": self.available, "unavailable_symbols": self.unavailable,
                "paper_orders": pf.paper_orders, "live_orders": 0, "order_endpoint_called": self.order_endpoint_called(),
                "fees_paid": pf.fees_paid, "slippage_paid": pf.slippage_paid,
                "last_decision_day": str(self.last_decision_day.date()) if self.last_decision_day is not None else None,
                "last_prices": self.engine.last_price,
                "positions_detail": {c: {"side": p.side, "qty": p.qty, "entry_ref": p.entry_ref, "entry_fill": p.entry_fill,
                                         "entry_time": str(p.entry_time), "notional": p.notional, "entry_fee": p.entry_fee,
                                         "entry_slippage": p.entry_slippage, "signal_ret40": p.signal_ret}
                                     for c, p in pf.positions.items()},
                "signal_states": self.signal_states(),
                "startup_signals_not_traded": self.startup_signals,
                "snapshot": self.engine.snapshot(), "events": self.engine.events,
                "trades": pf.trades, "equity_marks": self.equity_marks[-5000:]}
        # atomic replace: a reader (e.g. the dashboard) never sees a half-written file
        tmp = self.out_dir / "state.json.tmp"
        tmp.write_text(json.dumps(snap, indent=1, default=str))
        os.replace(tmp, self.out_dir / "state.json")
        if final is not None:
            (self.out_dir / "final_report.json").write_text(json.dumps(final, indent=2, default=str))


def format_final(r: dict) -> str:
    L = ["=" * 78, "multi_crypto_momentum - PAPER SESSION REPORT", "=" * 78,
         f"Market data      : {r['market_data']}", f"Session          : {r['started_at']} -> {r['ended_at']} ({r['end_reason']})",
         f"Starting equity  : ${r['starting_equity']:,.2f}", f"Ending equity    : ${r['ending_equity']:,.2f}",
         f"P&L              : ${r['pnl']:,.2f} ({r['return_pct']:.2%})", f"Max drawdown     : {r['max_drawdown']:.2%}",
         f"Closed trades    : {r['closed_trades']} (winning {r['winning_trades']}, losing {r['losing_trades']})",
         f"Trades by coin   : {r['trades_by_coin'] or 'none'}",
         f"Fees / slippage  : ${r['fees_paid']:,.2f} / ${r['slippage_paid']:,.2f}",
         f"Open positions   : {r['current_positions'] or 'none'}",
         f"Signals generated: {len(r['signals_generated'])}; rejected: {len(r['signals_rejected'])} "
         f"({pd.Series([x['reason'] for x in r['signals_rejected']]).value_counts().to_dict() if r['signals_rejected'] else {}})",
         f"Startup signals (not traded): {r['startup_signals_not_traded'] or 'none'}",
         f"Available        : {r['available_symbols']}", f"Unavailable      : {r['unavailable_symbols'] or 'none'}",
         f"Market-data msgs : {r['market_data_messages']} REST responses, {r['candles_received']} candles",
         f"Connection errors: {len(r['connection_errors'])}" + (f" (last: {r['connection_errors'][-1]})" if r['connection_errors'] else ""),
         "-" * 78, "PAPER MODE: ENABLED",
         f"order_endpoint_called: {'YES' if r['order_endpoint_called'] else 'NO'}",
         f"paper orders: {r['paper_orders']} | live orders: {r['live_orders']}",
         f"CONFIRMATION: {'NO live order endpoint was called.' if not r['order_endpoint_called'] else 'AN ORDER PATH WAS ATTEMPTED (refused by the allowlist).'}",
         "=" * 78]
    return "\n".join(L)


def run(session: MCMPaperSession, duration_s: float, poll_s: float, clock: Optional[SessionClock] = None,
        max_polls: Optional[int] = None) -> dict:
    clock = clock or SessionClock(duration_s)
    session.poll_s = poll_s
    stop = {"reason": "duration reached"}

    def on_sigint(*_):
        stop["reason"] = "interrupted (Ctrl+C)"
        stop["now"] = True
    old = _signal.signal(_signal.SIGINT, on_sigint) if hasattr(_signal, "SIGINT") else None
    polls = 0
    try:
        while not clock.expired() and not stop.get("now") and (max_polls is None or polls < max_polls):
            try:
                msg = session.step()
                if msg:
                    print(msg, flush=True)
            except ForbiddenEndpointError:
                raise
            except Exception as exc:                      # keep the session alive; record the problem
                session.connection_errors.append(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} step: {type(exc).__name__}: {exc}")
                log.warning("poll failed: %s", exc)
            polls += 1
            wait = min(poll_s, max(clock.remaining(), 0))
            end = time.monotonic() + wait
            while not stop.get("now") and time.monotonic() < end and not clock.expired():
                session.sleep(min(1.0, max(end - time.monotonic(), 0)))
    finally:
        if old is not None:
            _signal.signal(_signal.SIGINT, old)
    final = session.final_report(stop["reason"])
    session.persist(final)
    return final


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="multi_crypto_momentum paper session (PAPER ONLY)")
    ap.add_argument("--duration", type=float, default=7 * 24 * 3600, help="seconds (default 7 days)")
    ap.add_argument("--poll", type=float, default=300, help="seconds between polls (default 300)")
    ap.add_argument("--start", type=float, default=200.0)
    ap.add_argument("--fee", type=float, default=MCMParams.fee_rate)
    ap.add_argument("--slippage", type=float, default=MCMParams.slippage_rate)
    args = ap.parse_args(argv)
    try:
        require_paper_mode()
    except PaperModeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    params = MCMParams(fee_rate=args.fee, slippage_rate=args.slippage)
    out = REPO_ROOT / "paper_trading" / "records" / f"mcm_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    client = CoinbaseAdvancedClient(credentials=None, transport=ReadOnlyTransport(None))   # public, read-only
    session = MCMPaperSession(client, params, args.start, out_dir=out)
    print("\n".join(session.startup()), flush=True)
    if not session.available:
        final = session.final_report("no available symbols")
        session.persist(final)
        print(format_final(final))
        return 1
    final = run(session, args.duration, args.poll)
    print(format_final(final), flush=True)
    print(f"records: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
