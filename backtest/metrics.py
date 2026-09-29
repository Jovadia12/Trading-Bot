"""Performance metrics and regime labels for backtest results."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.engine import AccountResult


def _streaks(wins: np.ndarray) -> tuple[int, int]:
    best_w = best_l = cur_w = cur_l = 0
    for w in wins:
        cur_w, cur_l = (cur_w + 1, 0) if w else (0, cur_l + 1)
        best_w, best_l = max(best_w, cur_w), max(best_l, cur_l)
    return best_w, best_l


def drawdown_stats(equity: pd.Series) -> tuple[float, float]:
    """(max drawdown, average of per-episode max drawdowns), as positive fractions."""
    peak = equity.cummax()
    dd = 1 - equity / peak
    if dd.max() <= 0:
        return 0.0, 0.0
    episodes, cur, in_dd = [], 0.0, False
    for v in dd.to_numpy():
        if v > 0:
            in_dd, cur = True, max(cur, v)
        elif in_dd:
            episodes.append(cur)
            in_dd, cur = False, 0.0
    if in_dd:
        episodes.append(cur)
    return float(dd.max()), float(np.mean(episodes)) if episodes else 0.0


def summarize(res: AccountResult, bars_total: int, bar_seconds: int) -> dict:
    t = res.trades
    out = {"trades": len(t), "skipped_min_order": res.skipped_min_order}
    if t.empty:
        return out | {"profit_factor": np.nan, "net_return": 0.0}
    win = t.net > 0
    gw, gl = t.net[win].sum(), -t.net[~win].sum()
    eq = res.equity
    daily = eq.resample("1D").last().dropna()
    dr = daily.pct_change().dropna()
    years = max((eq.index[-1] - eq.index[0]).total_seconds() / (365.25 * 86400), 1e-9)
    final = float(eq.iloc[-1])
    downside = dr[dr < 0]
    mdd, add = drawdown_stats(eq)
    ws, ls = _streaks(win.to_numpy())
    dur_h = t.bars * bar_seconds / 3600
    return out | {
        "winning": int(win.sum()), "losing": int((~win).sum()), "win_rate": float(win.mean()),
        "avg_win": float(t.net[win].mean()) if win.any() else 0.0,
        "avg_loss": float(t.net[~win].mean()) if (~win).any() else 0.0,
        "avg_win_pct": float(t.ret[win].mean()) if win.any() else 0.0,
        "avg_loss_pct": float(t.ret[~win].mean()) if (~win).any() else 0.0,
        "reward_risk": float(t.net[win].mean() / -t.net[~win].mean()) if win.any() and (~win).any() else np.nan,
        "profit_factor": float(gw / gl) if gl > 0 else np.inf,
        "expectancy_usd": float(t.net.mean()), "expectancy_pct": float(t.ret.mean()),
        "median_trade_pct": float(t.ret.median()),
        "expectancy_r": float(t.r_mult.mean()),
        "gross_profit": float(t.gross.sum()), "fees": float(t.fees.sum()), "slippage": float(t.slippage.sum()),
        "net_profit": float(t.net.sum()), "net_return": final / res.start - 1,
        "cagr": (final / res.start) ** (1 / years) - 1 if final > 0 else -1.0,
        "max_drawdown": mdd, "avg_drawdown": add,
        "sharpe": float(dr.mean() / dr.std() * np.sqrt(365)) if dr.std() > 0 else 0.0,
        "sortino": float(dr.mean() / downside.std() * np.sqrt(365)) if len(downside) > 1 and downside.std() > 0 else 0.0,
        "longest_win_streak": ws, "longest_loss_streak": ls,
        "avg_duration_h": float(dur_h.mean()), "median_duration_h": float(dur_h.median()),
        "exposure": float(t.bars.sum() / bars_total) if bars_total else 0.0,
        "trades_per_year": len(t) / years, "years": years,
        "tstat": float(t.ret.mean() / t.ret.std(ddof=1) * np.sqrt(len(t))) if len(t) > 2 and t.ret.std() > 0 else 0.0,
    }


def regime_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Daily regime labels, lagged one day so they are known at every intraday bar.

    trend: BULL (close > SMA200 and SMA200 rising over 20d), BEAR (close < SMA200 and falling), else SIDEWAYS.
    vol: HIGH / LOW / MID by 30-day realized volatility vs its trailing 365-day 33rd/67th percentiles.
    """
    d = df.close.resample("1D").last().dropna()
    sma = d.rolling(200, min_periods=200).mean()
    slope = sma - sma.shift(20)
    trend = np.where((d > sma) & (slope > 0), "BULL", np.where((d < sma) & (slope < 0), "BEAR", "SIDEWAYS"))
    rv = np.log(d).diff().rolling(30, min_periods=30).std()
    lo, hi = rv.rolling(365, min_periods=180).quantile(0.33), rv.rolling(365, min_periods=180).quantile(0.67)
    vol = np.where(rv > hi, "HIGH_VOL", np.where(rv < lo, "LOW_VOL", "MID_VOL"))
    lab = pd.DataFrame({"trend": trend, "vol": vol}, index=d.index)
    lab.loc[sma.isna(), "trend"] = "UNKNOWN"
    lab.loc[lo.isna() | rv.isna(), "vol"] = "UNKNOWN"
    return lab.shift(1).dropna()


def by_regime(trades: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    day = trades.entry_time.dt.floor("1D")
    lab = labels.reindex(day.values)
    rows = []
    for col in ("trend", "vol"):
        for name in sorted(set(lab[col].dropna())):
            m = (lab[col] == name).to_numpy()
            t = trades[m]
            if t.empty:
                continue
            w = t.net > 0
            gl = -t.net[~w].sum()
            rows.append({"regime": name, "trades": len(t), "win_rate": w.mean(),
                         "profit_factor": t.net[w].sum() / gl if gl > 0 else np.inf,
                         "expectancy_pct": t.ret.mean(), "net_profit": t.net.sum()})
    return pd.DataFrame(rows)
