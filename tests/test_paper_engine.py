from decimal import Decimal

import pytest

from execution.fees import FeeSchedule
from execution.models import Liquidity, OrderStatus, Side
from execution.paper_engine import PaperExecutionConfig, PaperExecutionEngine
from paper_trading.account import PaperAccount
from paper_trading.recorder import TradeRecorder
from risk.limits import RiskLimits
from tests.conftest import at, make_book, trade

FEES = FeeSchedule(Decimal("0.004"), Decimal("0.006"), "test")


def engine(product, usd=500, risk=None, **cfg):
    return PaperExecutionEngine(product, FEES, PaperAccount(usd=Decimal(usd)), PaperExecutionConfig(**cfg), risk=risk)


BOOK = lambda: make_book([(64000, 0.5), (63999, 1)], [(64001, 0.001), (64002, 1)])


def test_taker_buy_walks_book_charges_taker_fee_and_records_costs(product):
    e = engine(product)
    e.on_book(BOOK(), at(0))
    o = e.submit_market(Side.BUY, quote_size=Decimal(250), now=at(0), signal="t")
    assert o.status is OrderStatus.PENDING          # latency window
    e.on_book(BOOK(), at(0.3))
    assert o.status is OrderStatus.FILLED
    f = e.fills[0]
    assert f.liquidity is Liquidity.TAKER and f.price > Decimal(64001)   # swept past a thin touch
    assert f.fee == f.notional * Decimal("0.006")
    assert f.spread_cost > 0 and f.slippage > 0                          # half-spread + depth impact
    assert e.account.usd == Decimal(500) - f.notional - f.fee
    assert e.account.held_usd == 0


def test_latency_uses_book_at_activation_not_submission(product):
    e = engine(product, latency_ms=1000)
    e.on_book(BOOK(), at(0))
    o = e.submit_market(Side.BUY, quote_size=Decimal(100), now=at(0), signal="t")
    e.on_book(BOOK(), at(0.5))
    assert o.status is OrderStatus.PENDING
    moved = make_book([(64100, 1)], [(64101, 1)])
    e.on_book(moved, at(1.0))
    assert o.status is OrderStatus.FILLED and e.fills[0].price == Decimal(64101)
    assert e.fills[0].slippage > 0     # adverse drift during latency is slippage


def test_configurable_extra_slippage(product):
    e = engine(product, taker_extra_slippage_bps=Decimal(10))
    e.on_book(BOOK(), at(0))
    e.submit_market(Side.BUY, base_size=Decimal("0.001"), now=at(0), signal="t")
    e.on_book(BOOK(), at(1))
    assert e.fills[0].price == Decimal(64001) * Decimal("1.001")


def test_partial_fill_on_thin_book_cancels_remainder(product):
    e = engine(product, usd=100000, risk=RiskLimits(max_order_notional_usd=Decimal(10000)))
    thin = make_book([(64000, 1)], [(64001, 0.01)])
    e.on_book(thin, at(0))
    o = e.submit_market(Side.BUY, base_size=Decimal("0.05"), now=at(0), signal="t")
    e.on_book(thin, at(1))
    assert o.status is OrderStatus.CANCELLED and o.filled_base == Decimal("0.01")
    assert "remainder cancelled" in o.reason
    assert e.account.held_usd == 0


def test_maker_entry_fills_on_trade_through_and_charges_maker_fee(product):
    e = engine(product)
    e.on_book(BOOK(), at(0))
    o = e.submit_post_only_limit(Side.BUY, Decimal("0.003"), Decimal(64000), now=at(0), signal="m")
    e.on_book(BOOK(), at(0.3))
    assert o.status is OrderStatus.OPEN
    e.on_trade(trade(64000.5, 1, at(1)), at(1))    # above our bid: nothing
    assert o.filled_base == 0
    e.on_trade(trade(63999, 0.01, at(2)), at(2))   # through our level -> fully filled
    assert o.status is OrderStatus.FILLED
    f = e.fills[0]
    assert f.liquidity is Liquidity.MAKER and f.price == Decimal(64000) and f.fee == f.notional * Decimal("0.004")
    assert f.slippage == 0 and f.spread_cost < 0     # earned half-spread vs submit mid


def test_maker_queue_model_partial_fills(product):
    e = engine(product)
    e.on_book(BOOK(), at(0))                            # 0.5 BTC displayed at 64000 -> we are behind it
    o = e.submit_post_only_limit(Side.BUY, Decimal("0.004"), Decimal(64000), now=at(0), signal="m")
    e.on_book(BOOK(), at(0.3))
    assert o.queue_ahead == Decimal("0.5")
    e.on_trade(trade(64000, 0.4, at(1)), at(1))       # consumes queue only
    assert o.filled_base == 0 and o.queue_ahead == Decimal("0.1")
    e.on_trade(trade(64000, 0.102, at(2)), at(2))     # 0.1 queue + 0.002 to us
    assert o.filled_base == Decimal("0.002") and not o.status.terminal
    e.on_trade(trade(64000, 1, at(3)), at(3))
    assert o.status is OrderStatus.FILLED and len(e.fills) == 2


