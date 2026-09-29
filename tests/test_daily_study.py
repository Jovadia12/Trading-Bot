"""Daily study: families (no look-ahead), 2d/3d bars, taker/maker execution model, acceptance, pipeline."""
import numpy as np
import pandas as pd
import pytest

from backtest.costs import CostModel
from backtest.data import TF_SECONDS, resample
from backtest.engine import Signals, generate_trades, simulate_account
from backtest.exec_model import MakerRules, generate_trades_exec, simulate_exec
from backtest.strategies import build
from backtest.strategies_daily import DAILY_FAMILIES, DAILY_TIMEFRAMES
from tests.test_backtest_engine import random_walk

COSTS = CostModel("t")  # 0.50% maker / 0.90% taker defaults


def bars(rows, start="2024-01-01", freq="1D"):
    """rows = [(o, h, l, c), ...]"""
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame([dict(open=o, high=h, low=l, close=c, volume=1.0) for o, h, l, c in rows], index=idx)


def signals(n, entry_at=(), exit_at=(), stop=10.0, trail=None):
    e = np.zeros(n, bool); e[list(entry_at)] = True
    x = np.zeros(n, bool); x[list(exit_at)] = True
    return Signals(e, np.full(n, stop), None, x, trail_dist=trail)


# ---------------------------------------------------------------------------------------- families
@pytest.mark.parametrize("family", DAILY_FAMILIES, ids=lambda f: f.key)
def test_daily_family_uses_no_future_data(family):
    df = random_walk(1500, seed=7, freq="1D")
    cut = 1000
    fut = df.copy()
    fut.iloc[cut + 1:, :4] *= np.random.default_rng(4).uniform(0.5, 1.5, (len(df) - cut - 1, 1))
    fut["high"] = fut[["open", "high", "close"]].max(axis=1)
    fut["low"] = fut[["open", "low", "close"]].min(axis=1)
    for combo in family.combos():
        a, b = build(family, df, combo), build(family, fut, combo)
        assert (a.entry[:cut + 1] == b.entry[:cut + 1]).all(), (family.key, combo)
        assert np.allclose(a.stop_dist[:cut + 1], b.stop_dist[:cut + 1], equal_nan=True)
        if a.exit_sig is not None:
            assert (a.exit_sig[:cut + 1] == b.exit_sig[:cut + 1]).all()
        if a.trail_dist is not None:
            assert np.allclose(a.trail_dist[:cut + 1], b.trail_dist[:cut + 1], equal_nan=True)


@pytest.mark.parametrize("family", DAILY_FAMILIES, ids=lambda f: f.key)
def test_daily_family_trades_and_has_positive_stops(family):
    df = random_walk(2500, seed=13, freq="1D")
    for combo in family.combos():
        s = build(family, df, combo)
        assert np.all(s.stop_dist[s.entry] > 0), (family.key, combo)
    assert build(family, df, family.combos()[0]).entry.sum() > 0


def test_grid_is_small_and_preregistered():
    sizes = {f.key: len(f.combos()) for f in DAILY_FAMILIES}
    assert sizes == {"ema_trend": 8, "breakout": 16, "pullback": 8, "regime_trend": 12, "hybrid": 8}
    assert DAILY_TIMEFRAMES == ["1d", "2d", "3d"] and TF_SECONDS["2d"] == 2 * 86400 and TF_SECONDS["3d"] == 3 * 86400


def test_state_entries_fire_once_per_transition():
    from backtest.strategies_daily import _became_true
    assert _became_true(pd.Series([False, True, True, False, True])).tolist() == [False, True, False, False, True]


