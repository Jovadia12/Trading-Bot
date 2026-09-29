"""HTF (2h/4h/6h) study: look-ahead safety of the new families, resampling, acceptance extras, pipeline."""
import numpy as np
import pandas as pd
import pytest

from backtest.costs import CostModel
from backtest.data import TF_SECONDS, resample, save_candles
from backtest.strategies import build
from backtest.strategies_htf import HTF_FAMILIES, HTF_TIMEFRAMES
from tests.test_backtest_engine import random_walk


@pytest.mark.parametrize("family", HTF_FAMILIES, ids=lambda f: f.key)
def test_htf_family_uses_no_future_data(family):
    df = random_walk(3000, seed=5, freq="4h")
    cut = 2000
    future = df.copy()
    future.iloc[cut + 1:, :4] *= np.random.default_rng(3).uniform(0.5, 1.5, (len(df) - cut - 1, 1))
    future["high"] = future[["open", "high", "close"]].max(axis=1)
    future["low"] = future[["open", "low", "close"]].min(axis=1)
    for combo in family.combos():
        a, b = build(family, df, combo), build(family, future, combo)
        assert (a.entry[:cut + 1] == b.entry[:cut + 1]).all(), (family.key, combo)
        assert np.allclose(a.stop_dist[:cut + 1], b.stop_dist[:cut + 1], equal_nan=True)
        if a.exit_sig is not None:
            assert (a.exit_sig[:cut + 1] == b.exit_sig[:cut + 1]).all()
        if a.trail_dist is not None:
            assert np.allclose(a.trail_dist[:cut + 1], b.trail_dist[:cut + 1], equal_nan=True)


@pytest.mark.parametrize("family", HTF_FAMILIES, ids=lambda f: f.key)
def test_htf_family_trades_and_has_stops(family):
    df = random_walk(4000, seed=11, freq="4h")
    s = build(family, df, family.combos()[0])
    assert s.entry.sum() > 0 and np.all(s.stop_dist[s.entry] > 0)


def test_grid_is_small_and_timeframes_are_2h_4h_6h():
    assert sum(len(f.combos()) for f in HTF_FAMILIES) == 32 and HTF_TIMEFRAMES == ["2h", "4h", "6h"]
    assert TF_SECONDS["2h"] == 7200 and TF_SECONDS["6h"] == 21600


def test_resample_2h_and_6h_are_utc_aligned():
    df = random_walk(48, freq="1h")
    six = resample(df, "6h")
    assert [t.hour for t in six.index[:4]] == [0, 6, 12, 18] and six.high.iloc[0] == df.high.iloc[:6].max()
    assert len(resample(df, "2h")) == 24


def test_acceptance_extra_checks():
    from backtest import research as r
    base = {"val_pass": True, "oos_profit_factor": 1.8, "oos_expectancy_pct": 0.01, "wf_profit_factor": 1.7,
            "wf_expectancy_pct": 0.01, "full_trades": 400, "full_max_drawdown": 0.2}
    old = r.P
    r.P = r.Protocol(min_train_trades=60, min_val_trades=15, accept_trades=150)
    try:
        assert r.acceptance({**base, "neighbour_median_net_pf": 1.3, "pf_without_best_year": 1.4}) == (True, [])
        ok, why = r.acceptance({**base, "neighbour_median_net_pf": 0.9, "pf_without_best_year": 0.8})
        assert not ok and any("neighbourhood" in w for w in why) and any("single calendar year" in w for w in why)
    finally:
        r.P = old


def test_htf_study_runs_end_to_end_on_synthetic_data(tmp_path, monkeypatch):
    """Mechanics only: a random walk must not yield an accepted strategy after costs."""
    import backtest.research as r
    base = random_walk(40000, seed=21, freq="1h")
    p = tmp_path / "coinbase_btcusd_5m.csv.gz"
    save_candles(base, p)
    monkeypatch.setattr(r, "data_path", lambda tf: p)
    monkeypatch.setattr(r, "load_timeframe", lambda tf: resample(base, tf))
    monkeypatch.setattr(r, "default_costs", lambda: CostModel("t"))
    out = tmp_path / "htf"
    assert r.main(["--study", "htf", "--tf", "4h", "--out", str(out)]) == 0
    text = (out / "REPORT.md").read_text()
    assert "study `htf`" in text and "HTF_STRATEGY_PROTOCOL.md" in text
    summ = pd.read_csv(out / "strategy_summary.csv")
    assert set(summ.family) == {f.key for f in HTF_FAMILIES} and not summ.accepted.any()
    assert r.P == r.Protocol(min_train_trades=60, min_val_trades=15, accept_trades=150)
    r.P = r.Protocol()      # restore the module default for other tests