def test_strict_model_ignores_at_price_trades(product):
    e = engine(product, maker_fill_model="trade_through_only")
    e.on_book(BOOK(), at(0))
    o = e.submit_post_only_limit(Side.BUY, Decimal("0.003"), Decimal(64000), now=at(0), signal="m")
    e.on_book(BOOK(), at(0.3))
    e.on_trade(trade(64000, 5, at(1)), at(1))
    assert o.filled_base == 0


def test_post_only_that_would_take_is_rejected(product):
    e = engine(product)
    e.on_book(BOOK(), at(0))
    o = e.submit_post_only_limit(Side.BUY, Decimal("0.003"), Decimal(64001), now=at(0), signal="m")
    e.on_book(BOOK(), at(0.3))
    assert o.status is OrderStatus.REJECTED and "would take" in o.reason
    assert e.account.held_usd == 0 and e.fills == []


def test_unfilled_maker_expires_and_releases_hold(product):
    e = engine(product)
    e.on_book(BOOK(), at(0))
    o = e.submit_post_only_limit(Side.BUY, Decimal("0.003"), Decimal(63990), now=at(0), signal="m", ttl_s=5)
    assert e.account.held_usd > 0
    e.on_book(BOOK(), at(6))
    assert o.status is OrderStatus.EXPIRED and "unfilled" in o.reason and e.account.held_usd == 0


def test_cancel_releases_hold(product):
    e = engine(product)
    e.on_book(BOOK(), at(0))
    o = e.submit_post_only_limit(Side.BUY, Decimal("0.003"), Decimal(63990), now=at(0), signal="m")
    e.cancel(o.order_id, at(1))
    assert o.status is OrderStatus.CANCELLED and e.account.held_usd == 0


def test_insufficient_balance_rejected(product):
    e = engine(product, usd=100)
    e.on_book(BOOK(), at(0))
    o = e.submit_market(Side.BUY, quote_size=Decimal(150), now=at(0), signal="t")
    assert o.status is OrderStatus.REJECTED and "insufficient USD" in o.reason
    s = e.submit_market(Side.SELL, base_size=Decimal("0.001"), now=at(0), signal="t")
    assert s.status is OrderStatus.REJECTED   # holds no BTC (long-only / insufficient BTC)


def test_minimum_order_size_rejected(product):
    e = engine(product)
    e.on_book(BOOK(), at(0))
    o = e.submit_market(Side.BUY, quote_size=Decimal("0.50"), now=at(0), signal="t")
    assert o.status is OrderStatus.REJECTED and "minimum" in o.reason
    o2 = e.submit_post_only_limit(Side.BUY, Decimal("0.000001"), Decimal(64000), now=at(0), signal="m")
    assert o2.status is OrderStatus.REJECTED and "base_min_size" in o2.reason


def test_maker_exit_and_round_trip_record(product):
    e = engine(product)
    rec = TradeRecorder()
    e.on_fill(rec.on_fill)
    e.on_book(BOOK(), at(0))
    e.submit_post_only_limit(Side.BUY, Decimal("0.003"), Decimal(64000), now=at(0), signal="ENTRY sig")
    e.on_book(BOOK(), at(0.3))
    e.on_trade(trade(63999, 1, at(1)), at(1))
    x = e.submit_post_only_limit(Side.SELL, Decimal("0.003"), Decimal(64010), now=at(10), signal="EXIT sig")
    e.on_book(BOOK(), at(10.3))
    assert x.status is OrderStatus.OPEN
    e.on_trade(trade(64011, 1, at(3600)), at(3600))
    assert x.status is OrderStatus.FILLED
    t = rec.trades[0]
    assert t.execution_type == "MAKER/MAKER" and t.side == "LONG"
    assert t.entry_price == Decimal(64000) and t.exit_price == Decimal(64010) and t.quantity == Decimal("0.003")
    assert t.gross_pnl == Decimal(10) * Decimal("0.003")
    assert t.fees == Decimal("0.003") * (Decimal(64000) + Decimal(64010)) * Decimal("0.004")
    assert t.net_pnl == t.gross_pnl - t.fees
    assert t.holding_seconds == 3599 and t.entry_signal == "ENTRY sig" and t.exit_signal == "EXIT sig"


def test_risk_limit_blocks_oversized_order(product):
    e = engine(product, usd=100000)
    e.on_book(BOOK(), at(0))
    o = e.submit_market(Side.BUY, quote_size=Decimal(1000), now=at(0), signal="t")
    assert o.status is OrderStatus.REJECTED and "exceeds limit" in o.reason
