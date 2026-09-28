"""Version A paper strategy: indicators, rules, sizing, stop, accounting, aggregation, warm-up, CLI."""
import ast
import asyncio
import base64
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import requests
import websockets
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from execution.fees import FeeSchedule
from execution.models import OrderStatus
from execution.paper_engine import PaperExecutionConfig, PaperExecutionEngine
from market_data.candle_aggregator import FOUR_HOURS, CandleAggregator, aggregate, bucket_start
from market_data.models import Candle, MarketTrade
from paper_trading.account import PaperAccount
from paper_trading.recorder import TradeRecorder
from paper_trading.strategy_session import StrategyTrader, fetch_warmup
from risk.limits import RiskLimits
from strategy.indicators import atr_wilder, true_ranges
from strategy.version_a import VersionA, VersionAParams, breakout, size_position
from tests.conftest import make_book

D = Decimal
REPO = Path(__file__).resolve().parent.parent
B = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)      # a 4H boundary
H4 = timedelta(hours=4)


def cndl(start, o, h, l, c, v=1):
    return Candle(start, D(str(o)), D(str(h)), D(str(l)), D(str(c)), D(str(v)))


def flat_history(n=30, end=B, high=60100, low=59900, close=60000):
    return [cndl(end - (n - i) * H4, close, high, low, close) for i in range(n)]


# ---- breakout ------------------------------------------------------------------------------------

def test_breakout_uses_previous_20_highs_only():
    prev = flat_history(25)
    prev[0] = cndl(prev[0].start, 60000, 99999, 59900, 60000)       # 25 candles ago: outside the window
    assert breakout(prev, cndl(B, 60000, 60200, 59950, 60101)) == D(60100)
    assert breakout(prev, cndl(B, 60000, 60200, 59950, 60100)) is None        # equal is not a break
    assert breakout(prev, cndl(B, 60000, 99999, 59950, 60050)) is None        # own high irrelevant; close counts
    prev[-1] = cndl(prev[-1].start, 60000, 60300, 59900, 60000)      # inside the window
    assert breakout(prev, cndl(B, 60000, 60400, 59950, 60200)) is None
    assert breakout(prev[:19], cndl(B, 60000, 70000, 59950, 70000)) is None   # < 20 previous candles


def test_strategy_signal_needs_history_and_carries_stop():
    s = VersionA()
    assert s.on_candle_close(cndl(B, 1, 2, 1, 2)) is None            # no history yet
    s = VersionA()
    s.warm_up(flat_history(30))
    sig = s.on_candle_close(cndl(B, 60000, 60500, 60000, 60500))
    assert sig.action == "ENTER_LONG" and sig.reference_price == D(60100)
    assert sig.stop_distance == D("1.5") * sig.atr
    assert s.on_candle_close(cndl(B + H4, 60500, 60500, 60400, 60450)) is None
    with pytest.raises(ValueError):
        s.on_candle_close(cndl(B, 1, 1, 1, 1))                      # out-of-order candle


# ---- ATR -----------------------------------------------------------------------------------------

def test_true_range_and_wilder_atr_by_hand():
    cs = [cndl(B + i * H4, *x) for i, x in enumerate([
        (10, 11, 9, 10),     # first candle: only a previous close
        (10, 12, 10, 11),    # TR = 2
        (11, 11, 8, 9),      # TR = 3
        (9, 14, 9, 13),      # TR = max(5, 5, 0) = 5
        (13, 13, 12, 12),    # TR = 1
        (12, 20, 12, 19)])]  # TR = max(8, 8, 0) = 8
    assert true_ranges(cs) == [D(2), D(3), D(5), D(1), D(8)]
    atr = atr_wilder(cs, period=3)             # seed (2+3+5)/3 = 10/3 ; then (10/3*2+1)/3 ; then (..*2+8)/3
    seed = D(10) / 3
    step1 = (seed * 2 + 1) / 3
    assert atr == (step1 * 2 + 8) / 3
    with pytest.raises(ValueError):
        atr_wilder(cs[:3], period=3)


def test_atr_gap_uses_previous_close():
    cs = [cndl(B, 100, 101, 99, 100), cndl(B + H4, 120, 121, 119, 120)]
    assert true_ranges(cs) == [D(21)]


# ---- sizing --------------------------------------------------------------------------------------

def test_position_size_risks_half_percent_of_equity():
    d = size_position(D(1000), stop_distance=D(300), price=D(30000), available_usd=D(1000),
                      taker_fee_rate=D("0.006"), base_increment=D("0.00000001"))   # ~$500 notional fits
    assert d.risk_usd == D(5) and not d.cash_capped
    assert d.base == D("0.01666666")                     # 5/300 rounded DOWN to 1e-8
    assert d.base * D(300) <= D(5)


