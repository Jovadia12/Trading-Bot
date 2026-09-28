"""Correctness tests for the research backtester. Synthetic data here tests MECHANICS only;
nothing in this file is, or may be reported as, a strategy result."""
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from backtest import indicators as ind
from backtest.costs import ZERO, CostModel
from backtest.data import TF_SECONDS, load_candles, quality_report, resample, save_candles
from backtest.engine import Signals, generate_trades, simulate_account
from backtest.metrics import drawdown_stats, regime_labels, summarize
from backtest.research import monte_carlo, neighbours
from backtest.strategies import FAMILIES, build


def frame(rows, start="2024-01-01", freq="1h"):
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=1.0)


def sig(n, entries, stop=5.0, tp=None, exit_at=(), max_hold=None, trail=None):
    e = np.zeros(n, bool)
    e[list(entries)] = True
    x = np.zeros(n, bool)
    x[list(exit_at)] = True
    return Signals(e, np.full(n, stop), None if tp is None else np.full(n, tp), x if exit_at else None, max_hold,
                   None if trail is None else np.full(n, trail))


FLAT = [(100, 101, 99, 100)] * 10


# ---- execution rules -------------------------------------------------------------------------------

def test_entry_is_next_bar_open_not_signal_close():
    df = frame([(100, 101, 99, 100), (105, 106, 104, 105)] + FLAT)
    t = generate_trades(df, sig(len(df), [0], stop=50.0, exit_at=[3]))[0]
    assert t.signal_i == 0 and t.entry_i == 1 and t.entry_ref == 105
    assert t.exit_type == "signal" and t.exit_i == 4 and t.exit_ref == df.open.iloc[4]


def test_stop_intrabar_and_gap_fill():
    rows = [(100, 101, 99, 100), (100, 101, 99, 100), (100, 100, 94, 96)] + FLAT
    t = generate_trades(frame(rows), sig(len(rows), [0], stop=5.0))[0]
    assert t.exit_type == "stop" and t.exit_ref == 95 and t.exit_i == 2          # intrabar: stop price
    rows = [(100, 101, 99, 100), (100, 101, 99, 100), (90, 92, 88, 91)] + FLAT
    t = generate_trades(frame(rows), sig(len(rows), [0], stop=5.0))[0]
    assert t.exit_type == "stop" and t.exit_ref == 90                           # gap: filled at the open


def test_target_needs_strictly_higher_high_and_stop_wins_same_bar():
    rows = [(100, 101, 99, 100), (100, 110, 99, 100)] + FLAT                    # touches 110 exactly
    t = generate_trades(frame(rows), sig(len(rows), [0], stop=5.0, tp=10.0))[0]
    assert t.exit_type != "target"
    rows = [(100, 101, 99, 100), (100, 110.5, 99, 100)] + FLAT
    assert generate_trades(frame(rows), sig(len(rows), [0], stop=5.0, tp=10.0))[0].exit_type == "target"
    rows = [(100, 101, 99, 100), (100, 111, 94, 100)] + FLAT                    # both in one bar
    t = generate_trades(frame(rows), sig(len(rows), [0], stop=5.0, tp=10.0))[0]
    assert t.exit_type == "stop" and t.exit_ref == 95


def test_entry_bar_is_checked_after_the_open():
    rows = [(100, 101, 99, 100), (100, 100, 90, 92)] + FLAT
    t = generate_trades(frame(rows), sig(len(rows), [0], stop=5.0))[0]
    assert t.entry_i == 1 and t.exit_i == 1 and t.exit_ref == 95


def test_time_exit_and_one_position_at_a_time():
    df = frame(FLAT * 3)
    ts = generate_trades(df, sig(len(df), [0, 1, 2, 5, 10], max_hold=3))
    assert [(t.entry_i, t.exit_i, t.exit_type) for t in ts][:2] == [(1, 4, "time"), (6, 9, "time")]