# ------------------------------------------------------------------------------------------ bars
def test_multi_day_bars_are_complete_and_epoch_anchored(monkeypatch):
    from backtest import daily_study as ds
    daily = random_walk(20, freq="1D")          # starts 2021-01-01 (epoch day 18628, even)
    monkeypatch.setattr(ds, "load_timeframe", lambda tf: daily)
    two, three = ds.load_bars("2d"), ds.load_bars("3d")
    assert all(((t - pd.Timestamp("1970-01-01", tz="UTC")).days % 2) == 0 for t in two.index)
    assert all(((t - pd.Timestamp("1970-01-01", tz="UTC")).days % 3) == 0 for t in three.index)
    first = two.index[0]
    src = daily.loc[first:first + pd.Timedelta(days=1)]
    assert two.high.iloc[0] == src.high.max() and two.open.iloc[0] == src.open.iloc[0] and two.close.iloc[0] == src.close.iloc[-1]
    # incomplete buckets at either edge are dropped (20 days, 3d buckets: partial ends removed)
    assert len(three) * 3 <= 20 and len(resample(daily, "3d")) >= len(three)


# ------------------------------------------------------------------------------ taker == old engine
def test_taker_mode_reproduces_existing_engine_exactly():
    df = random_walk(1500, seed=3, freq="1D")
    for fam in DAILY_FAMILIES:
        sig = build(fam, df, fam.combos()[0])
        old = simulate_account(df, generate_trades(df, sig), COSTS, start=10_000, risk=0.01)
        new = simulate_exec(df, generate_trades_exec(df, sig, mode="taker"), COSTS, start=10_000, risk=0.01)
        assert len(old.trades) == len(new.trades)
        if len(old.trades):
            assert np.allclose(old.trades.net, new.trades.net) and np.allclose(old.equity, new.equity)


# ----------------------------------------------------------------------------------- maker entries
def test_maker_entry_missed_when_price_does_not_trade_through_limit():
    # signal close 100; next bar low 99.95 only 0.05% below -> not through by 0.10% -> missed
    df = bars([(100, 101, 99, 100), (100, 103, 99.95, 102), (102, 104, 101, 103)])
    st = {}
    tr = generate_trades_exec(df, signals(3, entry_at=[0]), mode="maker", stats=st)
    assert tr == [] and st["missed_entries"] == 1 and st["entry_signals"] == 1


def test_maker_entry_touch_is_not_a_fill_but_trade_through_is():
    df = bars([(100, 101, 99, 100), (100, 103, 99.9, 102)])  # exactly 0.10% below: not strictly through
    assert generate_trades_exec(df, signals(2, entry_at=[0]), mode="maker") == []
    df2 = bars([(100, 101, 99, 100), (100, 103, 99.8, 102), (102, 104, 101, 103)])
    tr = generate_trades_exec(df2, signals(3, entry_at=[0]), mode="maker")
    assert len(tr) == 1 and tr[0].entry_ref == 100 and tr[0].entry_maker and tr[0].stop0 == 90


def test_maker_entry_fill_is_at_limit_even_if_bar_gaps_below():
    df = bars([(100, 101, 99, 100), (95, 96, 94, 95.5), (95.5, 97, 95, 96)])
    tr = generate_trades_exec(df, signals(3, entry_at=[0]), mode="maker")
    assert tr[0].entry_ref == 100          # the resting bid is filled at its limit, never better


def test_maker_stop_on_entry_bar_is_assumed_hit():
    df = bars([(100, 101, 99, 100), (100, 100.5, 85, 99), (99, 100, 98, 99)])
    tr = generate_trades_exec(df, signals(3, entry_at=[0], stop=10), mode="maker")
    assert tr[0].exit_type == "stop" and tr[0].exit_ref == 90 and tr[0].exit_i == 1 and not tr[0].exit_maker


def test_maker_signal_exit_filled_as_maker_when_high_trades_through():
    df = bars([(100, 101, 99, 100), (100, 106, 99.5, 105), (105, 106, 104, 105.5),
               (105.5, 106, 105, 105.8)])
    tr = generate_trades_exec(df, signals(4, entry_at=[0], exit_at=[1]), mode="maker")
    t = tr[0]
    assert t.exit_type == "signal_maker" and t.exit_maker and t.exit_ref == 105 and t.exit_i == 2


