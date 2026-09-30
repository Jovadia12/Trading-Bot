"""Backtest for `multi_crypto_momentum` on DAILY SPOT OHLC data used as a PROXY for perpetual trading.

    PAPER_MODE=true python3 -m backtest.mcm_backtest --data research_data/crypto_data.zip

The data are daily SPOT candles. They are NOT perpetual-futures data: no funding payments, no perp basis, no
order-book depth. Shorts are simulated on spot prices with 1x cash collateral. Every report says so.

Rules are fixed in strategy/multi_crypto_momentum.py (see MULTI_CRYPTO_MOMENTUM.md); nothing is optimised.
Outputs: research_results/multi_crypto_momentum/ (REPORT.md, trades.csv, equity_curve.csv, equity_curve.svg,
summary.json).
"""
from __future__ import annotations

import argparse
import html
import io
import json
import math
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.data import REPO_ROOT
from strategy.multi_crypto_momentum import (LONG, SHORT, UNIVERSE, MCMEngine, MCMParams, build_states,
                                            params_dict)

DEFAULT_ZIP = REPO_ROOT / "research_data" / "crypto_data.zip"
OUT = REPO_ROOT / "research_results" / "multi_crypto_momentum"
DATA_LABEL = "DAILY SPOT OHLC used as a PROXY for perpetual trading (no funding, no perp basis, no order book)"
OOS_FRAC = 0.15          # project convention: chronological 70/15/15, OOS = last 15% of the span
QUOTES = ("USDT", "USDC", "BUSD", "USD", "EUR", "PERP", "")


class DataError(ValueError):
    pass


# ------------------------------------------------------------------------------------------- loading
def _coin_from_name(name: str) -> str | None:
    tokens = [t for t in re.split(r"[^A-Z0-9]+", Path(name).stem.upper()) if t]
    hits = set()
    for tok in tokens:
        for c in UNIVERSE:
            if tok == c or (tok.startswith(c) and tok[len(c):] in QUOTES):
                hits.add(c)
    return hits.pop() if len(hits) == 1 else None


def _col(df: pd.DataFrame, *names) -> str | None:
    low = {c.strip().lower(): c for c in df.columns}
    for n in names:
        if n in low:
            return low[n]
    return None


def _normalise(raw: pd.DataFrame, where: str) -> pd.DataFrame:
    tcol = _col(raw, "date", "time", "timestamp", "datetime", "open_time", "opentime", "day", "snapped_at")
    cols = {k: _col(raw, k) for k in ("open", "high", "low", "close")}
    if tcol is None or any(v is None for v in cols.values()):
        raise DataError(f"{where}: need a date/time column and open/high/low/close columns; got {list(raw.columns)}")
    t = raw[tcol]
    if pd.api.types.is_numeric_dtype(t):
        unit = "ms" if t.dropna().abs().median() > 1e11 else "s"
        ts = pd.to_datetime(t, unit=unit, utc=True)
    else:
        ts = pd.to_datetime(t, utc=True, format="mixed")
    df = pd.DataFrame({k: pd.to_numeric(raw[v], errors="coerce") for k, v in cols.items()})
    vcol = _col(raw, "volume", "vol", "volume_usd", "total_volume")
    df["volume"] = pd.to_numeric(raw[vcol], errors="coerce") if vcol else np.nan
    df.index = ts.dt.floor("1D")
    df = df.dropna(subset=["open", "high", "low", "close"]).sort_index()
    if df.index.duplicated().any():
        raise DataError(f"{where}: more than one row per UTC day -- this loader expects DAILY candles")
    return df


BINANCE_KLINE_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
                         "trades", "taker_base_volume", "taker_quote_volume", "ignore"]


