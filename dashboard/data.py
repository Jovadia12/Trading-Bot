"""Read-only data layer for the paper-trading dashboard.

It reads ONLY the files the paper runner already writes (paper_trading/records/mcm_<UTC>/state.json and, once a
session ends, final_report.json). It makes no network calls, imports no exchange/order code and never writes
anything. Values the runner did not record are returned as None (shown as "N/A"); nothing is invented.

Two state.json formats exist:
  * schema 1 (runner commit 1c04321, e.g. a session started before the dashboard existed): status, errors,
    snapshot (equity/cash/exposure/positions), events (signals, rejections, fills), trades, equity_marks.
  * schema 2 (this version): adds session facts, live paper/live order counters, last prices, position detail
    and per-coin signal states. Fields derived for schema 1 are labelled as derived.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORDS_DIR = REPO_ROOT / "paper_trading" / "records"
UNIVERSE = ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "LINK", "ADA", "AVAX", "DOT")
DEFAULT_POLL_S = 300
MAX_EQUITY_MARKS = 5000          # the runner keeps the last 5000 marks


# ----------------------------------------------------------------------------------------------- helpers
def ts(v) -> Optional[pd.Timestamp]:
    if v is None or v == "" or str(v) in ("None", "NaT", "nan"):
        return None
    try:
        t = pd.Timestamp(v)
    except (ValueError, TypeError):
        return None
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def iso(t: Optional[pd.Timestamp]) -> Optional[str]:
    return None if t is None else t.strftime("%Y-%m-%d %H:%M:%S UTC")


def num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def pct(a, b) -> Optional[float]:
    a, b = num(a), num(b)
    return None if a is None or b in (None, 0) else a / b


# ------------------------------------------------------------------------------------------- file access
def find_session_dir(root: Path = RECORDS_DIR, name: Optional[str] = None) -> Optional[Path]:
    """The named session, else the newest mcm_<UTC timestamp> directory that has a state.json."""
    root = Path(root)
    if name:
        d = root / name
        return d if (d / "state.json").is_file() else None
    dirs = sorted((d for d in root.glob("mcm_*") if (d / "state.json").is_file()), key=lambda d: d.name)
    return dirs[-1] if dirs else None


@dataclass
class StateReader:
    """Reads state.json defensively; keeps the last good copy if a read fails (e.g. a write in progress by an older
    runner that did not write atomically)."""
    root: Path = RECORDS_DIR
    session: Optional[str] = None
    _last: dict = field(default_factory=dict)

    def read(self) -> dict:
        d = find_session_dir(self.root, self.session)
        if d is None:
            return {"ok": False, "error": f"no paper session found under {self.root} (mcm_*/state.json)",
                    "state": None, "final": None, "path": None}
        err = None
        for attempt in range(3):
            try:
                state = json.loads((d / "state.json").read_text())
                break
            except (json.JSONDecodeError, OSError) as exc:
                err, state = f"{type(exc).__name__}: {exc}", None
                time.sleep(0.05 * (attempt + 1))
        final = None
        if (d / "final_report.json").is_file():
            try:
                final = json.loads((d / "final_report.json").read_text())
            except (json.JSONDecodeError, OSError):
                final = None
        if state is None:
            last = self._last.get(str(d))
            return {"ok": last is not None, "stale_read": True, "error": err, "state": last, "final": final, "path": str(d)}
        self._last[str(d)] = state
        return {"ok": True, "stale_read": False, "error": None, "state": state, "final": final, "path": str(d)}


# ------------------------------------------------------------------------------------------- sections
def _marks(state) -> pd.Series:
    rows = [(ts(t), num(v)) for t, v in state.get("equity_marks") or [] if ts(t) is not None and num(v) is not None]
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series([v for _t, v in rows], index=pd.DatetimeIndex([t for t, _v in rows]))
    return s[~s.index.duplicated(keep="last")].sort_index()


def _start_equity(state) -> tuple[Optional[float], str]:
    if num(state.get("start_equity")) is not None:
        return num(state["start_equity"]), "recorded by the runner"
    marks = state.get("equity_marks") or []
    if marks and len(marks) < MAX_EQUITY_MARKS:
        # the runner marks equity at startup, when the account is flat, so the first mark IS the starting balance
        return num(marks[0][1]), "first equity mark (startup, flat account)"
    return None, "not recorded"


def _events(state, kind=None, coin=None) -> list[dict]:
    out = []
    for e in state.get("events") or []:
        if (kind is None or e.get("kind") == kind) and (coin is None or e.get("coin") == coin):
            out.append(e)
    return out


def _entry_reason(state, coin, side, entry_time, signal_ret=None) -> str:
    """Why the paper engine entered: the strategy signal on the completed candle before the fill."""
    sig = [e for e in _events(state, "signal", coin) if e.get("side") == side and ts(e.get("time")) is not None
           and entry_time is not None and ts(e["time"]) < entry_time]
    r = num(sig[-1].get("ret40")) if sig else num(signal_ret)
    day = ts(sig[-1]["time"]).strftime("%Y-%m-%d") if sig else None
    if side == "long":
        rule = "40-day return {} > +5% and close > EMA200".format(f"{r:+.2%}" if r is not None else "N/A")
        regime = "" if coin == "BTC" else "; BTC above its EMA200 (alt regime filter passed)"
    else:
        rule = "40-day return {} < -5% and close < EMA200".format(f"{r:+.2%}" if r is not None else "N/A")
        regime = "" if coin == "BTC" else "; BTC below its EMA200 (alt regime filter passed)"
    when = f"{side.upper()} signal on the {day} daily close: " if day else f"{side.upper()} signal: "
    return when + rule + regime + "; filled at the next daily open"


def _positions(state, equity) -> list[dict]:
    snap = state.get("snapshot") or {}
    detail = state.get("positions_detail") or {}
    prices = state.get("last_prices") or {}
    sigs = state.get("signal_states") or {}
    rows = []
    for coin, p in (snap.get("positions") or {}).items():
        d = detail.get(coin, {})
        side = p.get("side")
        qty, entry_fill, value = num(p.get("qty")), num(p.get("entry_fill")), num(p.get("value"))
        price, price_src = num(prices.get(coin)), "last market price recorded by the runner"
        if price is None and qty:
            # schema 1: the mark price is implied exactly by value = qty*price (long) or notional + qty*(entry-price) (short)
            price = value / qty if side == "long" else 2 * entry_fill - value / qty
            price_src = "derived from the position's marked value"
        cost = qty * entry_fill if qty is not None and entry_fill is not None else None
        unreal = value - cost if value is not None and cost is not None else None
        exposure = abs(qty * price) if qty is not None and price is not None else None
        entry_time = ts(p.get("entry_time"))
        s = sigs.get(coin, {})
        regime = None
        if coin == "BTC":
            regime = "n/a (BTC is not filtered)"
        elif s:
            ok = s.get("regime_ok_long") if side == "long" else s.get("regime_ok_short")
            regime = "satisfied" if ok else "NOT satisfied (does not force an exit; exits use the coin's own rules)"
        rows.append({
            "symbol": coin, "side": side, "entry_time": iso(entry_time),
            "entry_price": num(d.get("entry_ref")), "entry_fill": entry_fill, "current_price": price,
            "price_source": price_src, "qty": qty, "notional_at_entry": cost, "market_value": value,
            "allocation_pct": pct(exposure, equity), "unrealized_pnl": unreal, "unrealized_pct": pct(unreal, cost),
            "entry_fee": num(d.get("entry_fee")), "ret40": num(s.get("ret40")), "ema200": num(s.get("ema200")),
            "indicator_candle": s.get("candle"), "btc_regime": regime,
            "entry_reason": _entry_reason(state, coin, side, entry_time, d.get("signal_ret40")),
        })
    return sorted(rows, key=lambda r: UNIVERSE.index(r["symbol"]) if r["symbol"] in UNIVERSE else 99)


def _trades(state, positions) -> list[dict]:
    out = []
    for t in state.get("trades") or []:
        et, xt = ts(t.get("entry_time")), ts(t.get("exit_time"))
        fees, net = num(t.get("fees")), num(t.get("pnl"))
        out.append({"status": "CLOSED", "symbol": t.get("coin"), "side": t.get("side"), "entry_time": iso(et),
                    "entry_price": num(t.get("entry_ref")), "entry_fill": num(t.get("entry_fill")),
                    "exit_time": iso(xt), "exit_price": num(t.get("exit_ref")), "exit_fill": num(t.get("exit_fill")),
                    "qty": num(t.get("qty")), "notional": num(t.get("notional")), "fees": fees,
                    "slippage": num(t.get("slippage")),
                    # gross = P&L after slippage, before fees (pnl is recorded net of entry+exit fees)
                    "gross_pnl": net + fees if net is not None and fees is not None else None,
                    "net_pnl": net, "return_pct": num(t.get("ret_on_notional")),
                    "entry_reason": _entry_reason(state, t.get("coin"), t.get("side"), et, t.get("signal_ret40")),
                    "exit_reason": t.get("exit_reason")})
    for p in positions:
        out.append({"status": "OPEN", "symbol": p["symbol"], "side": p["side"], "entry_time": p["entry_time"],
                    "entry_price": p["entry_price"], "entry_fill": p["entry_fill"], "exit_time": None,
                    "exit_price": None, "exit_fill": None, "qty": p["qty"], "notional": p["notional_at_entry"],
                    "fees": p["entry_fee"], "slippage": None, "gross_pnl": None, "net_pnl": None,
                    "unrealized_pnl": p["unrealized_pnl"], "return_pct": p["unrealized_pct"],
                    "entry_reason": p["entry_reason"], "exit_reason": None})
    return sorted(out, key=lambda r: r["entry_time"] or "", reverse=True)


def _next_decision(state, now_state: Optional[pd.Timestamp]) -> Optional[str]:
    status = str(state.get("status") or "")
    if status.startswith("WAITING"):
        return "due now: waiting for the new daily candles (see status)"
    if now_state is None:
        return None
    return iso(now_state.floor("1D") + pd.Timedelta(days=1))


def _bot_status(state, final, now_state, server_now) -> dict:
    if final:
        return {"state": "STOPPED", "detail": f"session ended: {final.get('end_reason', 'N/A')}"}
    if now_state is None:
        return {"state": "UNKNOWN", "detail": "state.json has no timestamp"}
    poll = num(state.get("poll_seconds")) or DEFAULT_POLL_S
    age = (server_now - now_state).total_seconds()
    if age < -120:
        return {"state": "RUNNING", "detail": f"state time is {-age / 60:.0f} min AHEAD of this machine's clock (clock skew)"}
    age = max(age, 0.0)
    limit = max(3 * poll, 900)
    if age > limit:
        return {"state": "STALE", "detail": f"no update for {age / 60:.0f} min (expected every {poll / 60:.0f} min): "
                                            "the runner may be stopped or the machine asleep"}
    return {"state": "RUNNING", "detail": f"last update {age:.0f}s ago"}


def _period_pnl(marks: pd.Series, equity, start_equity, period_start: pd.Timestamp) -> tuple:
    before = marks[marks.index < period_start]
    base = num(before.iloc[-1]) if len(before) else start_equity
    if base is None or equity is None:
        return None, None
    return equity - base, pct(equity - base, base)


def _trade_stats(trades: list[dict]) -> dict:
    closed = [t for t in trades if t["status"] == "CLOSED" and t["net_pnl"] is not None]
    if not closed:
        return {"trades": 0, "win_rate": None, "profit_factor": None, "avg_win": None, "avg_loss": None,
                "best": None, "worst": None, "by_side": {}}
    wins = [t["net_pnl"] for t in closed if t["net_pnl"] > 0]
    losses = [t["net_pnl"] for t in closed if t["net_pnl"] <= 0]
    best = max(closed, key=lambda t: t["net_pnl"])
    worst = min(closed, key=lambda t: t["net_pnl"])
    by_side = {}
    for side in ("long", "short"):
        g = [t["net_pnl"] for t in closed if t["side"] == side]
        if g:
            gw, gl = sum(x for x in g if x > 0), -sum(x for x in g if x <= 0)
            by_side[side] = {"trades": len(g), "win_rate": sum(1 for x in g if x > 0) / len(g),
                             "net_pnl": sum(g), "profit_factor": gw / gl if gl > 0 else None}
    gl = -sum(losses)
    return {"trades": len(closed), "win_rate": len(wins) / len(closed),
            "profit_factor": sum(wins) / gl if gl > 0 else None,
            "avg_win": sum(wins) / len(wins) if wins else None, "avg_loss": sum(losses) / len(losses) if losses else None,
            "best": {"symbol": best["symbol"], "side": best["side"], "net_pnl": best["net_pnl"], "exit_time": best["exit_time"]},
            "worst": {"symbol": worst["symbol"], "side": worst["side"], "net_pnl": worst["net_pnl"], "exit_time": worst["exit_time"]},
            "by_side": by_side}


def _performance(marks: pd.Series, start_equity, trades) -> dict:
    perf = {"equity_curve": [], "daily": [], "cumulative": [], "drawdown": [], "monthly": [], "stats": _trade_stats(trades)}
    if marks.empty:
        return perf
    m = marks
    if len(m) > 1500:                              # keep the payload small; the last point is always kept
        step = math.ceil(len(m) / 1500)
        m = pd.concat([m.iloc[::step], m.iloc[-1:]])
        m = m[~m.index.duplicated(keep="last")]
    base = start_equity if start_equity is not None else num(marks.iloc[0])
    peak = marks.cummax().clip(lower=base)
    dd = marks / peak - 1
    perf["equity_curve"] = [[iso(t), v] for t, v in m.items()]
    perf["cumulative"] = [[iso(t), v - base] for t, v in m.items()]
    perf["drawdown"] = [[iso(t), num(dd.loc[t])] for t in m.index]
    daily = marks.resample("1D").last().dropna()
    prev = base
    for t, v in daily.items():
        perf["daily"].append({"date": t.strftime("%Y-%m-%d"), "equity": v, "pnl": v - prev, "pnl_pct": pct(v - prev, prev)})
        prev = v
    monthly = marks.resample("ME").last().dropna()
    prev = base
    for t, v in monthly.items():
        perf["monthly"].append({"month": t.strftime("%Y-%m"), "equity": v, "pnl": v - prev, "pnl_pct": pct(v - prev, prev)})
        prev = v
    return perf


def _signal_table(state) -> tuple[list[dict], str]:
    sigs = state.get("signal_states") or {}
    prices = state.get("last_prices") or {}
    rows = []
    if sigs:
        for coin in [c for c in UNIVERSE if c in sigs]:
            s = sigs[coin]
            pos = s.get("position")
            ret, ema, close = num(s.get("ret40")), num(s.get("ema200")), num(s.get("close"))
            if pos == "long":
                sig = "EXIT LONG at next open" if s.get("exit_long") else "HOLD LONG"
                why = ("40-day return below 0%" if (ret is not None and ret < 0) else "close below EMA200") \
                    if s.get("exit_long") else "long exit conditions not met (40-day return >= 0% and close >= EMA200)"
            elif pos == "short":
                sig = "EXIT SHORT at next open" if s.get("exit_short") else "HOLD SHORT"
                why = ("40-day return above 0%" if (ret is not None and ret > 0) else "close above EMA200") \
                    if s.get("exit_short") else "short exit conditions not met (40-day return <= 0% and close <= EMA200)"
            elif s.get("long_sig"):
                sig, why = "LONG ENTRY signal", "40-day return > +5% and close > EMA200" + ("" if coin == "BTC" else ", BTC regime bullish")
            elif s.get("short_sig"):
                sig, why = "SHORT ENTRY signal", "40-day return < -5% and close < EMA200" + ("" if coin == "BTC" else ", BTC regime bearish")
            elif s.get("raw_long"):
                sig, why = "LONG blocked", "coin qualifies but BTC is not above its EMA200 (alt regime filter)"
            elif s.get("raw_short"):
                sig, why = "SHORT blocked", "coin qualifies but BTC is not below its EMA200 (alt regime filter)"
            else:
                sig = "NO SIGNAL"
                if ret is None or ema is None:
                    why = "indicators not available (needs 200 completed daily candles)"
                elif abs(ret) <= 0.05:
                    why = f"40-day return {ret:+.2%} is inside the ±5% band"
                else:
                    why = f"40-day return {ret:+.2%} and close {'above' if close > ema else 'below'} EMA200 disagree"
            if coin == "BTC":
                regime = "n/a (BTC not filtered)"
            else:
                regime = "bullish (alt longs allowed)" if s.get("regime_ok_long") else \
                    "bearish (alt shorts allowed)" if s.get("regime_ok_short") else "neutral / unknown"
            rows.append({"symbol": coin, "candle": s.get("candle"), "ret40": ret, "ema200": ema, "close": close,
                         "price": num(prices.get(coin)), "long_eligible": bool(s.get("raw_long")),
                         "short_eligible": bool(s.get("raw_short")), "btc_regime": regime, "position": pos,
                         "signal": sig, "reason": why})
        return rows, "computed by the runner from the latest COMPLETED daily candle (same build_states() as the engine)"
    # schema 1 fallback: what the engine logged at its last decision (no fresh indicator values exist)
    by_coin = {}
    for e in state.get("events") or []:
        if e.get("kind") in ("signal", "signal_rejected", "exit_signal"):
            by_coin[e.get("coin")] = e
    snap_pos = (state.get("snapshot") or {}).get("positions") or {}
    for coin in UNIVERSE:
        e = by_coin.get(coin)
        rows.append({"symbol": coin, "candle": str(ts(e["time"]).date()) if e and ts(e.get("time")) else None,
                     "ret40": num(e.get("ret40")) if e else None, "ema200": None, "close": None,
                     "price": num(prices.get(coin)), "long_eligible": None, "short_eligible": None, "btc_regime": None,
                     "position": (snap_pos.get(coin) or {}).get("side"),
                     "signal": (f"{e['kind'].replace('_', ' ')}: {e.get('side', '')}".strip() if e else "N/A"),
                     "reason": (e.get("reason") or "") if e else "N/A"})
    return rows, ("LAST DECISION EVENTS ONLY: this session's runner version does not record per-coin indicator "
                  "states (EMA200, eligibility) -- they appear after the runner is next restarted with this version")


RULES = [
    ("Universe", "BTC, ETH, SOL, XRP, BNB, DOGE, LINK, ADA, AVAX, DOT (Coinbase <COIN>-USD spot prices as a perp proxy)"),
    ("Timeframe", "Daily UTC candles. Signals use the COMPLETED candle; paper fills at the NEXT daily open (00:00 UTC)."),
    ("Long entry", "40-day return > +5% AND close > EMA200. Alts additionally need BTC close > BTC EMA200."),
    ("Short entry", "40-day return < -5% AND close < EMA200. Alts additionally need BTC close < BTC EMA200."),
    ("Long exit", "40-day return crosses below 0% OR close crosses below EMA200."),
    ("Short exit", "40-day return crosses above 0% OR close crosses above EMA200."),
    ("Sizing", "Max 10% of equity per coin at entry, max 100% gross exposure, 1x, no leverage, no borrowing. "
               "Exits first, then entries by |40-day return| (ties: universe order)."),
    ("Costs (paper)", "0.05% fee + 0.02% slippage per side (configurable in the runner)."),
]


def build_dashboard(read: dict, server_now: Optional[pd.Timestamp] = None) -> dict:
    server_now = server_now or pd.Timestamp.now(tz="UTC")
    state, final = read.get("state"), read.get("final")
    base = {"generated_at": iso(server_now), "source": {"path": read.get("path"), "read_ok": read.get("ok"),
                                                         "stale_read": read.get("stale_read"), "error": read.get("error")},
            "safety": {"paper_mode": "ON", "live_trading": "OFF",
                       "dashboard": "read-only: GET routes only, no network calls, no exchange/order code imported"}}
    if not state:
        return {**base, "available": False}
    schema = int(state.get("schema") or 1)
    snap = state.get("snapshot") or {}
    now_state = ts(state.get("now"))
    marks = _marks(state)
    equity, cash, gross = num(snap.get("equity")), num(snap.get("cash")), num(snap.get("gross_exposure"))
    start, start_src = _start_equity(state)
    positions = _positions(state, equity)
    trades = _trades(state, positions)
    closed = [t for t in trades if t["status"] == "CLOSED"]
    realized = sum(t["net_pnl"] for t in closed if t["net_pnl"] is not None) if closed else 0.0
    unrealized = sum(p["unrealized_pnl"] for p in positions if p["unrealized_pnl"] is not None)
    total = equity - start if equity is not None and start is not None else None
    ref_now = now_state or server_now
    today = _period_pnl(marks, equity, start, ref_now.floor("1D"))
    month = _period_pnl(marks, equity, start, ref_now.floor("1D").replace(day=1))
    peak = max([start or 0.0] + ([float(marks.max())] if len(marks) else []))
    fills = _events(state, "fill_entry") + _events(state, "fill_exit")
    paper_orders = state.get("paper_orders")
    bot = _bot_status(state, final, now_state, server_now)
    signals = _events(state, "signal")
    rejected = _events(state, "signal_rejected")
    reasons: dict = {}
    for e in rejected:
        reasons[e.get("reason")] = reasons.get(e.get("reason"), 0) + 1
    sig_rows, sig_src = _signal_table(state)
    oe = state.get("order_endpoint_called")
    if oe is None and final:
        oe = final.get("order_endpoint_called")
    return {
        **base, "available": True, "schema": schema,
        "overview": {
            "equity": equity, "start_equity": start, "start_equity_source": start_src,
            "total_pnl": total, "total_pnl_pct": pct(total, start),
            "today_pnl": today[0], "today_pnl_pct": today[1], "month_pnl": month[0], "month_pnl_pct": month[1],
            "cash": cash, "invested_capital": sum(p["notional_at_entry"] or 0 for p in positions) if positions else 0.0,
            "gross_exposure": gross, "gross_exposure_pct": pct(gross, equity),
            "open_positions": len(positions), "closed_trades": len(closed),
            "realized_pnl": realized, "unrealized_pnl": unrealized,
            "open_position_costs": (start + realized + unrealized - equity)
            if None not in (start, equity) else None,   # entry fees/slippage of open positions (equity identity)
            "current_drawdown": pct(equity - peak, peak) if equity is not None and peak else None,
            "bot_status": bot, "status_text": state.get("status"),
            "last_market_data_update": iso(ts(state.get("last_successful_refresh"))),
            "next_decision": _next_decision(state, now_state),
            "error_count": state.get("connection_errors_total", len(state.get("connection_errors") or [])),
            "state_time": iso(now_state)},
        "positions": positions,
        "trades": trades,
        "strategy": {"rules": RULES, "signals": sig_rows, "signals_source": sig_src,
                     "startup_signals_not_traded": state.get("startup_signals_not_traded")},
        "performance": _performance(marks, start, trades),
        "status": {
            "paper_mode": "ON" if state.get("paper_mode", True) else "UNKNOWN",
            "paper_mode_basis": "the runner refuses to start unless PAPER_MODE=true; this state file only exists if it started",
            "live_trading": "OFF (no live order code path exists in this project)",
            "bot": bot, "status_text": state.get("status"),
            "data_feed": ("OK" if state.get("last_successful_refresh") not in (None, "None") and bot["state"] == "RUNNING"
                          else "NO SUCCESSFUL REFRESH YET" if state.get("last_successful_refresh") in (None, "None")
                          else "STALE"),
            "last_successful_refresh": iso(ts(state.get("last_successful_refresh"))),
            "next_decision": _next_decision(state, now_state),
            "data_errors": state.get("connection_errors_total", len(state.get("connection_errors") or [])),
            "recent_errors": (state.get("connection_errors") or [])[-20:],
            "paper_orders": paper_orders if paper_orders is not None else len(fills),
            "paper_orders_source": "runner counter" if paper_orders is not None else "counted from recorded fill events",
            "live_orders": 0,
            "order_endpoint_called": oe,
            "order_endpoint_source": "recorded by the runner" if state.get("order_endpoint_called") is not None
            else ("final report" if oe is not None else "not recorded by this runner version (the final report confirms it)"),
            "pipeline": {"signals": len(signals), "signals_rejected": len(rejected), "rejections_by_reason": reasons,
                         "paper_orders_filled": paper_orders if paper_orders is not None else len(fills),
                         "entry_fills": len(_events(state, "fill_entry")), "exit_fills": len(_events(state, "fill_exit")),
                         "open_positions": len(positions), "closed_trades": len(closed)},
            "available_symbols": state.get("available_symbols"), "unavailable_symbols": state.get("unavailable_symbols"),
            "started_at": iso(ts(state.get("started_at"))), "session_dir": read.get("path")},
    }