def test_maker_signal_exit_falls_back_to_taker_next_open():
    # exit signal at bar 1 (close 105); bar 2 high 105.05 < 105*1.001 -> unfilled -> taker at bar 3 open
    df = bars([(100, 101, 99, 100), (100, 106, 99.5, 105), (104, 105.05, 103, 104), (103, 104, 102, 103)])
    t = generate_trades_exec(df, signals(4, entry_at=[0], exit_at=[1]), mode="maker")[0]
    assert t.exit_type == "signal_taker_fallback" and not t.exit_maker and t.exit_i == 3 and t.exit_ref == 103


def test_maker_exit_bar_with_stop_inside_assumes_stop_first():
    df = bars([(100, 101, 99, 100), (100, 106, 99.5, 105), (105, 110, 80, 100), (100, 101, 99, 100)])
    t = generate_trades_exec(df, signals(4, entry_at=[0], exit_at=[1], stop=10), mode="maker")[0]
    assert t.exit_type == "stop" and t.exit_ref == 90 and t.exit_i == 2


def test_maker_trades_respect_window_and_close_at_window_end():
    df = bars([(100, 101, 99, 100)] + [(100, 101, 99.5, 100)] * 9)
    tr = generate_trades_exec(df, signals(10, entry_at=[0, 6]), window=(df.index[0], df.index[4]), mode="maker")
    assert len(tr) == 1 and tr[0].exit_type == "window_end" and tr[0].exit_i == 4


def test_simulate_exec_prices_maker_legs_with_maker_fee_and_no_slippage():
    df = bars([(100, 101, 99, 100), (100, 106, 99.5, 105), (105, 106, 104, 105.5), (105.5, 106, 105, 105.8)])
    tr = generate_trades_exec(df, signals(4, entry_at=[0], exit_at=[1]), mode="maker")
    res = simulate_exec(df, tr, COSTS, start=1000, risk=1.0)   # risk large -> cash-capped
    t = res.trades.iloc[0]
    qty = 1000 / (100 * 1.005)
    assert np.isclose(t.qty, qty) and np.isclose(t.slippage, 0.0)
    assert np.isclose(t.fees, qty * 100 * 0.005 + qty * 105 * 0.005)
    assert np.isclose(t.net, qty * 5 - t.fees)
    assert t.notional <= 1000                                  # no leverage


def test_simulate_exec_cash_cap_and_min_order():
    df = bars([(100, 101, 99, 100), (100, 106, 99.5, 105), (105, 106, 104, 105.5)])
    tr = generate_trades_exec(df, signals(3, entry_at=[0], stop=0.5), mode="taker")
    res = simulate_exec(df, tr, COSTS, start=200, risk=0.15)
    t = res.trades.iloc[0]
    assert t.notional + t.fees - (t.qty * t.exit_ref * (1 - COSTS.taker_price_impact()) * COSTS.taker_fee) <= 200 + 1e-9
    assert simulate_exec(df, tr, COSTS, start=0.5, risk=0.15).skipped_min_order == 1


# ------------------------------------------------------------------------------------ acceptance
def _good(**over):
    r = {"mode": "taker", "val_pass": True, "oos_trades": 8, "oos_expectancy_pct": 0.02, "oos_profit_factor": 1.8,
         "wf_trades": 30, "wf_expectancy_pct": 0.01, "wf_profit_factor": 1.7, "full_profit_factor": 1.9,
         "full_trades": 60, "full_max_drawdown": 0.15, "paper_max_drawdown": 0.35, "best_year_share_of_net": 0.3,
         "pf_without_best_year": 1.5, "neighbour_median_pf": 1.5, "net_without_topk": 500.0}
    r.update(over)
    return r


