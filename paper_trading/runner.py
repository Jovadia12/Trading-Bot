"""Paper-trading session runner: Coinbase market data -> paper execution -> records.

Usage (from repo root):
    PAPER_MODE=true python -m paper_trading --duration 120
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
from exchange.errors import ExchangeAPIError
from execution.fees import DEFAULT_US_ENTRY_TIER, FeeSchedule
from execution.models import OrderStatus, Side
from execution.paper_engine import PaperExecutionConfig, PaperExecutionEngine
from market_data.models import ProductSpec
from market_data.spread_monitor import SpreadMonitor
from market_data.websocket_feed import CoinbaseMarketDataFeed, FeedEvent, replay_file
from paper_trading.account import PaperAccount
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


def build_session(settings: Settings, replay: bool):
    client = CoinbaseAdvancedClient(settings.credentials)
    notes: list[str] = []
    fees, product = DEFAULT_US_ENTRY_TIER, None
    if settings.has_credentials and not replay:
        check_key_permissions(client.get_key_permissions(), settings)  # raises StartupRefused
        try:
            fees = FeeSchedule.from_account(client.get_fee_rates())
        except (ExchangeAPIError, KeyError) as exc:
            notes.append(f"fee tier unavailable ({type(exc).__name__}); using {fees.source}")
        try:
            bal = summarize_balances(client.get_accounts())
            notes.append(f"real account balances (read-only, not used for paper): "
                         + ", ".join(f"{k}={v}" for k, v in bal.items()))
        except ExchangeAPIError as exc:
            notes.append(f"accounts unavailable: {exc}")
    elif not settings.has_credentials:
        notes.append("no API credentials: public market data only; fee tier = configured default")
    if not replay:
        try:
            product = client.get_product(settings.product_id)
        except ExchangeAPIError as exc:
            notes.append(f"product fetch failed: {exc}")
    if product is None:
        product = FALLBACK_BTC_USD
        notes.append("using FALLBACK BTC-USD product spec (not fetched from Coinbase)")
    return client, product, fees, notes


def run(events: Iterable[FeedEvent] | None, engine: PaperExecutionEngine, monitor: SpreadMonitor,
        demo: Optional[DemoRoundTrip], stats: dict) -> None:
    for ev in events:
        handle_event(ev, engine, monitor, demo, stats)


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


async def run_live(feed: CoinbaseMarketDataFeed, duration: float, engine, monitor, demo, stats) -> None:
    async for ev in feed.stream(stop_after=duration):
        handle_event(ev, engine, monitor, demo, stats)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="paper_trading", description="Coinbase BTC-USD paper trading (no live orders)")
    ap.add_argument("--duration", type=float, default=60.0, help="live session length in seconds")
    ap.add_argument("--replay", help="replay recorded WebSocket messages (JSONL) instead of connecting")
    ap.add_argument("--demo-roundtrip", action="store_true", help="scripted execution smoke test (not a strategy)")
    ap.add_argument("--start-usd", type=Decimal, default=Decimal(500))
    ap.add_argument("--latency-ms", type=int, default=250)
    ap.add_argument("--extra-slippage-bps", type=Decimal, default=Decimal(0))
    ap.add_argument("--records-dir", default=str(REPO_ROOT / "paper_trading" / "records"))
    args = ap.parse_args(argv)

    try:
        settings = load_settings()
    except PaperModeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    setup_logging()
    log.info("PAPER MODE: live order execution is disabled in this build.")
    try:
        _client, product, fees, notes = build_session(settings, replay=bool(args.replay))
    except StartupRefused as exc:
        log.error("startup refused: %s", exc)
        return 3
    for n in notes:
        log.info(n)
    log.info("fees: maker=%s taker=%s source=%s", fees.maker_rate, fees.taker_rate, fees.source)

    engine = PaperExecutionEngine(product, fees, PaperAccount(usd=args.start_usd),
                                  PaperExecutionConfig(latency_ms=args.latency_ms,
                                                       taker_extra_slippage_bps=args.extra_slippage_bps))
    recorder, monitor = TradeRecorder(), SpreadMonitor()
    engine.on_fill(recorder.on_fill)
    engine.on_order_closed(recorder.on_order_closed)
    demo = DemoRoundTrip(engine) if args.demo_roundtrip else None
    stats: dict = {}
    source = f"replay:{args.replay}" if args.replay else "live:wss://advanced-trade-ws.coinbase.com"
    error = None
    try:
        if args.replay:
            run(replay_file(args.replay, settings.product_id), engine, monitor, demo, stats)
        else:
            feed = CoinbaseMarketDataFeed(settings.product_id, max_retries=2)
            asyncio.run(run_live(feed, args.duration, engine, monitor, demo, stats))
    except Exception as exc:  # report, don't crash silently
        error = f"{type(exc).__name__}: {exc}"
        log.error("market-data session ended with error: %s", error)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.records_dir) / run_id
    paths = recorder.write(out)
    monitor.to_csv(out / "spreads.csv")
    summary = {
        "run_id": run_id, "source": source, "product": product.product_id, "product_status": product.status,
        "fees": {"maker": str(fees.maker_rate), "taker": str(fees.taker_rate), "source": fees.source},
        "events": stats, "spread": monitor.summary(), "orders": len(recorder.orders),
        "round_trips": len(recorder.trades),
        "account": {"usd": str(engine.account.usd), "btc": str(engine.account.base)},
        "error": error, "notes": notes,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    print(f"records written to {out}")
    return 0 if error is None else 1