def test_position_size_never_exceeds_available_cash():
    d = size_position(D(1000), stop_distance=D(10), price=D(60000), available_usd=D(400),
                      taker_fee_rate=D("0.006"), base_increment=D("0.00000001"))
    assert d.cash_capped and d.base < d.risk_based_base
    assert d.base * D(60000) * D("1.006") <= D(400)
    assert size_position(D(1000), D(10), D(60000), D(-5), D("0.006"), D("0.00000001")).base == 0


# ---- aggregator ----------------------------------------------------------------------------------

def tr(t, price, size="0.01", tid=None):
    return MarketTrade("BTC-USD", t, D(str(price)), D(size), "BUY", tid)


def test_aggregator_emits_exactly_one_candle_per_boundary():
    agg = CandleAggregator()
    agg.seed(cndl(B, 100, 100, 100, 100, 0), as_of=B)
    closed = []
    for k in range(3):                                   # three buckets of trades
        for m in range(0, 240, 30):
            closed += agg.on_trade(tr(B + k * H4 + timedelta(minutes=m), 100 + k, tid=f"{k}-{m}"))
    closed += agg.on_trade(tr(B + 3 * H4 + timedelta(seconds=1), 200, tid="x"))
    closed += agg.on_time(B + 3 * H4 + timedelta(minutes=5))          # clock tick: nothing new to close
    assert [c.candle.start for c in closed] == [B, B + H4, B + 2 * H4]
    assert closed[1].candle.open == D(101) and closed[1].candle.close == D(101) and all(c.complete for c in closed)
    assert len(set(agg.emitted)) == len(agg.emitted)


def test_aggregator_closes_quiet_candle_by_clock_once_and_fills_gaps():
    agg = CandleAggregator(grace_s=2)
    agg.seed(cndl(B, 100, 110, 90, 105, 1), as_of=B)
    assert agg.on_time(B + H4) == []                                  # within grace
    first = agg.on_time(B + H4 + timedelta(seconds=3))
    assert [c.candle.start for c in first] == [B] and first[0].candle.high == D(110)
    assert agg.on_time(B + H4 + timedelta(seconds=10)) == []           # never twice
    later = agg.on_trade(tr(B + 3 * H4 + timedelta(minutes=1), 120, tid="t"))   # two empty buckets passed
    assert [c.candle.start for c in later] == [B + H4, B + 2 * H4]
    assert all(c.candle.volume == 0 and c.candle.close == D(105) for c in later)


def test_aggregator_ignores_duplicates_late_and_pre_seed_trades():
    agg = CandleAggregator()
    agg.seed(cndl(B, 100, 100, 100, 100, 0), as_of=B + timedelta(minutes=10))
    agg.on_trade(tr(B + timedelta(minutes=5), 999, tid="old"))       # already inside the REST seed
    agg.on_trade(tr(B + timedelta(minutes=20), 101, tid="a"))
    agg.on_trade(tr(B + timedelta(minutes=21), 150, tid="a"))        # duplicate id
    out = agg.on_trade(tr(B + H4 + timedelta(seconds=1), 102, tid="b"))
    agg.on_trade(tr(B + timedelta(minutes=30), 1, tid="late"))        # belongs to a closed bucket
    assert out[0].candle.high == D(101) and agg.late_trades == 2


def test_unseeded_mid_bucket_start_is_marked_incomplete():
    agg = CandleAggregator()
    agg.on_trade(tr(B + timedelta(minutes=90), 100, tid="1"))
    out = agg.on_trade(tr(B + H4 + timedelta(seconds=1), 100, tid="2"))
    assert out[0].complete is False


# ---- warm-up -------------------------------------------------------------------------------------

