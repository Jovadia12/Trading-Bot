"""Momentum Breakout study: signals (no look-ahead, filters), position engine (partials, breakeven, trail,
time exit, maker fills, windows), accounting, acceptance and the end-to-end pipeline (synthetic data only)."""
import numpy as np
import pandas as pd
import pytest

from backtest.costs import ZERO, CostModel
from backtest.momentum_engine import generate_positions, simulate_positions
from backtest.strategies_momentum import VERSIONS, ExitSpec, MomentumSignals, filtered
from tests.test_backtest_engine import random_walk

COSTS = CostModel("t")


def bars(rows, freq="1h"):
    idx = pd.date_range("2024-01-01", periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame([dict(open=o, high=h, low=l, close=c, volume=1.0) for o, h, l, c in rows], index=idx)


def sig(n, spec, entry_at=(0,), atr=10.0, bar_hours=1.0):
    e = np.zeros(n, bool); e[list(entry_at)] = True
    return MomentumSignals(e, np.full(n, atr), spec, bar_hours)


B_SPEC = ExitSpec(stop_atr=1.0, trail_atr=2.0, trail_from_entry=False, partial_r=2.0, partial_frac=0.5,
                  breakeven_after_partial=True)


# ------------------------------------------------------------------------------------------ signals
def _perturbed(df, seed=3, cut=None):
    fut = df.copy()
    fut.iloc[cut + 1:, :5] *= np.random.default_rng(seed).uniform(0.5, 1.5, (len(df) - cut - 1, 1))
    fut["high"] = fut[["open", "high", "close"]].max(axis=1)
    fut["low"] = fut[["open", "low", "close"]].min(axis=1)
    return fut


@pytest.mark.parametrize("version", VERSIONS, ids=lambda v: v.key)
def test_versions_use_no_future_data(version):
    df = random_walk(2500, seed=9, freq="1h")
    cut = 1800
    fut = _perturbed(df, cut=cut)
    combos = version.combos()
    for combo in combos + [c for base in combos for c in version.neighbours(base)]:
        a, b = version.build(df, combo), version.build(fut, combo)
        assert (a.entry[:cut + 1] == b.entry[:cut + 1]).all(), (version.key, combo)
        assert np.allclose(a.atr[:cut + 1], b.atr[:cut + 1], equal_nan=True)


def test_grids_are_small_and_as_preregistered():
    v = {x.key: x for x in VERSIONS}
    assert [x.tf for x in VERSIONS] == ["4h", "1h", "15m"]
    assert len(v["A_4h_conservative"].combos()) == 4 and len(v["C_15m_faster"].combos()) == 4
    assert v["B_1h_main"].combos() == [{}]
    b = v["B_1h_main"].params({})
    assert (b["n"], b["stop_atr"], b["vol_mult"], b["rsi_lo"], b["rsi_hi"], b["atr_lo"], b["atr_hi"], b["partial_r"],
            b["trail_atr"], b["time_exit_hours"], b["time_exit_r"]) == (20, 1.5, 1.2, 55, 75, 0.004, 0.03, 2.0, 2.0, 24, 0.5)
    assert len(v["B_1h_main"].neighbours({})) == 12
    a_spec = v["A_4h_conservative"].build(random_walk(400, freq="4h"), {"n": 20, "stop_atr": 1.5}).exit
    assert a_spec.trail_from_entry and a_spec.partial_r is None and a_spec.time_exit_hours is None
    assert v["C_15m_faster"].params({"n": 20, "stop_atr": 1.5})["time_exit_hours"] == 24.0


def test_filtered_entry_requires_each_filter():
    df = random_walk(3000, seed=4, freq="1h")
    base = filtered(df).entry
    loose = filtered(df, vol_mult=0.0, rsi_lo=0, rsi_hi=100, atr_lo=0, atr_hi=1).entry
    assert base.sum() > 0 and loose.sum() > base.sum() and not (base & ~loose).any()
    assert filtered(df, vol_mult=1e9).entry.sum() == 0 and filtered(df, rsi_lo=99.9).entry.sum() == 0
    assert filtered(df, atr_hi=1e-9).entry.sum() == 0


def test_volume_average_excludes_current_bar():
    df = random_walk(600, seed=2, freq="1h")
    a = filtered(df, vol_mult=1.0, rsi_lo=0, rsi_hi=100, atr_lo=0, atr_hi=1).entry
    df2 = df.copy()
    df2.iloc[-1, df2.columns.get_loc("volume")] *= 1000  # huge current volume: its own average must not absorb it
    b = filtered(df2, vol_mult=1.0, rsi_lo=0, rsi_hi=100, atr_lo=0, atr_hi=1).entry
    assert (a[:-1] == b[:-1]).all()


# -------------------------------------------------------------------------------------- taker engine
def test_partial_at_2r_then_breakeven_stop():
    df = bars([(100, 101, 99, 100), (100, 105, 98, 104), (104, 121, 103, 118), (118, 119, 99, 105), (105, 106, 104, 105)])
    p = generate_positions(df, sig(5, B_SPEC))[0]
    assert p.entry_ref == 100 and p.stop0 == 90 and p.entry_i == 1
    assert [(l.frac, l.exit_i, l.exit_ref, l.exit_type) for l in p.legs] == [(0.5, 2, 120, "partial_target"), (0.5, 3, 100, "stop")]
    res = simulate_positions(df, [p], ZERO, start=1000, risk=0.01)
    t = res.trades.iloc[0]
    assert np.isclose(t.qty, 1.0) and np.isclose(t.net, 10.0)
    assert np.allclose(res.equity.iloc[1:4], [1004, 1019, 1010])   # MTM with half the position sold at bar 2


def test_touching_target_is_not_a_fill_and_stop_first_on_ambiguous_bar():
    df = bars([(100, 101, 99, 100), (100, 120, 98, 104), (104, 121, 89, 110), (110, 111, 109, 110)])
    p = generate_positions(df, sig(4, B_SPEC))[0]
    assert [(l.frac, l.exit_i, l.exit_ref, l.exit_type) for l in p.legs] == [(1.0, 2, 90, "stop")]


def test_gap_below_stop_fills_at_open():
    df = bars([(100, 101, 99, 100), (100, 103, 95, 101), (80, 82, 78, 81)])
    p = generate_positions(df, sig(3, B_SPEC))[0]
    assert p.legs[0].exit_ref == 80 and p.legs[0].exit_type == "stop"


def test_trail_after_partial_uses_highest_close():
    df = bars([(100, 101, 99, 100), (100, 121, 99, 119), (119, 140, 118, 139), (139, 139.5, 118.5, 125)])
    p = generate_positions(df, sig(4, B_SPEC))[0]
    # after bar 2 close: highest close 139 - 2*10 = 119 -> bar 3 low 118.5 hits 119
    assert p.legs[1].exit_ref == 119 and p.legs[1].exit_i == 3


def test_version_a_trail_active_from_entry_without_partial():
    spec = ExitSpec(stop_atr=1.5, trail_atr=2.0, trail_from_entry=True)
    df = bars([(100, 101, 99, 100), (100, 105, 99, 104), (104, 131, 103, 130), (130, 131, 109, 115)])
    p = generate_positions(df, sig(4, spec))[0]
    assert p.stop0 == 85 and [(l.frac, l.exit_ref, l.exit_type) for l in p.legs] == [(1.0, 110, "stop")]


def test_time_exit_after_24h_without_half_r():
    spec = ExitSpec(1.0, 2.0, False, 2.0, 0.5, True, time_exit_hours=3.0, time_exit_r=0.5)
    rows = [(100, 101, 99, 100), (100, 104, 97, 101), (101, 103, 98, 100), (100, 105, 96, 99), (98, 99, 97, 98), (98, 99, 97, 98)]
    p = generate_positions(bars(rows), sig(6, spec))[0]
    assert [(l.exit_i, l.exit_ref, l.exit_type) for l in p.legs] == [(4, 98, "time")]
    rows[2] = (101, 106, 98, 100)            # +0.5R (105) exceeded at bar 2 -> no time exit
    p2 = generate_positions(bars(rows), sig(6, spec))[0]
    assert p2.legs[0].exit_type == "data_end"


def test_time_exit_bar_count_scales_with_timeframe():
    spec = ExitSpec(1.0, 2.0, False, 2.0, 0.5, True, time_exit_hours=24.0, time_exit_r=0.5)
    rows = [(100, 101, 99, 100)] + [(100, 101, 99.5, 100)] * 120
    p = generate_positions(bars(rows, "15min"), sig(len(rows), spec, bar_hours=0.25))[0]
    assert p.legs[0].exit_type == "time" and p.legs[0].exit_i == 1 + 96


def test_positions_do_not_overlap_and_respect_window():
    rows = [(100, 101, 99.5, 100)] * 12
    df = bars(rows)
    spec = ExitSpec(1.0, 2.0, True)
    ps = generate_positions(df, sig(12, spec, entry_at=(0, 3, 8)), window=(df.index[0], df.index[6]))
    assert len(ps) == 1 and ps[0].legs[-1].exit_type == "window_end" and ps[0].exit_i == 6


# -------------------------------------------------------------------------------------- maker engine
def test_maker_entry_missed_unless_price_trades_through():
    df = bars([(100, 101, 99, 100), (100, 104, 99.95, 103), (103, 104, 102, 103)])
    st = {}
    assert generate_positions(df, sig(3, B_SPEC), mode="maker", stats=st) == [] and st["missed_entries"] == 1


def test_maker_entry_bar_high_does_not_count_for_target():
    df = bars([(100, 101, 99, 100), (100, 125, 99.8, 101), (101, 102, 100.5, 101.5)])
    p = generate_positions(df, sig(3, B_SPEC), mode="maker")[0]
    assert p.entry_ref == 100 and p.entry_maker and all(l.exit_type != "partial_target" for l in p.legs)


def test_maker_partial_is_maker_and_time_exit_limit_or_fallback():
    df = bars([(100, 101, 99, 100), (100, 103, 99.5, 101), (101, 121, 100.5, 118), (118, 119, 99, 105)])
    p = generate_positions(df, sig(4, B_SPEC), mode="maker")[0]
    assert p.legs[0].exit_type == "partial_target" and p.legs[0].maker
    spec = ExitSpec(1.0, 2.0, False, 2.0, 0.5, True, time_exit_hours=2.0)
    rows = [(100, 101, 99, 100), (100, 102, 99.5, 101), (101, 103, 98, 102), (102, 102.05, 101, 101.5), (101, 102, 100, 101)]
    p2 = generate_positions(bars(rows), sig(5, spec), mode="maker")[0]
    assert (p2.legs[0].exit_type, p2.legs[0].exit_i, p2.legs[0].exit_ref) == ("time_taker_fallback", 4, 101)
    rows[3] = (102, 103, 101, 102.5)
    p3 = generate_positions(bars(rows), sig(5, spec), mode="maker")[0]
    assert (p3.legs[0].exit_type, p3.legs[0].exit_ref, p3.legs[0].maker) == ("time_maker", 102, True)


# ----------------------------------------------------------------------------------------- accounting
def test_simulator_fees_by_leg_and_cash_cap():
    df = bars([(100, 101, 99, 100), (100, 105, 98, 104), (104, 121, 103, 118), (118, 119, 99, 105), (105, 106, 104, 105)])
    p = generate_positions(df, sig(5, B_SPEC))[0]
    res = simulate_positions(df, [p], COSTS, start=1000, risk=0.5)          # risk-size 50 BTC -> cash-capped
    t = res.trades.iloc[0]
    imp = COSTS.taker_price_impact()
    e_fill = 100 * (1 + imp)
    qty = 1000 / (e_fill * 1.009)
    assert np.isclose(t.qty, qty) and t.notional <= 1000
    x1 = 120 * (1 - imp)
    x2 = 100 * (1 - COSTS.taker_price_impact(is_stop=True))
    fees = qty * e_fill * 0.009 + qty / 2 * x1 * 0.009 + qty / 2 * x2 * 0.009
    assert np.isclose(t.fees, fees)
    assert np.isclose(res.equity.iloc[-1], 1000 - qty * e_fill - qty * e_fill * 0.009 + qty / 2 * (x1 + x2) * (1 - 0.009))
    mk = generate_positions(df, sig(5, B_SPEC), mode="maker")
    if mk:
        tm = simulate_positions(df, mk, COSTS, start=1000, risk=0.01).trades.iloc[0]
        assert tm.entry_maker and tm.slippage >= 0


def test_min_order_is_skipped():
    df = bars([(100, 101, 99, 100), (100, 105, 98, 104), (104, 106, 103, 105)])
    res = simulate_positions(df, generate_positions(df, sig(3, B_SPEC)), COSTS, start=0.5, risk=0.02)
    assert res.skipped_min_order == 1 and res.trades.empty


# ------------------------------------------------------------------------------------------ acceptance
def _good(**over):
    r = {"mode": "taker", "val_pass": True, "oos_trades": 60, "oos_expectancy_pct": 0.002, "oos_net_return": 0.05,
         "oos_profit_factor": 1.8, "wf_trades": 200, "wf_expectancy_pct": 0.002, "wf_profit_factor": 1.6,
         "full_profit_factor": 1.7, "sim_2pct_max_drawdown": 0.2, "best_year_share_of_net": 0.3,
         "pf_without_best_year": 1.4, "neighbour_median_pf": 1.4, "net_without_topk": 100.0}
    r.update(over)
    return r


def test_acceptance_rules():
    from backtest.momentum_study import acceptance
    v = {x.key: x for x in VERSIONS}["C_15m_faster"]
    assert acceptance(_good(), v) == ("PASS", [])
    assert acceptance(_good(wf_profit_factor=1.3), v)[0] == "MARGINAL"
    for bad, text in [({"oos_net_return": -0.01}, "OOS net return"), ({"oos_trades": 10}, "OOS trades"),
                      ({"sim_2pct_max_drawdown": 0.4}, "2% risk"), ({"neighbour_median_pf": 1.1}, "nearby"),
                      ({"best_year_share_of_net": 0.6}, "best year"), ({"wf_profit_factor": 1.1}, "walk-forward PF <"),
                      ({"mode": "maker", "taker_check_pf": 0.95}, "taker costs"), ({"val_pass": False}, "validation")]:
        st, why = acceptance(_good(**bad), v)
        assert st == "FAIL" and any(text in w for w in why), (bad, why)


# ------------------------------------------------------------------------------------------- pipeline
def test_momentum_study_end_to_end_on_synthetic_data(tmp_path, monkeypatch):
    from backtest import momentum_study as ms
    from backtest.data import resample
    base = random_walk(40_000, seed=17, freq="15min")
    base.index = pd.date_range("2017-01-01", periods=len(base), freq="15min", tz="UTC")
    p = tmp_path / "x.csv.gz"; p.write_text("x")
    monkeypatch.setattr(ms, "data_path", lambda tf: p)
    monkeypatch.setattr(ms, "load_timeframe", lambda tf: base if tf == "15m" else resample(base, tf))
    monkeypatch.setattr(ms, "default_costs", lambda: CostModel("t"))
    monkeypatch.setattr(ms, "P", ms.MomentumProtocol(wf_train_days=120, wf_test_days=60))
    assert ms.main(["--out", str(tmp_path / "o")]) == 0
    rep = (tmp_path / "o" / "REPORT.md").read_text()
    summ = pd.read_csv(tmp_path / "o" / "strategy_summary.csv")
    assert len(summ) == 6 and set(summ["mode"]) == {"taker", "maker"}
    assert "PASS" not in set(summ.status) and "NO STRATEGY PASSED" in rep
    for s in ("buy-and-hold", "Maker vs taker", "$200 simulation", "by year", "| 2% |", "| 10% |"):
        assert s in rep, s


def test_momentum_study_refuses_without_data(tmp_path, monkeypatch, capsys):
    from backtest import momentum_study as ms
    monkeypatch.setattr(ms, "data_path", lambda tf: tmp_path / "none")
    assert ms.main(["--out", str(tmp_path / "o")]) == 3 and "MISSING DATA" in capsys.readouterr().err
