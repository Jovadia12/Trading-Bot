"""Fib + FVG (Unicorn) research strategy: definitions, no look-ahead, execution and accounting. Synthetic data only."""
import math

import numpy as np
import pandas as pd
import pytest

from backtest.fib_fvg import (COST_CASES, Costs, Rules, Signal, find_signals, fvgs, indicators_5m, management_15m,
                              portfolio, resample_15m, simulate_trades, stop_price, swings)

R = Rules()


def walk(n=6000, seed=3, drift=0.0, vol=0.0025, start="2025-01-01"):
    rng = np.random.default_rng(seed)
    regime = np.sin(np.arange(n) / 700.0) * 0.0006 + drift                 # alternating up/down trends
    close = 100 * np.exp(np.cumsum(rng.normal(regime, vol)))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    lo = np.minimum(op, close) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    idx = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close, "volume": 1.0}, index=idx)


def perturb_after(df, cut, seed=9):
    f = df.copy()
    k = len(df) - cut - 1
    f.iloc[cut + 1:, :4] *= np.random.default_rng(seed).uniform(0.7, 1.3, (k, 1))
    f["high"] = f[["open", "high", "close"]].max(axis=1)
    f["low"] = f[["open", "low", "close"]].min(axis=1)
    return f


# ------------------------------------------------------------------------------------------- definitions
def test_swing_confirmation_needs_k_later_bars_and_is_strict():
    h = np.array([1, 2, 3, 9, 3, 2, 1, 1, 1], float)
    l = h - 0.5
    sh, shi, _sl, _sli = swings(h, l, 3)
    assert np.isnan(sh[5]) and sh[6] == 9 and shi[6] == 3            # pivot at 3 confirmed at 3+3
    h2 = np.array([1, 2, 9, 9, 3, 2, 1, 1], float)                    # equal highs: not a strict pivot
    assert np.all(np.isnan(swings(h2, h2 - 0.5, 2)[0]))


def test_fvg_three_candle_definition():
    h = np.array([10, 12, 15, 11], float)
    l = np.array([9, 10, 11, 8], float)
    bull, bear = fvgs(h, l)
    assert bull.tolist() == [False, False, True, False]              # high[0]=10 < low[2]=11
    h2, l2 = np.array([20, 19, 15], float), np.array([18, 16, 14], float)
    assert fvgs(h2, l2)[1].tolist() == [False, False, True]          # low[0]=18 > high[2]=15


def test_resample_15m_uses_complete_groups_only():
    df = walk(10)
    d15 = resample_15m(df)
    assert len(d15) == 3 and d15.high.iloc[0] == df.high.iloc[:3].max() and d15.close.iloc[0] == df.close.iloc[2]


# ---------------------------------------------------------------------------------------------- look-ahead
def test_swings_use_no_future_data():
    df = walk(3000)
    cut = 2000
    f = perturb_after(df, cut)
    a = swings(df.high.to_numpy(), df.low.to_numpy(), 3)
    b = swings(f.high.to_numpy(), f.low.to_numpy(), 3)
    for x, y in zip(a, b):
        assert np.array_equal(np.asarray(x)[:cut + 1], np.asarray(y)[:cut + 1], equal_nan=True)


@pytest.mark.parametrize("unicorn", [False, True])
def test_signals_use_no_future_data(unicorn):
    df = walk(8000, seed=5)
    cut = 6000
    a = find_signals(indicators_5m(df), unicorn)
    b = find_signals(indicators_5m(perturb_after(df, cut)), unicorn)
    key = lambda s: (s.i, s.side, round(s.zone_lo, 9), round(s.zone_hi, 9))
    assert [key(s) for s in a if s.i <= cut] == [key(s) for s in b if s.i <= cut]


def test_15m_management_uses_only_completed_15m_bars():
    df = walk(3000)
    cut = 2000
    a, b = management_15m(df), management_15m(perturb_after(df, cut))
    for k in ("exit_long", "exit_short", "trail_long", "trail_short", "src"):
        assert np.array_equal(a[k][:cut + 1], b[k][:cut + 1], equal_nan=True), k