def test_trailing_stop_updates_at_close_and_applies_next_bar():
    rows = [(100, 101, 99, 100), (100, 101, 99, 100), (100, 121, 99, 120), (120, 121, 104, 110)] + FLAT
    t = generate_trades(frame(rows), sig(len(rows), [0], stop=50.0, trail=10.0))[0]
    assert t.exit_type == "stop" and t.exit_i == 3 and t.exit_ref == 110          # 120 - 10 from bar 2's close


def test_window_restricts_entries_and_force_closes():
    df = frame(FLAT * 3)
    w = (df.index[5], df.index[12])
    ts = generate_trades(df, sig(len(df), [2, 6], exit_at=[25]), window=w)
    assert len(ts) == 1 and ts[0].signal_i == 6 and ts[0].exit_i == 12 and ts[0].exit_type == "window_end"


# ---- account, sizing and costs --------------------------------------------------------------------

COST = CostModel("t", maker_fee=0.004, taker_fee=0.006, half_spread=0.0001, slippage=0.0002, stop_slippage=0.0005)


def test_cost_accounting_is_exact_for_target_exit():
    rows = [(100, 101, 99, 100), (100, 101, 99, 100), (100, 111, 99, 110)] + FLAT
    df = frame(rows)
    res = simulate_account(df, generate_trades(df, sig(len(rows), [0], stop=5.0, tp=10.0)), COST, start=1000, risk=0.01)
    t = res.trades.iloc[0]
    e_fill = 100 * 1.0003
    qty = min(0.01 * 1000 / 5.0, 1000 / (e_fill * 1.006))
    assert t.qty == pytest.approx(qty)
    assert t.gross == pytest.approx(qty * 10)
    assert t.fees == pytest.approx(qty * e_fill * 0.006 + qty * 110 * 0.004)          # maker on the target
    assert t.slippage == pytest.approx(qty * (e_fill - 100))                           # no slippage on a limit exit
    assert t.net == pytest.approx(t.gross - t.fees - t.slippage)
    assert res.equity.iloc[-1] == pytest.approx(1000 + t.net)


def test_stop_exit_pays_taker_fee_and_stop_slippage():
    rows = [(100, 101, 99, 100), (100, 101, 94, 96)] + FLAT
    df = frame(rows)
    t = simulate_account(df, generate_trades(df, sig(len(rows), [0], stop=5.0)), COST, 1000, 0.01).trades.iloc[0]
    x_fill = 95 * (1 - 0.0008)
    assert t.slippage == pytest.approx(t.qty * (100 * 1.0003 - 100) + t.qty * (95 - x_fill))
    assert t.fees == pytest.approx(t.qty * 100 * 1.0003 * 0.006 + t.qty * x_fill * 0.006)


def test_cash_is_the_hard_cap_no_leverage():
    df = frame([(100, 101, 99, 100)] * 5)
    t = simulate_account(df, generate_trades(df, sig(5, [0], stop=0.5, exit_at=[2])), COST, 1000, 0.03).trades.iloc[0]
    assert t.qty * 100 * 1.0003 * 1.006 <= 1000 + 1e-9                 # 3% risk over a 0.5 stop would be 60 BTC


def test_min_order_skips_dust_trades():
    df = frame([(100, 101, 99, 100)] * 5)
    res = simulate_account(df, generate_trades(df, sig(5, [0], stop=50.0, exit_at=[2])), COST, start=5, risk=0.001)
    assert res.trades.empty and res.skipped_min_order == 1


def test_mark_to_market_equity_shows_open_drawdown():
    rows = [(100, 101, 99, 100), (100, 101, 99, 100), (100, 100, 96, 97), (97, 101, 96, 100)] + FLAT
    df = frame(rows)
    res = simulate_account(df, generate_trades(df, sig(len(rows), [0], stop=10.0, exit_at=[3])), ZERO, 1000, 0.01)
    assert res.equity.iloc[2] < 1000 and res.equity.iloc[-1] == pytest.approx(1000)