class FakeCandleClient:
    """Returns 1H candles like Coinbase: newest first, INCLUDING the in-progress hour."""
    def __init__(self, now, missing=()):
        self.now, self.missing, self.calls = now, set(missing), []

    def get_candles(self, product_id, start, end, granularity):
        assert granularity == "1h" and (end - start) <= timedelta(hours=350)
        self.calls.append((start, end))
        t = start.replace(minute=0, second=0, microsecond=0)
        out = []
        while t <= min(end, self.now):
            if t not in self.missing:
                p = 60000 + (t.timestamp() // 3600) % 50
                out.append(cndl(t, p, p + 100, p - 100, p + 1))
            t += timedelta(hours=1)
        return list(reversed(out))


def test_warmup_excludes_the_forming_candle():
    now = B + timedelta(hours=2, minutes=17)                 # 2h17m into the 08:00 bucket
    client = FakeCandleClient(now)
    history, forming = fetch_warmup(client, "BTC-USD", now, n_candles=60)
    assert len(history) == 60 and history[-1].start == B - H4
    assert all(c.start + H4 <= B for c in history)
    assert forming.start == B                                 # returned separately, not in history
    assert all((b.start - a.start) == H4 for a, b in zip(history, history[1:]))
    assert len(client.calls) >= 1


def test_warmup_drops_buckets_with_missing_hours():
    now = B + timedelta(minutes=1)
    history, _ = fetch_warmup(FakeCandleClient(now, missing={B - 2 * H4 + timedelta(hours=1)}), "BTC-USD", now, 30)
    assert B - 2 * H4 not in [c.start for c in history]


def test_aggregate_boundary_exactly_at_now():
    cs = [cndl(B - H4 + timedelta(hours=i), 1, 2, 0, 1) for i in range(4)]
    completed, forming = aggregate(cs, FOUR_HOURS, 3600, now=B)
    assert [c.start for c in completed] == [B - H4] and forming is None


# ---- trader: entry, stop exit, fees and slippage -------------------------------------------------

FEES = FeeSchedule(D("0.004"), D("0.006"), "test: Coinbase-reported rates")


def make_trader(product, usd=1000, slippage_bps=0):
    eng = PaperExecutionEngine(product, FEES, PaperAccount(usd=D(usd)),
                               PaperExecutionConfig(latency_ms=250, taker_extra_slippage_bps=D(slippage_bps)),
                               risk=RiskLimits(max_order_notional_usd=D("1e12"), max_drawdown_fraction=None))
    rec = TradeRecorder()
    eng.on_fill(rec.on_fill)
    eng.on_order_closed(rec.on_order_closed)
    strat = VersionA()
    strat.warm_up(flat_history(30))
    agg = CandleAggregator()
    agg.set_last_close(D(60000))
    agg.seed(cndl(B, 60000, 60000, 60000, 60000, 0), as_of=B)
    return StrategyTrader(strat, eng, agg), eng, rec


def breakout_then_entry(trader, eng):
    book = make_book([(60500, 5), (60490, 5)], [(60501, 0.005), (60510, 5)])
    eng.on_book(book, B + timedelta(minutes=1))
    trader.on_trade(tr(B + timedelta(minutes=2), 60500, tid="b1"))            # breakout candle forms
    trader.on_trade(tr(B + H4 + timedelta(seconds=1), 60500, tid="b2"))       # closes it -> signal -> buy
    assert trader.entry_order is not None and trader.entry_order.status is OrderStatus.PENDING
    eng.on_book(book, B + H4 + timedelta(seconds=2))                          # after 250 ms latency
    return book


def test_breakout_entry_sizes_to_risk_and_arms_fixed_stop(product):
    trader, eng, rec = make_trader(product)
    breakout_then_entry(trader, eng)
    assert trader.in_position and trader.stop_price is not None
    sig_atr = (D(200) * 13 + D(500)) / 14                                     # Wilder step with TR=500
    entry = eng.fills[0]
    assert trader.stop_price == pytest.approx(entry.price - D("1.5") * sig_atr, abs=D("1e-9"))
    risk = eng.account.base * (entry.price - trader.stop_price)
    assert D("4.9") < risk <= D("5.0001")                                    # 0.5% of $1000 equity
    trader.on_trade(tr(B + H4 + timedelta(minutes=10), 60300, tid="n1"))     # above stop: hold
    assert trader.exit_order is None


def test_stop_exit_closes_whole_position_with_taker_fill(product):
    trader, eng, rec = make_trader(product)
    breakout_then_entry(trader, eng)
    stop = trader.stop_price
    trader.on_trade(tr(B + H4 + timedelta(hours=1), stop - 1, tid="s1"))
    assert trader.stats.stops_triggered == 1 and trader.exit_order.status is OrderStatus.PENDING
    eng.on_book(make_book([(stop - 5, 5)], [(stop + 5, 5)]), B + H4 + timedelta(hours=1, seconds=1))
    assert not trader.in_position and trader.stop_price is None
    t = rec.trades[0]
    assert t.execution_type == "TAKER/TAKER" and t.exit_price == stop - 5
    assert t.exit_signal.startswith("VersionA: 1.5 ATR stop")


def test_fee_and_slippage_accounting_is_exact(product):
    trader, eng, rec = make_trader(product, slippage_bps=5)
    breakout_then_entry(trader, eng)
    stop = trader.stop_price
    trader.on_trade(tr(B + H4 + timedelta(hours=1), stop - 1, tid="s1"))
    eng.on_book(make_book([(stop - 5, 5)], [(stop + 5, 5)]), B + H4 + timedelta(hours=1, seconds=1))
    buy, sell = eng.fills
    # entry swept 0.005 @ 60501 then the rest @ 60510 (depth), plus 5 bps configured slippage
    assert buy.price > D(60501) and buy.slippage > 0 and buy.spread_cost > 0
    assert buy.fee == buy.price * buy.base * D("0.006") and sell.fee == sell.price * sell.base * D("0.006")
    t = rec.trades[0]
    assert t.fees == buy.fee + sell.fee
    assert t.gross_pnl == (sell.price - buy.price) * buy.base and t.net_pnl == t.gross_pnl - t.fees
    assert eng.account.usd == D(1000) + t.net_pnl                            # cash reconciles exactly
    assert eng.account.usd > 0 and eng.account.base >= 0 and eng.account.held_usd == 0


def test_signal_ignored_while_in_position_and_no_pyramiding(product):
    trader, eng, rec = make_trader(product)
    book = breakout_then_entry(trader, eng)
    qty = eng.account.base
    trader.on_trade(tr(B + H4 + timedelta(minutes=30), 61000, tid="c1"))
    trader.on_trade(tr(B + 2 * H4 + timedelta(seconds=1), 61000, tid="c2"))   # another breakout close
    assert trader.stats.signals == 2 and trader.stats.signals_ignored_in_position == 1
    assert eng.account.base == qty and len(eng.fills) == 1


def test_no_market_data_means_no_entry(product):
    trader, eng, rec = make_trader(product)
    trader.on_trade(tr(B + timedelta(minutes=2), 60500, tid="b1"))
    trader.on_trade(tr(B + H4 + timedelta(seconds=1), 60500, tid="b2"))
    assert trader.stats.signals == 1 and trader.entry_order is None and eng.fills == []


# ---- safety --------------------------------------------------------------------------------------

def test_strategy_modules_cannot_reach_the_exchange():
    for mod in ("strategy/version_a.py", "strategy/indicators.py", "market_data/candle_aggregator.py"):
        tree = ast.parse((REPO / mod).read_text())
        names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | \
                {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any(m.startswith(("exchange", "requests", "websockets", "socket", "coinbase")) for m in names), mod
    tree = ast.parse((REPO / "paper_trading/strategy_session.py").read_text())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "exchange.client"
                for a in n.names}
    assert imported == {"ExchangeClient"}          # type only; the trader never calls the exchange
    src = (REPO / "paper_trading/strategy_session.py").read_text()
    assert "client." not in src.split("def fetch_warmup")[1].split("class StrategyStats")[1]


# ---- CLI: strategy mode end to end (mocked REST + local WebSocket) --------------------------------

def _fake_secret():
    sk = ed25519.Ed25519PrivateKey.generate()
    raw = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()) + \
        sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