# --------------------------------------------------------------------------------- every signal satisfies the rules
@pytest.mark.parametrize("seed", [5, 11])
def test_every_signal_satisfies_the_documented_conditions(seed):
    df = walk(12000, seed=seed)
    x = indicators_5m(df)
    sigs = find_signals(x, False)
    assert len(sigs) >= 5
    o, h, l, c = x["open"], x["high"], x["low"], x["close"]
    for s in sigs:
        i = s.i
        L, H = (s.impulse_start, s.impulse_end) if s.side == "long" else (s.impulse_end, s.impulse_start)
        rng = H - L
        assert rng >= R.min_impulse_atr * x["atr"][i] - 1e-9 and s.bos_i < i
        if s.side == "long":
            assert x["trend_long"][i]
            fib_lo, fib_hi = H - 0.618 * rng, H - 0.382 * rng
            assert fib_lo - 1e-9 <= s.zone_lo < s.zone_hi <= fib_hi + 1e-9
            assert l[i] <= s.zone_hi and c[i] > o[i] and c[i] > 0.5 * (s.zone_lo + s.zone_hi)
            # zone lies inside a real bullish FVG formed before the trigger
            js = [j for j in range(s.bos_i - 400, i) if j >= 2 and h[j - 2] < l[j]
                  and h[j - 2] <= s.zone_lo + 1e-9 and l[j] >= s.zone_hi - 1e-9]
            assert js
        else:
            assert x["trend_short"][i]
            fib_lo, fib_hi = L + 0.382 * rng, L + 0.618 * rng
            assert fib_lo - 1e-9 <= s.zone_lo < s.zone_hi <= fib_hi + 1e-9
            assert h[i] >= s.zone_lo and c[i] < o[i] and c[i] < 0.5 * (s.zone_lo + s.zone_hi)
            js = [j for j in range(s.bos_i - 400, i) if j >= 2 and l[j - 2] > h[j]
                  and h[j] <= s.zone_lo + 1e-9 and l[j - 2] >= s.zone_hi - 1e-9]
            assert js


def test_unicorn_is_a_subset_with_ema200_in_the_zone():
    df = walk(20000, seed=7)
    x = indicators_5m(df)
    std = {(s.i, s.side) for s in find_signals(x, False)}
    uni = find_signals(x, True)
    for s in uni:
        tol = R.unicorn_tol_atr * s.atr
        assert s.zone_lo - tol <= x["ema200"][s.i] <= s.zone_hi + tol
    assert uni and len(uni) < len(std)            # the EMA200 condition makes the Unicorn version much rarer


# --------------------------------------------------------------------------------------------- execution
def bars(rows, start="2025-01-01"):
    idx = pd.date_range(start, periods=len(rows), freq="5min", tz="UTC")
    return pd.DataFrame([dict(open=o, high=h, low=l, close=c, volume=1.0) for o, h, l, c in rows], index=idx)


def fake_x(df):
    return {k: df[k].to_numpy(float) for k in ("open", "high", "low", "close")}


def no_m15(n):
    return {"exit_long": np.zeros(n, bool), "exit_short": np.zeros(n, bool), "trail_long": np.full(n, np.nan),
            "trail_short": np.full(n, np.nan), "src": np.full(n, -1)}


SIG = Signal(i=0, side="long", zone_lo=98, zone_hi=99, fvg_edge=97.5, impulse_start=95, impulse_end=105, atr=1.0,
             bos_i=0, trigger_extreme=98.5)
TAKER = COST_CASES[0]


def test_entry_next_open_target_strict_and_stop_first():
    df = bars([(100, 101, 99, 100), (100, 101, 99.5, 100.5), (100.5, 103.0, 100, 102), (102, 103.01, 101, 102.5)] + [(102.5, 103, 102, 102.5)] * 3)
    t = simulate_trades("BTC", fake_x(df), no_m15(len(df)), [SIG], "atr1.5", "R2" if False else "R3", TAKER)
    # entry at open[1] = 100, R = 1.5 -> target 104.5 never traded through; data end
    assert t[0].entry_i == 1 and t[0].entry_ref == 100 and t[0].stop0 == 98.5 and t[0].exit_type == "data_end"
    df2 = bars([(100, 101, 99, 100), (100, 101, 99.5, 100.5), (100.5, 104.6, 98.0, 101)])
    t2 = simulate_trades("BTC", fake_x(df2), no_m15(3), [SIG], "atr1.5", "R3", TAKER)
    assert t2[0].exit_type == "stop" and t2[0].exit_ref == 98.5            # both inside one bar -> stop first
    df3 = bars([(100, 101, 99, 100), (100, 101, 99.5, 100.5), (100.5, 104.5, 100, 101), (101, 104.51, 100, 101)])
    t3 = simulate_trades("BTC", fake_x(df3), no_m15(4), [SIG], "atr1.5", "R3", TAKER)
    assert t3[0].exit_i == 3 and t3[0].exit_ref == 104.5                   # touching 104.5 is not a fill


def test_structural_stop_and_gap_fill():
    assert stop_price(SIG, 100.0, "struct") == pytest.approx(min(97.5, 98.5) - 0.1)
    df = bars([(100, 101, 99, 100), (100, 101, 99.5, 100.5), (95, 96, 94, 95)])
    t = simulate_trades("BTC", fake_x(df), no_m15(3), [SIG], "struct", "R5", TAKER)
    assert t[0].exit_type == "stop_gap" and t[0].exit_ref == 95


def test_exit_a_only_on_15m_bar_completed_after_entry():
    df = bars([(100, 101, 99.9, 100)] * 8)
    m = no_m15(8)
    m["exit_long"][:] = True
    m["src"][:4] = 1                     # condition already known at entry (bar 1) -> ignored
    m["src"][4:] = 4                     # a new 15m bar completes before bar 4's open
    t = simulate_trades("BTC", fake_x(df), m, [SIG], "atr2", "A", TAKER)
    assert t[0].exit_i == 4 and t[0].exit_type == "15m_opposite" and t[0].exit_ref == 100