def test_acceptance_pass_marginal_fail():
    from backtest.daily_study import acceptance
    assert acceptance(_good()) == ("PASS", [])
    st, why = acceptance(_good(oos_profit_factor=1.35))
    assert st == "MARGINAL" and "OOS PF 1.35" in why[0]
    for bad, text in [({"oos_profit_factor": 1.1}, "OOS PF <"), ({"best_year_share_of_net": 0.7}, "best year"),
                      ({"net_without_topk": -5.0}, "best few trades"), ({"paper_max_drawdown": 0.7}, "15% risk"),
                      ({"neighbour_median_pf": 1.0}, "neighbour"), ({"wf_trades": 5}, "walk-forward trades"),
                      ({"val_pass": False}, "validation"), ({"oos_expectancy_pct": None}, "OOS expectancy"),
                      ({"mode": "maker", "taker_check_pf": 0.9}, "taker costs")]:
        st, why = acceptance(_good(**bad))
        assert st == "FAIL" and any(text in w for w in why), (bad, why)
    assert acceptance(_good(mode="maker", taker_check_pf=1.2))[0] == "PASS"


def test_trade_concentration_and_year_dependence():
    from backtest.daily_study import trade_concentration, year_dependence
    t = pd.DataFrame({"net": [100.0, -10, -10, 5, -10], "ret": [.1, -.01, -.01, .005, -.01],
                      "exit_time": pd.to_datetime(["2020-01-01", "2020-02-01", "2021-01-01", "2021-02-01", "2022-01-01"], utc=True)})
    c = trade_concentration(t)
    assert c["top_k"] == 2 and c["net_without_topk"] == -30 and np.isclose(c["best_trade_share"], 100 / 75)
    y = year_dependence(t)
    assert y["best_year"] == 2020 and y["pf_without_best_year"] == 5 / 20


# -------------------------------------------------------------------------------------- pipeline
def test_daily_study_runs_end_to_end_on_synthetic_data(tmp_path, monkeypatch):
    from backtest import daily_study as ds
    daily = random_walk(2600, seed=21, freq="1D")
    daily.index = pd.date_range("2017-01-01", periods=len(daily), freq="1D", tz="UTC")
    p = tmp_path / "x.csv.gz"; p.write_text("x")
    monkeypatch.setattr(ds, "data_path", lambda tf: p)
    monkeypatch.setattr(ds, "load_timeframe", lambda tf: daily)
    monkeypatch.setattr(ds, "default_costs", lambda: CostModel("t"))
    assert ds.main(["--tf", "1d", "3d", "--out", str(tmp_path / "out")]) == 0
    rep = (tmp_path / "out" / "REPORT.md").read_text()
    summ = pd.read_csv(tmp_path / "out" / "strategy_summary.csv")
    assert len(summ) == 2 * 2 * len(DAILY_FAMILIES) and set(summ["mode"]) == {"taker", "maker"}
    assert "buy-and-hold" in rep and "Maker vs taker" in rep and "$200 simulation" in rep
    assert "PASS" not in set(summ.status)       # a driftless random walk must not produce an accepted strategy


def test_daily_study_refuses_without_data(tmp_path, monkeypatch, capsys):
    from backtest import daily_study as ds
    monkeypatch.setattr(ds, "data_path", lambda tf: tmp_path / "none.csv.gz")
    assert ds.main(["--out", str(tmp_path / "o")]) == 3
    assert "MISSING DATA" in capsys.readouterr().err


def test_by_regime_matches_tz_aware_entry_days():
    from backtest.metrics import by_regime, regime_labels
    d = random_walk(900, seed=21, freq="1D")
    t = pd.DataFrame({"entry_time": d.index[[500, 600, 700]], "net": [10.0, -5.0, 3.0], "ret": [.01, -.005, .003]})
    reg = by_regime(t, regime_labels(d))
    assert not reg.empty and reg[reg.regime.isin(["BULL", "BEAR", "SIDEWAYS"])].trades.sum() == 3