# ---- metrics -------------------------------------------------------------------------------------

def test_drawdown_and_summary_numbers():
    eq = pd.Series([100, 110, 99, 120, 108, 130], index=pd.date_range("2024", periods=6, freq="D", tz="UTC"), dtype=float)
    mdd, add = drawdown_stats(eq)
    assert mdd == pytest.approx(0.1) and add == pytest.approx((0.1 + 0.1) / 2)
    rows = [(100, 101, 99, 100), (100, 101, 99, 100), (100, 111, 99, 110), (110, 111, 109, 110),
            (110, 111, 104, 106), (106, 107, 105, 106)] + FLAT
    df = frame(rows)
    s = sig(len(rows), [0, 3], stop=5.0, tp=10.0)
    res = simulate_account(df, generate_trades(df, s), ZERO, 1000, 0.01)
    m = summarize(res, len(df), 3600)
    assert m["trades"] == 2 and m["winning"] == 1 and m["win_rate"] == 0.5
    assert m["profit_factor"] == pytest.approx(res.trades.net.iloc[0] / -res.trades.net.iloc[1])
    assert m["longest_loss_streak"] == 1 and m["fees"] == 0


# ---- look-ahead: every strategy family -------------------------------------------------------------

def random_walk(n=3000, seed=1, freq="1h"):
    rng = np.random.default_rng(seed)
    close = 30000 * np.exp(np.cumsum(rng.normal(0, 0.006, n)))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.002, n)))
    lo = np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.002, n)))
    idx = pd.date_range("2021-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close, "volume": rng.uniform(1, 5, n)}, index=idx)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.key)
def test_no_strategy_uses_future_data(family):
    df = random_walk()
    cut = 2000
    future = df.copy()
    rng = np.random.default_rng(99)
    future.iloc[cut + 1:, :4] *= rng.uniform(0.5, 1.5, (len(df) - cut - 1, 1))    # rewrite everything after bar `cut`
    future["high"] = future[["open", "high", "close"]].max(axis=1)
    future["low"] = future[["open", "low", "close"]].min(axis=1)
    for combo in family.combos():
        a, b = build(family, df, combo), build(family, future, combo)
        assert (a.entry[:cut + 1] == b.entry[:cut + 1]).all(), (family.key, combo)
        assert np.allclose(a.stop_dist[:cut + 1], b.stop_dist[:cut + 1], equal_nan=True)
        if a.exit_sig is not None:
            assert (a.exit_sig[:cut + 1] == b.exit_sig[:cut + 1]).all()


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.key)
def test_every_family_produces_trades_with_positive_stops(family):
    df = random_walk()
    s = build(family, df, family.combos()[0])
    assert s.entry.sum() > 0
    assert np.all(s.stop_dist[s.entry] > 0)


def test_indicator_definitions():
    df = random_walk(500)
    assert ind.donchian_high(df, 5).iloc[10] == df.high.iloc[5:10].max()          # excludes current bar
    r = ind.rsi(pd.Series(np.arange(1.0, 50.0)), 14)
    assert r.iloc[-1] == 100
    v = ind.session_vwap(df)
    first = df.index.floor("1D") == df.index[0].floor("1D")
    tp = (df.high + df.low + df.close) / 3
    assert v[first].iloc[3] == pytest.approx((tp[first] * df.volume[first]).iloc[:4].sum() / df.volume[first].iloc[:4].sum())


def test_neighbours_are_one_grid_step_away():
    fam = next(f for f in FAMILIES if f.key == "bb_mr")
    nb = neighbours(fam, {"k": 2.0, "stop_atr": 2.0})
    assert {json.dumps(x, sort_keys=True) for x in nb} == {json.dumps(x, sort_keys=True) for x in
            [{"k": 1.5, "stop_atr": 2.0}, {"k": 2.5, "stop_atr": 2.0}, {"k": 2.0, "stop_atr": 3.0}]}