def test_trailing_stop_only_tightens_with_fresh_15m_levels():
    df = bars([(100, 101, 99.9, 100)] * 5 + [(100, 100.2, 99.2, 99.5)])
    m = no_m15(6)
    m["trail_long"][:] = 99.4
    m["src"][:3] = 1                     # stale at entry: ignored
    m["src"][3:] = 3
    t = simulate_trades("BTC", fake_x(df), m, [SIG], "atr2", "B", TAKER)
    assert t[0].exit_type == "trail" and t[0].exit_ref == 99.4 and t[0].exit_i == 5


def test_one_position_per_coin():
    df = bars([(100, 101, 99.9, 100)] * 10)
    s2 = Signal(**{**SIG.__dict__, "i": 3})
    t = simulate_trades("BTC", fake_x(df), no_m15(10), [SIG, s2], "atr2", "R5", TAKER)
    assert len(t) == 1


# --------------------------------------------------------------------------------------------- accounting
def test_portfolio_fees_slippage_and_reconciliation():
    df = bars([(100, 101, 99, 100), (100, 101, 99.5, 100.5), (100.5, 104.6, 100, 104), (104, 105, 103, 104.5)])
    t = simulate_trades("BTC", fake_x(df), no_m15(4), [SIG], "atr1.5", "R3", TAKER)
    tr, eq = portfolio(t, {"BTC": df.close.to_numpy()}, df.index, TAKER, start=200.0)
    row = tr.iloc[0]
    imp = TAKER.impact()
    e_fill = 100 * (1 + imp)
    notional = 20.0
    qty = notional / e_fill
    x_fill = 104.5 * (1 - imp)
    assert row.notional == pytest.approx(notional) and row.qty == pytest.approx(qty)
    assert row.fees == pytest.approx(notional * 0.009 + qty * x_fill * 0.009)
    assert row.pnl == pytest.approx(qty * (x_fill - e_fill) - row.fees)
    assert eq.iloc[-1] == pytest.approx(200 + row.pnl)
    assert row.r_mult == pytest.approx(row.pnl / (qty * 1.5))


def test_maker_case_prices_entry_and_target_as_maker():
    maker = COST_CASES[1]
    df = bars([(100, 101, 99, 100), (100, 101, 99.5, 100.5), (100.5, 104.6, 100, 104)])
    t = simulate_trades("BTC", fake_x(df), no_m15(3), [SIG], "atr1.5", "R3", maker)
    tr, _eq = portfolio(t, {"BTC": df.close.to_numpy()}, df.index, maker)
    row = tr.iloc[0]
    assert row.entry_fill == 100 and row.exit_fill == 104.5 and row.slippage == pytest.approx(0)
    assert row.fees == pytest.approx(20 * 0.005 + row.qty * 104.5 * 0.005)


def test_short_trade_accounting():
    s = Signal(i=0, side="short", zone_lo=101, zone_hi=102, fvg_edge=102.5, impulse_start=105, impulse_end=95, atr=1.0,
               bos_i=0, trigger_extreme=101.5)
    df = bars([(100, 101, 99, 100), (100, 100.5, 99, 99.5), (99.5, 100, 95.4, 96)])
    t = simulate_trades("BTC", fake_x(df), no_m15(3), [s], "atr1.5", "R3", COST_CASES[2])
    assert t[0].side == "short" and t[0].exit_ref == 95.5
    tr, eq = portfolio(t, {"BTC": df.close.to_numpy()}, df.index, COST_CASES[2])
    assert tr.pnl.iloc[0] > 0 and eq.iloc[-1] == pytest.approx(200 + tr.pnl.iloc[0])


def test_research_module_has_no_order_or_network_code():
    import ast
    from pathlib import Path
    for p in ("backtest/fib_fvg.py", "backtest/fib_fvg_study.py"):
        tree = ast.parse((Path(__file__).resolve().parent.parent / p).read_text())
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
               {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any(m and m.split(".")[0] in ("exchange", "execution", "paper_trading", "requests") for m in mods), (p, mods)


def test_portfolio_frees_cash_of_trades_that_stop_out_on_their_entry_bar():
    """Regression: a trade exiting inside its own entry bar must release its cash for later entries."""
    from backtest.fib_fvg import Trade
    n = 200
    idx = pd.date_range("2025-01-01", periods=n, freq="5min", tz="UTC")
    closes = {"BTC": np.full(n, 100.0)}
    trades = [Trade("BTC", "long", i - 1, i, i, 100.0, 99.0, 99.0, "stop", False, False) for i in range(1, n, 2)]
    tr, eq = portfolio(trades, closes, idx, TAKER, start=200.0)
    assert len(tr) == len(trades)                                   # nothing skipped for "no cash"
    assert tr.notional.iloc[-1] == pytest.approx(0.10 * (200 + tr.pnl.iloc[:-1].sum()), rel=1e-6)
    assert eq.iloc[-1] == pytest.approx(200 + tr.pnl.sum())
