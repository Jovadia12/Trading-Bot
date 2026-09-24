from decimal import Decimal

from backtest.candle_fill_model import maker_fills_on_bar, min_gross_move_required, round_trip_cost_fraction
from market_data.spread_monitor import SpreadMonitor
from tests.conftest import at, make_book


def test_spread_monitor_measures_spread_and_taker_cost():
    m = SpreadMonitor(min_interval_s=0)
    book = make_book([(99.99, 10)], [(100.01, 1), (100.05, 10)])
    s = m.sample(book, at(0))
    assert s.spread_bps == Decimal(2)
    assert s.taker_cost_bps["buy_250"] > Decimal(1)       # more than half-spread: walks to 2nd level
    assert abs(s.taker_cost_bps["sell_250"] - Decimal(1)) < Decimal("1e-9")
    summ = m.summary()
    assert summ["samples"] == 1 and summ["spread_bps_median"] == 2.0


def test_candle_maker_fill_is_strict():
    assert maker_fills_on_bar("BUY", Decimal(100), Decimal("99.99"), Decimal(101))
    assert not maker_fills_on_bar("BUY", Decimal(100), Decimal(100), Decimal(101))   # touch is not a fill
    assert maker_fills_on_bar("SELL", Decimal(100), Decimal(99), Decimal("100.01"))


def test_round_trip_costs():
    mk, tk = Decimal("0.005"), Decimal("0.009")
    assert round_trip_cost_fraction("MAKER", "MAKER", mk, tk) == Decimal("0.010")
    assert round_trip_cost_fraction("MAKER", "TAKER", mk, tk, Decimal("0.0005")) == Decimal("0.0145")
    assert round_trip_cost_fraction("TAKER", "TAKER", mk, tk, Decimal("0.0005")) == Decimal("0.019")
    assert min_gross_move_required(Decimal("0.0025"), Decimal("1.5")) == Decimal("0.00375")