def test_monte_carlo_is_reproducible_and_sane():
    rets = np.array([0.02, -0.01, 0.015, -0.01])
    a, b = monte_carlo(rets, 100, 500, 1), monte_carlo(rets, 100, 500, 1)
    assert a == b and a["final_multiple_p05"] <= a["final_multiple_median"] <= a["final_multiple_p95"]
    assert 0 <= a["prob_end_below_start"] <= 1


# ---- data ----------------------------------------------------------------------------------------

def test_quality_report_detects_problems_and_resample(tmp_path):
    df = random_walk(48, freq="1h")
    bad = df.drop(df.index[[5, 6, 7]])
    bad.iloc[10, bad.columns.get_loc("high")] = bad.iloc[10].low - 1
    q = quality_report(bad, "1h")
    assert q.missing_bars == 3 and q.largest_gap_bars == 3 and q.bad_ohlc_rows == 1
    four = resample(df, "4h")
    assert len(four) == 12 and four.high.iloc[0] == df.high.iloc[:4].max() and four.open.iloc[0] == df.open.iloc[0]
    p = tmp_path / "x.csv.gz"
    sha1 = save_candles(df, p)
    assert np.allclose(load_candles(p).close, df.close, rtol=1e-7) and save_candles(df, p) == sha1   # deterministic


def test_fetch_paginates_within_350_candle_windows():
    from backtest.fetch_coinbase import fetch
    from market_data.models import Candle
    from decimal import Decimal as D

    class FakeClient:
        calls = []

        def get_candles(self, pid, start, end, tf):
            self.calls.append((start, end))
            assert (end - start).total_seconds() / TF_SECONDS[tf] <= 349
            out, t = [], start
            while t < end:
                out.append(Candle(t, D(1), D(2), D(1), D(1), D(1)))
                t += timedelta(seconds=TF_SECONDS[tf])
            return out
    s = datetime(2024, 1, 1, tzinfo=timezone.utc)
    df = fetch(FakeClient(), "5m", s, s + timedelta(days=3), pause_s=0, log=lambda *a: None)
    assert len(df) == 3 * 288 and df.index.is_unique and len(FakeClient.calls) == 3 * 288 // 349 + 1


# ---- pipeline ------------------------------------------------------------------------------------

def test_research_refuses_without_data(tmp_path, monkeypatch, capsys):
    import backtest.research as r
    import backtest.data as d
    monkeypatch.setattr(r, "data_path", lambda tf: tmp_path / f"none_{tf}.csv.gz")
    assert r.main(["--tf", "1h", "--out", str(tmp_path)]) == 3
    assert "No results were produced" in capsys.readouterr().err


def test_research_pipeline_runs_end_to_end_on_synthetic_data(tmp_path, monkeypatch):
    """Mechanics only: a random walk must NOT produce an accepted strategy."""
    import backtest.research as r
    df = random_walk(20000, seed=7)
    p = tmp_path / "coinbase_btcusd_1h.csv.gz"
    save_candles(df, p)
    monkeypatch.setattr(r, "data_path", lambda tf: p if tf == "1h" else tmp_path / "none.csv.gz")
    monkeypatch.setattr(r, "load_timeframe", lambda tf: df)
    monkeypatch.setattr(r, "default_costs", lambda: CostModel("t"))
    out = tmp_path / "out"
    assert r.main(["--tf", "1h", "--families", "bb_mr", "donchian", "--out", str(out)]) == 0
    text = (out / "REPORT.md").read_text()
    assert "Final comparison table" in text and (out / "strategy_summary.csv").is_file()
    summ = pd.read_csv(out / "strategy_summary.csv")
    assert not summ.accepted.any()                     # no edge in a random walk after costs
    assert "No strategy met the pre-registered acceptance criteria" in text