class _R:
    def __init__(self, code, payload):
        self.status_code, self._p, self.text = code, payload, "{}"

    def json(self):
        return self._p


def _rest(fees_ok=True, candles_ok=True, calls=None):
    product = {"product_id": "BTC-USD", "base_increment": "0.00000001", "quote_increment": "0.01",
               "price_increment": "0.01", "base_min_size": "0.00000001", "base_max_size": "3400", "quote_min_size": "1"}

    def get(self, url, params=None, headers=None, timeout=None):
        path = url.replace("https://api.coinbase.com", "")
        if calls is not None:
            calls.append(path)
        if path.endswith("/key_permissions"):
            return _R(200, {"can_view": True, "can_trade": False, "can_transfer": False})
        if path.endswith("/transaction_summary"):
            return _R(200, {"fee_tier": {"pricing_tier": "Advanced 1", "maker_fee_rate": "0.004",
                                         "taker_fee_rate": "0.006"}}) if fees_ok else _R(500, {})
        if path.endswith("/accounts"):
            return _R(200, {"accounts": [], "has_next": False})
        if path.endswith("/products/BTC-USD"):
            return _R(200, product)
        if path.endswith("/candles"):
            if not candles_ok:
                return _R(200, {"candles": []})
            s, e = int(params["start"]), int(params["end"])
            t, out = s - s % 3600, []
            while t <= e:
                out.append({"start": str(t), "open": "60000", "high": "60100", "low": "59900",
                            "close": "60000", "volume": "5"})
                t += 3600
            return _R(200, {"candles": list(reversed(out))})
        return _R(404, {})
    return get