def _read_member(blob: bytes, name: str) -> pd.DataFrame:
    """CSV, or JSON: a list of Binance kline arrays [open_time_ms, open, high, low, close, volume, close_time_ms, ...]
    or a list of objects with named fields."""
    if name.lower().endswith(".csv"):
        return pd.read_csv(io.BytesIO(blob))
    data = json.loads(blob)
    if isinstance(data, dict):
        data = data.get("data") or data.get("klines") or data.get("candles") or []
    if not isinstance(data, list) or not data:
        raise DataError(f"{name}: JSON is not a non-empty list of candles")
    if isinstance(data[0], list):
        if len(data[0]) < 6:
            raise DataError(f"{name}: kline arrays need at least [open_time, open, high, low, close, volume]")
        df = pd.DataFrame([row[:12] for row in data], columns=BINANCE_KLINE_COLUMNS[:min(12, len(data[0]))])
        if "close_time" in df:   # daily klines must span one UTC day
            span = (pd.to_numeric(df.close_time) - pd.to_numeric(df.open_time) + 1) / 86_400_000
            if not np.allclose(span, 1.0):
                raise DataError(f"{name}: klines are not 1-day candles (DAILY data required)")
        return df
    return pd.DataFrame(data)


def load_crypto_zip(path: Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Return {coin: daily OHLC DataFrame (UTC day index)} for the 10-coin universe, plus notes.
    Accepts one CSV per coin (coin recognised from the file name, e.g. BTC.csv, BTC-USD.csv, btcusdt_1d.csv)
    or CSVs with a symbol/ticker/coin column. Refuses anything ambiguous instead of guessing."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    frames: dict[str, pd.DataFrame] = {}
    notes: list[str] = []
    with zipfile.ZipFile(path) as z:
        members = [m for m in z.namelist() if m.lower().endswith((".csv", ".json"))
                   and not Path(m).name.startswith("._")]
        if not members:
            raise DataError(f"{path.name}: no CSV or JSON files inside")
        for m in sorted(members):
            raw = _read_member(z.read(m), m)
            scol = _col(raw, "symbol", "ticker", "coin", "asset", "base")
            if scol is not None:
                for sym, g in raw.groupby(scol):
                    coin = _coin_from_name(str(sym))
                    if coin is None:
                        notes.append(f"ignored symbol {sym!r} in {m} (not in the universe)")
                        continue
                    if coin in frames:
                        raise DataError(f"{coin} appears in more than one place ({m})")
                    frames[coin] = _normalise(g, f"{m}[{sym}]")
                continue
            coin = _coin_from_name(m)
            if coin is None:
                notes.append(f"ignored {m} (could not map the file name to exactly one universe coin)")
                continue
            if coin in frames:
                raise DataError(f"{coin} appears in more than one file ({m})")
            frames[coin] = _normalise(raw, m)
    missing = [c for c in UNIVERSE if c not in frames]
    if missing:
        notes.append(f"MISSING coins (excluded, not substituted): {', '.join(missing)}")
    if "BTC" not in frames:
        raise DataError("BTC is required (regime filter for all altcoins)")
    return {c: frames[c] for c in UNIVERSE if c in frames}, notes


def quality(frames: dict) -> pd.DataFrame:
    rows = []
    for c, df in frames.items():
        days = (df.index[-1] - df.index[0]).days + 1
        bad = ((df.high < df[["open", "close"]].max(axis=1)) | (df.low > df[["open", "close"]].min(axis=1))).sum()
        rows.append({"coin": c, "first": df.index[0].date(), "last": df.index[-1].date(), "rows": len(df),
                     "missing_days": days - len(df), "bad_ohlc_rows": int(bad),
                     "nonpositive_rows": int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------ simulation
def simulate(frames: dict, p: MCMParams, start: float = 200.0, t0=None, t1=None):
    """Walk the union calendar. On each date: execute pending orders at the OPEN of coins that have a candle that
    day (next available candle), then evaluate that day's COMPLETED candles. Only signals from closes inside
    [t0, t1] are acted on (flat start, like the project's window isolation). Open positions are closed at the
    last close (reason 'end_of_data') so trade statistics are complete."""
    states = build_states(frames, p)
    recs = {c: s.to_dict("index") for c, s in states.items()}
    opens = {c: df.open.to_dict() for c, df in frames.items()}
    dates = sorted(set().union(*[set(df.index) for df in frames.values()]))
    if t0 is not None:
        dates = [d for d in dates if d >= t0]
    if t1 is not None:
        dates = [d for d in dates if d <= t1]
    eng = MCMEngine(start, p, enabled=set(frames))
    eq, gross, npos = [], [], []
    for d in dates:
        eng.on_open(d, {c: opens[c][d] for c in frames if d in opens[c]})
        eng.on_close(d, {c: recs[c][d] for c in frames if d in recs[c]})
        snap = eng.snapshot()
        eq.append(snap["equity"]); gross.append(snap["gross_exposure"]); npos.append(len(snap["positions"]))
    last = dates[-1]
    for c in list(eng.pf.positions):
        eng.pf.close(c, eng.last_price[c], last, "end_of_data (closed at final close)")
    eq[-1] = eng.equity()
    curve = pd.DataFrame({"equity": eq, "gross_exposure": gross, "positions": npos}, index=pd.DatetimeIndex(dates))
    trades = pd.DataFrame(eng.pf.trades)
    return eng, curve, trades


def buy_and_hold(frames: dict, coins, p: MCMParams, start: float, t0=None, t1=None) -> pd.Series:
    """Equal weight: start/len(coins) per coin, bought at each coin's first open inside the window (cash until
    then), same fee + slippage; marked at closes; sell costs applied on the final value."""
    dates = sorted(set().union(*[set(frames[c].index) for c in coins]))
    dates = [d for d in dates if (t0 is None or d >= t0) and (t1 is None or d <= t1)]
    idx = pd.DatetimeIndex(dates)
    per = start / len(coins)
    total = pd.Series(0.0, index=idx)
    for c in coins:
        df = frames[c].loc[(frames[c].index >= idx[0]) & (frames[c].index <= idx[-1])]
        if df.empty:
            total += per
            continue
        cost = 1 + p.fee_rate
        qty = per / (df.open.iloc[0] * (1 + p.slippage_rate) * cost)
        val = (qty * df.close).reindex(idx).ffill()
        val[idx < df.index[0]] = per
        val.iloc[-1] = qty * df.close.iloc[-1] * (1 - p.slippage_rate) * (1 - p.fee_rate)
        total += val.fillna(per)
    return total


# --------------------------------------------------------------------------------------------- metrics
def curve_metrics(eq: pd.Series, start: float) -> dict:
    daily = eq.resample("1D").last().ffill()
    r = daily.pct_change().dropna()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    final = float(eq.iloc[-1])
    peak = np.maximum.accumulate(np.r_[start, eq.to_numpy()])[1:]
    return {"start": start, "final": final, "total_return": final / start - 1,
            "cagr": (final / start) ** (1 / years) - 1 if final > 0 else -1.0,
            "max_drawdown": float((1 - eq.to_numpy() / peak).max()),
            "sharpe": float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else 0.0, "years": years}


def trade_metrics(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"trades": 0}
    win = t.pnl > 0
    gl = -t.pnl[~win].sum()
    streak = best = 0
    for w in t.sort_values("exit_time").pnl > 0:
        streak = 0 if w else streak + 1
        best = max(best, streak)
    return {"trades": len(t), "win_rate": float(win.mean()), "profit_factor": float(t.pnl[win].sum() / gl) if gl > 0 else math.inf,
            "net_pnl": float(t.pnl.sum()), "avg_trade_usd": float(t.pnl.mean()), "avg_trade_pct": float(t.ret_on_notional.mean()),
            "fees": float(t.fees.sum()), "slippage": float(t.slippage.sum()), "longest_losing_streak": best,
            "avg_days": float(t.days.mean()), "winners": int(win.sum()), "losers": int((~win).sum())}


def group_table(t: pd.DataFrame, by) -> pd.DataFrame:
    if t.empty:
        return pd.DataFrame()
    rows = []
    for k, g in t.groupby(by, sort=False):
        m = trade_metrics(g)
        rows.append({"group": k, **{x: m[x] for x in ("trades", "win_rate", "profit_factor", "net_pnl", "avg_trade_pct", "fees")}})
    return pd.DataFrame(rows)


def fmt(x, pct=False, d=2):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    if isinstance(x, float) and np.isinf(x):
        return "inf"
    return f"{x * 100:,.{d}f}%" if pct else f"{x:,.{d}f}"


# ------------------------------------------------------------------------------------------- chart
_CSS = """
.viz-root{--surface-1:#fcfcfb;--text-primary:#0b0b0b;--text-secondary:#52514e;--grid:#e4e3df;
 --series-1:#2a78d6;--series-2:#eb6834;--series-3:#1baf7a;font-family:system-ui,sans-serif}
@media (prefers-color-scheme: dark){.viz-root{--surface-1:#1a1a19;--text-primary:#ffffff;--text-secondary:#c3c2b7;
 --grid:#3a3a37;--series-1:#3987e5;--series-2:#d95926;--series-3:#199e70}}
"""


def equity_svg(series: dict[str, pd.Series], title: str, short: dict | None = None, w=960, h=420) -> str:
    """Static line chart on a log scale (one axis), legend + direct end labels, monthly hover points."""
    ml, mr, mt, mb = 64, 150, 60, 36
    short = short or {}
    esc = lambda x: html.escape(str(x), quote=True)          # every text node is XML-escaped
    allv = pd.concat(series.values())
    lo, hi = math.log10(max(allv.min(), 1e-6)), math.log10(allv.max())
    lo, hi = math.floor(lo * 2) / 2, math.ceil(hi * 2) / 2 or lo + 0.5
    t0, t1 = min(s.index[0] for s in series.values()), max(s.index[-1] for s in series.values())
    X = lambda t: ml + (t - t0).total_seconds() / max((t1 - t0).total_seconds(), 1) * (w - ml - mr)
    Y = lambda v: mt + (hi - math.log10(max(v, 1e-6))) / (hi - lo) * (h - mt - mb)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" class="viz-root" viewBox="0 0 {w} {h}" role="img" '
           f'aria-label="{esc(title)}"><style>{_CSS}</style><rect width="{w}" height="{h}" fill="var(--surface-1)"/>',
           f'<text x="{ml}" y="24" fill="var(--text-primary)" font-size="15" font-weight="600">{esc(title)}</text>']
    ticks = [m * 10 ** k for k in range(int(math.floor(lo)) - 1, int(math.ceil(hi)) + 1) for m in (1, 2, 5)]
    ticks = [v for v in ticks if lo - 1e-9 <= math.log10(v) <= hi + 1e-9]
    if len(ticks) > 9:                                       # keep the axis quiet on long ranges
        ticks = [v for v in ticks if str(int(v))[0] in "15"]
    for v in ticks:
        y = Y(v)
        out.append(f'<line x1="{ml}" x2="{w - mr}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--grid)" stroke-width="1"/>'
                   f'<text x="{ml - 8}" y="{y + 4:.1f}" text-anchor="end" fill="var(--text-secondary)" font-size="11">${v:,.0f}</text>')
    for yr in range(t0.year + 1, t1.year + 1):
        x = X(pd.Timestamp(f"{yr}-01-01", tz=t0.tz))
        out.append(f'<text x="{x:.1f}" y="{h - 12}" text-anchor="middle" fill="var(--text-secondary)" font-size="11">{yr}</text>')
    lab_y = []
    for i, (name, s) in enumerate(series.items(), start=1):
        s = s.resample("1D").last().ffill()
        pts = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in s.items())
        out.append(f'<polyline fill="none" stroke="var(--series-{i})" stroke-width="2" stroke-linejoin="round" points="{pts}"/>')
        for t, v in s.resample("ME").last().items():
            out.append(f'<circle cx="{X(t):.1f}" cy="{Y(v):.1f}" r="6" fill="transparent"><title>{esc(name)} '
                       f'{t:%Y-%m}: ${v:,.2f}</title></circle>')
        ly = Y(s.iloc[-1])
        while any(abs(ly - o) < 14 for o in lab_y):
            ly += 14
        lab_y.append(ly)
        out.append(f'<text x="{w - mr + 8}" y="{ly + 4:.1f}" fill="var(--text-primary)" font-size="12">'
                   f'<tspan fill="var(--series-{i})">&#9644;</tspan> {esc(short.get(name, name))} ${s.iloc[-1]:,.0f}</text>')
        out.append(f'<rect x="{ml + (i - 1) * 210}" y="40" width="14" height="4" rx="2" fill="var(--series-{i})"/>'
                   f'<text x="{ml + (i - 1) * 210 + 20}" y="46" fill="var(--text-secondary)" font-size="12">{esc(name)}</text>')
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------------------------------- main
def run_all(frames, p, start):
    t_first = min(df.index[0] for df in frames.values())
    t_last = max(df.index[-1] for df in frames.values())
    oos_start = (t_first + (t_last - t_first) * (1 - OOS_FRAC)).ceil("1D")
    full = simulate(frames, p, start)
    oos = simulate(frames, p, start, t0=oos_start)
    coins = list(frames)
    bench = {"BTC buy-and-hold": {"full": buy_and_hold(frames, ["BTC"], p, start),
                                  "oos": buy_and_hold(frames, ["BTC"], p, start, t0=oos_start)},
             f"Equal-weight buy-and-hold ({len(coins)} coins)": {"full": buy_and_hold(frames, coins, p, start),
                                                                 "oos": buy_and_hold(frames, coins, p, start, t0=oos_start)}}
    return {"oos_start": oos_start, "t_first": t_first, "t_last": t_last, "full": full, "oos": oos, "bench": bench}


def write_report(out: Path, frames, notes, p, start, res, data_path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    eng, curve, trades = res["full"]
    oeng, ocurve, otrades = res["oos"]
    cm, tm = curve_metrics(curve.equity, start), trade_metrics(trades)
    ocm, otm = curve_metrics(ocurve.equity, start), trade_metrics(otrades)
    expo = float((curve.gross_exposure / curve.equity).replace([np.inf, -np.inf], np.nan).mean())
    invested = float((curve.positions > 0).mean())
    ev = pd.DataFrame(eng.events)
    rej = ev[ev.kind == "signal_rejected"].reason.value_counts().to_dict() if len(ev) else {}
    trades.to_csv(out / "trades.csv", index=False)
    eq_df = curve.copy()
    for name, b in res["bench"].items():
        eq_df[name] = b["full"].reindex(eq_df.index).ffill()
    eq_df.to_csv(out / "equity_curve.csv", index_label="date")
    (out / "equity_curve.svg").write_text(equity_svg(
        {"multi_crypto_momentum": curve.equity, **{k: v["full"] for k, v in res["bench"].items()}},
        f"Equity from ${start:,.0f} (log scale) - spot-OHLC proxy for perps",
        {"multi_crypto_momentum": "Strategy", "BTC buy-and-hold": "BTC B&H",
         **{k: "Equal-wt B&H" for k in res["bench"] if k.startswith("Equal")}}))
    L = ["# multi_crypto_momentum - backtest", "",
         f"**Data: {DATA_LABEL}.** Source: `{data_path}`. Shorts are simulated on spot prices with 1x cash collateral; "
         "perpetual funding, basis, borrow and liquidation mechanics are NOT modelled.", "",
         f"Rules fixed in `strategy/multi_crypto_momentum.py` / `MULTI_CRYPTO_MOMENTUM.md`; parameters not optimised: "
         f"`{json.dumps(params_dict(p))}`. Start ${start:,.2f}.", "",
         f"Period {res['t_first']:%Y-%m-%d} -> {res['t_last']:%Y-%m-%d}. OOS (project convention: last 15% of the span, "
         f"flat start, own ${start:,.0f}) from {res['oos_start']:%Y-%m-%d}.", ""]
    if notes:
        L += ["**Data notes:** " + "; ".join(notes), ""]
    q = quality(frames)
    L += ["## Data quality", "", "| " + " | ".join(q.columns) + " |", "|" + "---|" * len(q.columns)]
    L += ["| " + " | ".join(str(v) for v in r) + " |" for r in q.itertuples(index=False)]
    L += ["",
          "## Headline (full history)", "", "| Metric | Value |", "|---|---|",
          f"| Total return | {fmt(cm['total_return'], True)} |", f"| Ending balance from ${start:,.0f} | ${fmt(cm['final'])} |",
          f"| Annualized return | {fmt(cm['cagr'], True)} |", f"| Max drawdown | {fmt(cm['max_drawdown'], True)} |",
          f"| Sharpe (daily, ann.) | {fmt(cm['sharpe'])} |", f"| Profit factor | {fmt(tm.get('profit_factor'))} |",
          f"| Win rate | {fmt(tm.get('win_rate'), True, 1)} |", f"| Trades | {tm.get('trades', 0)} |",
          f"| Average trade | ${fmt(tm.get('avg_trade_usd'))} ({fmt(tm.get('avg_trade_pct'), True)} of notional) |",
          f"| Fees paid | ${fmt(tm.get('fees'))} (slippage ${fmt(tm.get('slippage'))}) |",
          f"| Exposure | avg gross {fmt(expo, True, 1)} of equity; invested on {fmt(invested, True, 1)} of days |",
          f"| Longest losing streak | {tm.get('longest_losing_streak', 0)} trades |",
          f"| Signals rejected | {rej or 'none'} |",
          f"| Marks where a 1x short lost more than its collateral | {eng.short_collateral_breach_marks} |", "",
          "## OOS (flat start)", "", "| Metric | Value |", "|---|---|",
          f"| OOS return | {fmt(ocm['total_return'], True)} (${fmt(ocm['final'])}) |", f"| OOS PF | {fmt(otm.get('profit_factor'))} |",
          f"| OOS max drawdown | {fmt(ocm['max_drawdown'], True)} |", f"| OOS trades | {otm.get('trades', 0)} |",
          f"| OOS Sharpe | {fmt(ocm['sharpe'])} |", "",
          "## Benchmarks", "", "| | Full: end $ | Full return | Full CAGR | Full max DD | Full Sharpe | OOS return | OOS max DD |",
          "|---|---|---|---|---|---|---|---|",
          f"| multi_crypto_momentum | ${fmt(cm['final'])} | {fmt(cm['total_return'], True)} | {fmt(cm['cagr'], True)} | "
          f"{fmt(cm['max_drawdown'], True)} | {fmt(cm['sharpe'])} | {fmt(ocm['total_return'], True)} | {fmt(ocm['max_drawdown'], True)} |"]
    for name, b in res["bench"].items():
        f, o = curve_metrics(b["full"], start), curve_metrics(b["oos"], start)
        L.append(f"| {name} | ${fmt(f['final'])} | {fmt(f['total_return'], True)} | {fmt(f['cagr'], True)} | "
                 f"{fmt(f['max_drawdown'], True)} | {fmt(f['sharpe'])} | {fmt(o['total_return'], True)} | {fmt(o['max_drawdown'], True)} |")
    L += ["", "Equal-weight buy-and-hold: $%.0f per coin bought at each coin's first available open (cash until then)." % (start / len(frames)), ""]

    def table(df, title):
        if df.empty:
            return [f"## {title}", "", "no trades", ""]
        rows = [f"## {title}", "", "| | Trades | Win% | PF | Net P&L $ | Avg trade % | Fees $ |", "|---|---|---|---|---|---|---|"]
        rows += [f"| {r['group']} | {r['trades']} | {fmt(r['win_rate'], True, 1)} | {fmt(r['profit_factor'])} | "
                 f"{fmt(r['net_pnl'])} | {fmt(r['avg_trade_pct'], True)} | {fmt(r['fees'])} |" for r in df.to_dict("records")]
        return rows + [""]

    L += table(group_table(trades, "coin"), "Results by coin")
    L += table(group_table(trades, "side"), "Long vs short")
    yr = curve.equity.resample("YE").last()
    yr_ret = yr.pct_change()
    yr_ret.iloc[0] = yr.iloc[0] / start - 1
    by_year = group_table(trades.assign(year=trades.exit_time.dt.year) if len(trades) else trades, "year")
    btc_y = res["bench"]["BTC buy-and-hold"]["full"].resample("YE").last()
    btc_r = btc_y.pct_change(); btc_r.iloc[0] = btc_y.iloc[0] / start - 1
    L += ["## Results by year", "", "| Year | Strategy return | BTC B&H return | Trades (by exit) | PF | Net P&L $ |", "|---|---|---|---|---|---|"]
    for ts, v in yr_ret.items():
        g = by_year[by_year.group == ts.year] if len(by_year) else by_year
        r = g.iloc[0].to_dict() if len(g) else {}
        L.append(f"| {ts.year} | {fmt(v, True)} | {fmt(btc_r.get(ts), True)} | {r.get('trades', 0)} | "
                 f"{fmt(r.get('profit_factor'))} | {fmt(r.get('net_pnl'))} |")
    L += ["", "## Equity curve", "", "![equity curve](equity_curve.svg)", "",
          "Data: `equity_curve.csv` (strategy equity, gross exposure, open positions, benchmarks); trades: `trades.csv`.", ""]
    (out / "REPORT.md").write_text("\n".join(L))
    summary = {"data_label": DATA_LABEL, "params": params_dict(p), "start": start, "full": {**cm, **tm},
               "oos_start": str(res["oos_start"].date()), "oos": {**ocm, **otm}, "rejections": rej,
               "exposure_avg_gross": expo, "days_invested": invested, "notes": notes}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="multi_crypto_momentum backtest (spot-OHLC proxy for perps)")
    ap.add_argument("--data", default=str(DEFAULT_ZIP))
    ap.add_argument("--start", type=float, default=200.0)
    ap.add_argument("--fee", type=float, default=MCMParams.fee_rate, help="fee per side (fraction), default 0.0005")
    ap.add_argument("--slippage", type=float, default=MCMParams.slippage_rate, help="slippage per side, default 0.0002")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    path = Path(args.data)
    if not path.is_file():
        print(f"MISSING DATA: {path} not found. Put crypto_data.zip there (or pass --data). No results were produced.",
              file=sys.stderr)
        return 3
    frames, notes = load_crypto_zip(path)
    p = MCMParams(fee_rate=args.fee, slippage_rate=args.slippage)
    res = run_all(frames, p, args.start)
    s = write_report(Path(args.out), frames, notes, p, args.start, res, path.name)
    print(f"{DATA_LABEL}\nfull: return {fmt(s['full']['total_return'], True)} end ${fmt(s['full']['final'])} "
          f"PF {fmt(s['full'].get('profit_factor'))} maxDD {fmt(s['full']['max_drawdown'], True)}; "
          f"OOS return {fmt(s['oos']['total_return'], True)} PF {fmt(s['oos'].get('profit_factor'))}\n"
          f"wrote {Path(args.out) / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
