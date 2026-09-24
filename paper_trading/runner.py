"""Paper-trading session runner: Coinbase market data -> paper execution -> records.

Usage (from repo root; credentials come from the environment or a git-ignored .env):
    PAPER_MODE=true python3 -m paper_trading --duration 300
    PAPER_MODE=true python -m paper_trading --duration 300 --demo-roundtrip
    PAPER_MODE=true python -m paper_trading --replay tests/fixtures/ws_btcusd_synthetic.jsonl --demo-roundtrip

No strategy is attached in this phase. ``--demo-roundtrip`` runs a scripted execution-path
smoke test (maker entry -> taker exit, and taker entry -> taker exit). It is not a strategy.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Optional

from config.logging_setup import setup_logging
from config.settings import REPO_ROOT, PaperModeError, Settings, load_settings
from exchange.client import CoinbaseAdvancedClient, summarize_balances
from exchange.endpoints import WS_MARKET_DATA_URL
from exchange.transport import ReadOnlyTransport
from execution.fees import DEFAULT_US_ENTRY_TIER
from execution.models import Side
from execution.paper_engine import PaperExecutionConfig, PaperExecutionEngine
from market_data.models import ProductSpec
from market_data.spread_monitor import SpreadMonitor
from market_data.websocket_feed import CoinbaseMarketDataFeed, FeedEvent, replay_file
from paper_trading.account import PaperAccount
from paper_trading.diagnostics import Diagnostics, run_rest_checks
from paper_trading.recorder import TradeRecorder

log = logging.getLogger("paper_trading")

# Used only when the product endpoint is unreachable (e.g. offline replay). Labelled as such.
FALLBACK_BTC_USD = ProductSpec("BTC-USD", "BTC", "USD", Decimal("0.00000001"), Decimal("0.01"),
                               Decimal("0.01"), Decimal("0.00000001"), Decimal("3400"), Decimal("1"),
                               status="FALLBACK (not fetched from Coinbase)")


class StartupRefused(RuntimeError):
    pass


def check_key_permissions(perms: dict, settings: Settings) -> list[str]:
    """Refuse keys that can move funds; refuse trade-scoped keys unless explicitly allowed."""
    notes = []
    if perms.get("can_transfer"):
        raise StartupRefused("API key has TRANSFER permission. Create a View-only key for paper trading.")
    if perms.get("can_trade"):
        if not settings.allow_trade_scoped_key:
            raise StartupRefused("API key has TRADE permission. Use a View-only key "
                                 "(or set ALLOW_TRADE_SCOPED_KEY=true to accept it; orders remain impossible).")
        notes.append("WARNING: key is trade-scoped; order endpoints are still blocked by the transport allowlist.")
    return notes


class DemoRoundTrip:
    """Scripted smoke test of the execution paths. Not a strategy."""

    def __init__(self, engine: PaperExecutionEngine, notional: Decimal = Decimal(250), hold_s: float = 5.0,
                 maker_ttl_s: float = 20.0):
        self.e, self.notional, self.hold_s, self.maker_ttl_s = engine, notional, hold_s, maker_ttl_s
        self.phase, self.order, self.t_filled = "start", None, None

    def step(self, now: datetime) -> None:
        e, book = self.e, self.e._book
        if book is None or not book.ready:
            return
        if self.phase == "start":
            bid = book.best_bid()[0]
            self.order = e.submit_post_only_limit(Side.BUY, self.notional / bid, bid, now=now,
                                                  signal="DEMO maker entry (not a strategy)", ttl_s=self.maker_ttl_s)
            self.phase = "maker_wait"
        elif self.phase == "maker_wait" and self.order.status.terminal:
            if self.order.filled_base > 0:
                self.t_filled, self.phase = now, "maker_hold"
            else:
                self.order = e.submit_market(Side.BUY, quote_size=self.notional, now=now,
                                             signal="DEMO taker entry after unfilled maker (not a strategy)")
                self.phase = "taker_wait"
        elif self.phase == "taker_wait" and self.order.status.terminal:
            self.t_filled, self.phase = now, "maker_hold" if self.order.filled_base > 0 else "done"
        elif self.phase == "maker_hold" and (now - self.t_filled).total_seconds() >= self.hold_s:
            if e.account.available_base > 0:
                self.order = e.submit_market(Side.SELL, base_size=e.account.available_base, now=now,
                                             signal="DEMO taker exit (not a strategy)")
            self.phase = "exit_wait"
        elif self.phase == "exit_wait" and self.order.status.terminal:
            self.phase = "done"


def handle_event(ev: FeedEvent, engine, monitor, demo, stats) -> None:
    stats[ev.kind] = stats.get(ev.kind, 0) + 1
    if ev.kind == "book" and ev.time:
        engine.on_book(ev.payload, ev.time)
        monitor.sample(ev.payload, ev.time)
        if demo:
            demo.step(ev.time)
    elif ev.kind == "trade":
        engine.on_trade(ev.payload, ev.payload.time)
        if demo:
            demo.step(ev.payload.time)


class Session:
    """Wires market data -> paper engine; prints the diagnostic block once market data status is known."""

    def __init__(self, diag: Diagnostics, engine, monitor, demo):
        self.diag, self.engine, self.monitor, self.demo = diag, engine, monitor, demo
        self.stats: dict = {}
        self.printed = False
        self.last_book = None

    def print_diagnostics(self) -> None:
        if not self.printed:
            print("\n".join(self.diag.lines()), flush=True)
            self.printed = True

    def on_event(self, ev: FeedEvent) -> None:
        handle_event(ev, self.engine, self.monitor, self.demo, self.stats)
        if ev.kind == "book" and ev.payload.ready and not ev.payload.is_crossed():
            self.last_book = ev.payload
            if not self.diag.market_data:
                self.diag.market_data = True
                self.print_diagnostics()

    async def run_live(self, feed: CoinbaseMarketDataFeed, duration: float) -> None:
        async for ev in feed.stream(stop_after=duration):
            self.on_event(ev)

    def run_replay(self, events: Iterable[FeedEvent]) -> None:
        for ev in events:
            self.on_event(ev)


def _fmt(x, places=2):
    return "n/a" if x is None else f"{x:,.{places}f}"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="paper_trading", description="Coinbase BTC-USD paper trading (no live orders)")
    ap.add_argument("--duration", type=float, default=60.0, help="live session length in seconds")
    ap.add_argument("--replay", help="replay recorded WebSocket messages (JSONL) instead of connecting (offline)")
    ap.add_argument("--demo-roundtrip", action="store_true", help="scripted execution smoke test (not a strategy)")
    ap.add_argument("--start-usd", type=Decimal, default=Decimal(500))
    ap.add_argument("--latency-ms", type=int, default=250)
    ap.add_argument("--extra-slippage-bps", type=Decimal, default=Decimal(0))
    ap.add_argument("--show-balances", action="store_true", help="print your real USD/BTC available balances locally")
    ap.add_argument("--verbose", action="store_true", help="INFO-level logs (secrets are always redacted)")
    ap.add_argument("--records-dir", default=str(REPO_ROOT / "paper_trading" / "records"))
    args = ap.parse_args(argv)

    # HARD SAFETY ASSERTION: nothing else runs unless PAPER_MODE == true.
    try:
        settings = load_settings()
    except PaperModeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    assert settings.paper_mode is True
    setup_logging(logging.INFO if args.verbose else logging.WARNING)

    transport = ReadOnlyTransport(settings.credentials)
    client = CoinbaseAdvancedClient(transport=transport)
    diag = run_rest_checks(client, settings.has_credentials, settings.product_id, offline=bool(args.replay))

    refusal = None
    if diag.permissions is not None:
        try:
            for note in check_key_permissions(diag.permissions, settings):
                log.warning(note)
        except StartupRefused as exc:
            refusal = str(exc)
    if refusal:
        print("\n".join(diag.lines()))
        print(f"STARTUP REFUSED: {refusal}", file=sys.stderr)
        return 3

    fees = diag.fee_schedule or DEFAULT_US_ENTRY_TIER
    product = diag.product_spec or FALLBACK_BTC_USD
    engine = PaperExecutionEngine(product, fees, PaperAccount(usd=args.start_usd),
                                  PaperExecutionConfig(latency_ms=args.latency_ms,
                                                       taker_extra_slippage_bps=args.extra_slippage_bps))
    recorder, monitor = TradeRecorder(), SpreadMonitor()
    engine.on_fill(recorder.on_fill)
    engine.on_order_closed(recorder.on_order_closed)
    demo = DemoRoundTrip(engine) if args.demo_roundtrip else None
    session = Session(diag, engine, monitor, demo)

    feed = None
    error = None
    try:
        if args.replay:
            session.run_replay(replay_file(args.replay, settings.product_id))
        else:
            feed = CoinbaseMarketDataFeed(settings.product_id, max_retries=2)
            asyncio.run(session.run_live(feed, args.duration))
    except Exception as exc:  # report, don't crash
        error = f"{type(exc).__name__}: {exc}"
        log.error("market-data session ended with error: %s", error)
    session.print_diagnostics()   # prints with Market data stream: FAIL if no book ever arrived
    messages = feed.state.messages if feed else sum(session.stats.values())

    # ---- report ---------------------------------------------------------------------------
    book = session.last_book
    bid = book.best_bid()[0] if book else None
    ask = book.best_ask()[0] if book else None
    spread_usd = (ask - bid) if book else None
    spread_bps = book.spread_bps() if book else None
    report = {
        "authentication": "SUCCESS" if diag.authenticated else "FAIL",
        "market_data_received": "YES" if diag.market_data else "NO",
        "bid": _fmt(bid), "ask": _fmt(ask), "spread_usd": _fmt(spread_usd), "spread_bps": _fmt(spread_bps, 4),
        "fee_info": ({"maker": str(fees.maker_rate), "taker": str(fees.taker_rate), "tier": diag.pricing_tier,
                      "source": "Coinbase /transaction_summary"} if diag.fees else
                     {"maker": str(fees.maker_rate), "taker": str(fees.taker_rate),
                      "source": "NOT RETURNED BY COINBASE - using " + fees.source}),
        "account_data_read": "YES" if diag.account else "NO",
        "market_data_messages": messages,
        "paper_orders": len(recorder.orders),
        "simulated_trades": len(recorder.trades),
        "order_endpoint_called": "YES" if transport.order_endpoint_called else "NO",
        "rest_requests": len(transport.request_log),
        "refused_requests": sum(1 for _m, _p, ok in transport.request_log if not ok),
    }
    print("\n--- SESSION REPORT (paper mode; no orders placed) ---")
    for k, v in report.items():
        print(f"{k}: {v}")
    if args.show_balances and diag.accounts is not None:
        for cur, amt in summarize_balances(diag.accounts).items():
            print(f"available {cur}: {amt}")   # local terminal only; never written to disk

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.records_dir) / run_id
    recorder.write(out)
    monitor.to_csv(out / "spreads.csv")
    summary = {
        "run_id": run_id, "source": f"replay:{args.replay}" if args.replay else "live:" + WS_MARKET_DATA_URL,
        "diagnostics": diag.lines(), "diagnostic_errors": diag.errors, "report": report,
        "product": product.product_id, "product_status": product.status, "events": session.stats,
        "spread": monitor.summary(), "paper_account": {"usd": str(engine.account.usd), "btc": str(engine.account.base)},
        "error": error,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"records: {out}")
    return 0 if (error is None and diag.market_data) else 1