@pytest.fixture(scope="module")
def trade_ws_port():
    port, ready = [], threading.Event()

    async def handler(ws):
        n = 0
        await ws.send(json.dumps({"channel": "l2_data", "timestamp": "2026-09-28T00:00:00Z", "sequence_num": 0,
                                  "events": [{"type": "snapshot", "updates": [
                                      {"side": "bid", "price_level": "60000", "new_quantity": "5"},
                                      {"side": "offer", "price_level": "60001", "new_quantity": "5"}]}]}))
        try:
            await _stream_trades(ws)
        except websockets.exceptions.ConnectionClosed:
            return

    async def _stream_trades(ws):
        n = 0
        while True:
            n += 1
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            await ws.send(json.dumps({"channel": "market_trades", "timestamp": now, "sequence_num": n,
                                      "events": [{"type": "update", "trades": [{"trade_id": str(n), "product_id": "BTC-USD",
                                                  "price": "60000.5", "size": "0.001", "side": "BUY", "time": now}]}]}))
            await asyncio.sleep(0.02)

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        srv = loop.run_until_complete(websockets.serve(handler, "127.0.0.1", 0))
        port.append(srv.sockets[0].getsockname()[1])
        ready.set()
        loop.run_forever()
    threading.Thread(target=run, daemon=True).start()
    ready.wait(5)
    return port[0]


@pytest.fixture
def strategy_cli(monkeypatch, tmp_path, capsys, trade_ws_port):
    monkeypatch.setenv("COINBASE_API_KEY", "organizations/00000000-0000-0000-0000-000000000000/apiKeys/"
                                           "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv("COINBASE_API_SECRET", _fake_secret())
    import paper_trading.runner as runner
    monkeypatch.setattr(runner, "LIVE_WS_URL", f"ws://127.0.0.1:{trade_ws_port}")

    def go(*args, **rest_kw):
        calls = []
        monkeypatch.setattr(requests.Session, "get", _rest(calls=calls, **rest_kw))
        t0 = time.monotonic()
        rc = runner.main(["--records-dir", str(tmp_path), *args])
        out = capsys.readouterr()
        return rc, time.monotonic() - t0, out, calls
    return go


def test_cli_strategy_mode_runs_warms_up_and_reports(strategy_cli, tmp_path):
    rc, elapsed, out, calls = strategy_cli("--strategy", "version_a", "--duration", "2")
    assert rc == 0 and elapsed < 5
    assert "STRATEGY: version_a | warm-up 60 completed 4H candles" in out.out and "forming candle excluded" in out.out
    assert "paper start $1000" in out.out and "fees maker 0.004 taker 0.006 (Coinbase)" in out.out
    assert "strategy.warmup_candles: 60" in out.out and "order_endpoint_called: NO" in out.out
    assert "strategy.equity_usd: 1000.00" in out.out
    assert not any("/orders" in c for c in calls)
    assert list(tmp_path.rglob("candles_4h.csv")) and list(tmp_path.rglob("strategy_events.jsonl"))


def test_cli_start_usd_from_env_and_flag(strategy_cli, monkeypatch):
    monkeypatch.setenv("PAPER_START_USD", "2500")
    rc, _e, out, _c = strategy_cli("--strategy", "version_a", "--duration", "1")
    assert "paper start $2500" in out.out
    rc, _e, out, _c = strategy_cli("--strategy", "version_a", "--duration", "1", "--start-usd", "750")
    assert "paper start $750" in out.out


def test_cli_refuses_without_coinbase_fees(strategy_cli):
    rc, _e, out, _c = strategy_cli("--strategy", "version_a", "--duration", "1", fees_ok=False)
    assert rc == 4 and "STRATEGY MODE REFUSED" in out.err
    rc, _e, out, _c = strategy_cli("--strategy", "version_a", "--duration", "1", "--allow-default-fees", fees_ok=False)
    assert rc == 0 and "UNCONFIRMED default" in out.out


def test_cli_refuses_without_enough_warmup(strategy_cli):
    rc, _e, out, _c = strategy_cli("--strategy", "version_a", "--duration", "1", candles_ok=False)
    assert rc == 5 and "need 20" in out.err


def test_cli_strategy_still_requires_paper_mode(strategy_cli, monkeypatch):
    monkeypatch.setenv("PAPER_MODE", "false")
    rc, _e, out, calls = strategy_cli("--strategy", "version_a", "--duration", "1")
    assert rc == 2 and calls == []


def test_infra_mode_unchanged_default_500(strategy_cli):
    rc, _e, out, _c = strategy_cli("--duration", "1")
    assert rc == 0 and "STRATEGY:" not in out.out and "strategy." not in out.out
