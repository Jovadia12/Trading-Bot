"""EMA-trend + BOS + Fib + FVG ("Unicorn") study on 5m/15m data. Research only; see FIB_FVG_STUDY.md.

    PAPER_MODE=true python3 -m backtest.fib_fvg_study

Uses research_data/coinbase_<coin>usd_5m.csv.gz for every universe coin that exists (download the others with
`backtest.fetch_coinbase --product <COIN>-USD --tf 5m`). Window: the most recent 365 days of the common data.
Split: first 70% TRAIN (variant selection), last 30% OUT-OF-SAMPLE (one look), plus the selected candidate on the
full 12 months. Writes research_results/fib_fvg/.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.data import REPO_ROOT, data_path, load_candles
from backtest.fib_fvg import (COST_CASES, Costs, Rules, find_signals, indicators_5m, management_15m, portfolio,
                              simulate_trades)

UNIVERSE = ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "LINK", "ADA", "AVAX", "DOT")
OUT = REPO_ROOT / "research_results" / "fib_fvg"
VERSIONS = ("standard", "unicorn")
STOPS = ("struct", "atr1.5", "atr2", "atr2.5")
EXITS = ("A", "B", "R3", "R5")
EXIT_NAMES = {"A": "A: 15m opposite EMA/structure", "B": "B: 15m trailing structure", "R3": "C: 3R target", "R5": "D: 5R target"}
TRAIN_FRAC = 0.70
MIN_TRAIN_TRADES = 20
WARMUP = pd.Timedelta(days=7)
ZERO = Costs("zero_cost_diagnostic", 0.0, 0.0, 0.0, 0.0, 0.0, note="diagnostic only: no fees, no slippage")


# ------------------------------------------------------------------------------------------------- data
def load_universe(days: int = 365):
    raw = {c: load_candles(data_path("5m", f"{c.lower()}usd")) for c in UNIVERSE if data_path("5m", f"{c.lower()}usd").is_file()}
    if not raw:
        return None
    end = min(df.index[-1] for df in raw.values())
    start = (end - pd.Timedelta(days=days)).ceil("1D")
    grid = pd.date_range(start - WARMUP, end, freq="5min")
    frames, notes = {}, []
    for c, df in raw.items():
        d = df.loc[(df.index >= grid[0]) & (df.index <= end)]
        if d.index[0] > start:
            notes.append(f"{c}: data only from {d.index[0]:%Y-%m-%d}")
        missing = grid.difference(d.index)
        d = d.reindex(grid)
        d["close"] = d.close.ffill()
        for k in ("open", "high", "low"):            # missing 5m bars become flat bars at the last close
            d[k] = d[k].fillna(d.close)
        d["volume"] = d.volume.fillna(0.0)
        frames[c] = d.dropna(subset=["close"])
        if len(missing):
            notes.append(f"{c}: {len(missing):,} missing 5m bars ({len(missing) / len(grid):.2%}) filled flat")
    return frames, grid, start, end, notes


# ---------------------------------------------------------------------------------------------- metrics
def metrics(tr: pd.DataFrame, eq: pd.Series, start_bal: float = 200.0) -> dict:
    out = {"ending_balance": float(eq.iloc[-1]), "total_return": float(eq.iloc[-1] / start_bal - 1), "trades": len(tr)}
    peak = np.maximum.accumulate(np.r_[start_bal, eq.to_numpy()])[1:]
    out["max_drawdown"] = float((1 - eq.to_numpy() / peak).max())
    daily = eq.resample("1D").last().ffill().pct_change().dropna()
    out["sharpe"] = float(daily.mean() / daily.std() * math.sqrt(365)) if len(daily) > 20 and daily.std() > 0 else None
    if tr.empty:
        return out | {"win_rate": None, "profit_factor": None, "avg_trade_pct": None, "avg_r": None, "fees": 0.0,
                      "slippage": 0.0, "best": None, "worst": None, "net_pnl": 0.0}
    win = tr.pnl > 0
    gl = -tr.pnl[~win].sum()
    out |= {"win_rate": float(win.mean()), "profit_factor": float(tr.pnl[win].sum() / gl) if gl > 0 else math.inf,
            "avg_trade_pct": float(tr.ret.mean()), "avg_r": float(tr.r_mult.mean()), "fees": float(tr.fees.sum()),
            "slippage": float(tr.slippage.sum()), "net_pnl": float(tr.pnl.sum()),
            "best": f"{tr.loc[tr.pnl.idxmax(), 'coin']} {tr.loc[tr.pnl.idxmax(), 'side']} ${tr.pnl.max():,.2f} ({tr.ret.max():+.2%})",
            "worst": f"{tr.loc[tr.pnl.idxmin(), 'coin']} {tr.loc[tr.pnl.idxmin(), 'side']} ${tr.pnl.min():,.2f} ({tr.ret.min():+.2%})"}
    for side in ("long", "short"):
        g = tr[tr.side == side]
        if len(g):
            w = g.pnl > 0
            gl = -g.pnl[~w].sum()
            out[f"{side}_trades"], out[f"{side}_win_rate"] = len(g), float(w.mean())
            out[f"{side}_pf"] = float(g.pnl[w].sum() / gl) if gl > 0 else math.inf
            out[f"{side}_pnl"] = float(g.pnl.sum())
        else:
            out[f"{side}_trades"], out[f"{side}_win_rate"], out[f"{side}_pf"], out[f"{side}_pnl"] = 0, None, None, 0.0
    return out


def monthly(eq: pd.Series, start_bal: float = 200.0) -> pd.Series:
    m = eq.resample("ME").last()
    r = m.pct_change()
    r.iloc[0] = m.iloc[0] / start_bal - 1
    return r


def fmt(v, pct=False, d=2, money=False):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    if isinstance(v, float) and np.isinf(v):
        return "inf"
    if money:
        return f"${v:,.{d}f}"
    return f"{v * 100:+.{d}f}%" if pct else f"{v:,.{d}f}"


def dd(v):
    return "n/a" if v is None else f"-{v * 100:.2f}%"


def plain(v):
    return "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v * 100:.1f}%"


# ---------------------------------------------------------------------------------------------- running
class Study:
    def __init__(self, frames, grid, start, end, rules: Rules = Rules()):
        self.frames, self.grid, self.r = frames, grid, rules
        self.lo = int(grid.searchsorted(start))
        self.hi = len(grid)
        self.split = int(grid.searchsorted(start + (end - start) * TRAIN_FRAC))
        self.x = {c: indicators_5m(df, rules) for c, df in frames.items()}
        self.m15 = {c: management_15m(df, rules) for c, df in frames.items()}
        self.sig = {(c, v): find_signals(self.x[c], v == "unicorn", rules, lo_i=self.lo)
                    for c in frames for v in VERSIONS}
        self.closes = {c: df.close.to_numpy(float) for c, df in frames.items()}
        self.windows = {"train": (self.lo, self.split), "oos": (self.split, self.hi), "full": (self.lo, self.hi)}

    def run(self, version, stop, exit_, costs, window):
        lo, hi = self.windows[window]
        trades = []
        for c in self.frames:
            trades += simulate_trades(c, self.x[c], self.m15[c], self.sig[(c, version)], stop, exit_, costs,
                                      lo_i=lo, hi_i=hi if hi < len(self.grid) else None, r=self.r)
        tr, eq = portfolio(trades, self.closes, self.grid, costs)
        eq = eq.iloc[lo:hi]
        return tr, eq


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fib + FVG (Unicorn) 5m/15m study -- research only")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    t0 = time.time()
    loaded = load_universe(args.days)
    if loaded is None:
        print("MISSING DATA: no research_data/coinbase_<coin>usd_5m.csv.gz files. No results produced.", file=sys.stderr)
        return 3
    frames, grid, start, end, notes = loaded
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    st = Study(frames, grid, start, end)
    n_sig = {k: len(v) for k, v in st.sig.items()}
    print(f"coins with 5m data: {list(frames)}; window {start:%Y-%m-%d} -> {end:%Y-%m-%d}; split at {grid[st.split]:%Y-%m-%d %H:%M}")
    print(f"signals: {n_sig}")
    rows, details = [], {}
    cases = COST_CASES + [ZERO]
    for costs in cases:
        for v in VERSIONS:
            for s_ in STOPS:
                for e_ in EXITS:
                    row = {"costs": costs.name, "version": v, "stop": s_, "exit": e_}
                    for w in ("train", "oos", "full"):
                        tr, eq = st.run(v, s_, e_, costs, w)
                        m = metrics(tr, eq)
                        row |= {f"{w}_{k}": val for k, val in m.items() if not isinstance(val, str)}
                        details[(costs.name, v, s_, e_, w)] = (tr, eq, m)
                    rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(out / "variants.csv", index=False)
    # selection on TRAIN only, per real cost case (diagnostic zero-cost excluded)
    selected = {}
    for costs in COST_CASES:
        t = table[(table.costs == costs.name) & (table.train_trades >= MIN_TRAIN_TRADES)].copy()
        if t.empty:
            selected[costs.name] = None
            continue
        t["pf_sort"] = t.train_profit_factor.replace(np.inf, 1e9).fillna(0)
        best = t.sort_values(["pf_sort", "train_avg_trade_pct"], ascending=False).iloc[0]
        selected[costs.name] = (best.version, best.stop, best.exit)
    comparison = mcm_comparison(start, end)
    write_report(out, st, table, details, selected, comparison, notes, start, end, grid, time.time() - t0, n_sig)
    for name, sel in selected.items():
        if sel:
            tr, eq, m = details[(name,) + sel + ("full",)]
            tr.to_csv(out / f"trades_selected_{name}_full.csv", index=False)
    print(f"wrote {out / 'REPORT.md'}")
    return 0


def mcm_comparison(start, end) -> list[dict]:
    """The existing multi_crypto_momentum backtest over the same 12 months (daily data, flat start)."""
    try:
        from backtest.mcm_backtest import DEFAULT_ZIP, buy_and_hold, curve_metrics, load_crypto_zip, simulate, trade_metrics
        from strategy.multi_crypto_momentum import MCMParams
    except Exception as exc:  # noqa: BLE001
        return [{"name": f"unavailable ({exc})"}]
    if not Path(DEFAULT_ZIP).is_file():
        return [{"name": "unavailable (research_data/crypto_data.zip missing)"}]
    frames, _ = load_crypto_zip(DEFAULT_ZIP)
    t0, t1 = start.floor("1D"), end.floor("1D")
    res = []
    for label, p in (("multi_crypto_momentum (its spec: 0.05% fee + 0.02% slippage)", MCMParams()),
                     ("multi_crypto_momentum at Coinbase taker 0.90% + 0.02% slippage", MCMParams(fee_rate=0.009))):
        eng, curve, trades = simulate(frames, p, 200.0, t0=t0, t1=t1)
        cm, tm = curve_metrics(curve.equity, 200.0), trade_metrics(trades)
        res.append({"name": label, "ending_balance": cm["final"], "total_return": cm["total_return"],
                    "max_drawdown": cm["max_drawdown"], "sharpe": cm["sharpe"], "trades": tm.get("trades", 0),
                    "profit_factor": tm.get("profit_factor"), "win_rate": tm.get("win_rate")})
    b = curve_metrics(buy_and_hold(frames, ["BTC"], MCMParams(fee_rate=0.009), 200.0, t0=t0, t1=t1), 200.0)
    res.append({"name": "BTC buy-and-hold (0.90% taker in/out)", "ending_balance": b["final"], "total_return": b["total_return"],
                "max_drawdown": b["max_drawdown"], "sharpe": b["sharpe"], "trades": 1, "profit_factor": None, "win_rate": None})
    return res


def _metric_rows(m: dict) -> list[str]:
    return [f"| Ending balance (from $200) | {fmt(m['ending_balance'], money=True)} |",
            f"| Total return | {fmt(m['total_return'], True)} |", f"| Trades | {m['trades']} |",
            f"| Win rate | {fmt(m.get('win_rate'), True, 1).replace('+', '')} |",
            f"| Profit factor | {fmt(m.get('profit_factor'))} |",
            f"| Average trade (on notional) | {fmt(m.get('avg_trade_pct'), True, 3)} |",
            f"| Average R | {fmt(m.get('avg_r'))} |", f"| Max drawdown | {fmt(m['max_drawdown'], True).replace('+', '-')} |",
            f"| Sharpe (daily, ann.) | {fmt(m.get('sharpe'))} |",
            f"| Long: trades / win / PF / P&L | {m.get('long_trades', 0)} / {fmt(m.get('long_win_rate'), True, 1).replace('+', '')} / "
            f"{fmt(m.get('long_pf'))} / {fmt(m.get('long_pnl'), money=True)} |",
            f"| Short: trades / win / PF / P&L | {m.get('short_trades', 0)} / {fmt(m.get('short_win_rate'), True, 1).replace('+', '')} / "
            f"{fmt(m.get('short_pf'))} / {fmt(m.get('short_pnl'), money=True)} |",
            f"| Fees / slippage | {fmt(m.get('fees'), money=True)} / {fmt(m.get('slippage'), money=True)} |",
            f"| Biggest winner | {m.get('best') or 'n/a'} |", f"| Biggest loser | {m.get('worst') or 'n/a'} |"]


def write_report(out, st, table, details, selected, comparison, notes, start, end, grid, secs, n_sig):
    L = ["# EMA trend + BOS + Fibonacci + FVG (Unicorn) -- 5m/15m backtest", "",
         f"Generated {pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC in {secs:.0f}s by `python3 -m backtest.fib_fvg_study`. "
         "Rules: `FIB_FVG_STUDY.md` (objective definitions; the video itself could not be viewed from the research "
         "environment, so the rules implement the written specification).", "",
         f"**Coins with 5m data: {', '.join(st.frames)}** of {', '.join(UNIVERSE)}. "
         + ("**This is NOT the full 10-coin universe** -- the other coins' 5m data were not available." if len(st.frames) < len(UNIVERSE) else ""), "",
         f"Window: {start:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M} UTC (365 days). Train (selection only): first 70% to "
         f"{grid[st.split]:%Y-%m-%d %H:%M}; out-of-sample: the last 30%. 32 variants per cost case = 2 versions x 4 stops x 4 exits.",
         "", f"Signals found (whole window incl. warm-up exclusion): {json.dumps({f'{c}/{v}': n for (c, v), n in n_sig.items()})}", "",
         "Sizing: each entry uses 10% of current equity as notional (1x, cash-capped, shorts as 1x-collateral paper shorts), "
         "one position per coin, $200 start.", ""]
    if notes:
        L += ["Data notes: " + "; ".join(notes), ""]
    L += ["## Cost cases", ""] + [f"- **{c.name}**: {c.note}" for c in COST_CASES + [ZERO]] + [""]
    L += ["## Selected candidate per cost case (chosen on TRAIN only, then one OOS look, then full 12 months)", ""]
    for name, sel in selected.items():
        if sel is None:
            L += [f"### {name}: no variant had >= {MIN_TRAIN_TRADES} train trades -- nothing selected", ""]
            continue
        v, s_, e_ = sel
        L += [f"### {name}: {v}, stop {s_}, exit {EXIT_NAMES[e_]}", "",
              "| Metric | Train (selection) | Out-of-sample (30%) | Full 12 months |", "|---|---|---|---|"]
        cols = [details[(name, v, s_, e_, w)][2] for w in ("train", "oos", "full")]
        rws = [r.split(" | ") for r in [_metric_rows(m) for m in cols][0]]
        all_rows = [_metric_rows(m) for m in cols]
        for i in range(len(all_rows[0])):
            label = all_rows[0][i].split(" | ")[0].lstrip("| ")
            vals = [all_rows[k][i].split(" | ", 1)[1].rstrip(" |") for k in range(3)]
            L.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} |")
        mr = monthly(details[(name, v, s_, e_, "full")][1])
        L += ["", "Monthly returns (full 12 months): " + ", ".join(f"{t:%Y-%m} {x:+.2%}" for t, x in mr.items()), ""]
    L += ["## Every variant (full 12 months; train and OOS profit factor shown for context -- NOT for re-selection)", "",
          "| Costs | Version | Stop | Exit | Trades | Win% | PF | Avg trade | Avg R | Return | Max DD | Fees | Train PF | OOS PF | OOS return |",
          "|" + "---|" * 15]
    for r in table.sort_values(["costs", "version", "stop", "exit"]).to_dict("records"):
        L.append(f"| {r['costs']} | {r['version']} | {r['stop']} | {r['exit']} | {r['full_trades']} | "
                 f"{plain(r.get('full_win_rate'))} | {fmt(r.get('full_profit_factor'))} | {fmt(r.get('full_avg_trade_pct'), True, 3)} | "
                 f"{fmt(r.get('full_avg_r'))} | {fmt(r['full_total_return'], True)} | {dd(r['full_max_drawdown'])} | "
                 f"{fmt(r.get('full_fees'), money=True)} | {fmt(r.get('train_profit_factor'))} | {fmt(r.get('oos_profit_factor'))} | "
                 f"{fmt(r['oos_total_return'], True)} |")
    L += ["", "## Comparison over the same 12 months", "",
          "| Strategy | Ending balance | Return | Max DD | Sharpe | Trades | PF | Win% |", "|---|---|---|---|---|---|---|---|"]
    for name, sel in selected.items():
        if sel:
            m = details[(name,) + sel + ("full",)][2]
            L.append(f"| fib_fvg selected [{name}] {' / '.join(sel)} | {fmt(m['ending_balance'], money=True)} | {fmt(m['total_return'], True)} | "
                     f"{dd(m['max_drawdown'])} | {fmt(m.get('sharpe'))} | {m['trades']} | {fmt(m.get('profit_factor'))} | "
                     f"{plain(m.get('win_rate'))} |")
    for c in comparison:
        L.append(f"| {c['name']} | {fmt(c.get('ending_balance'), money=True)} | {fmt(c.get('total_return'), True)} | "
                 f"{dd(c.get('max_drawdown'))} | {fmt(c.get('sharpe'))} | {c.get('trades', 'n/a')} | "
                 f"{fmt(c.get('profit_factor'))} | {plain(c.get('win_rate'))} |")
    L += ["", "multi_crypto_momentum uses the 10-coin DAILY Binance-format data (crypto_data.zip) over the same dates; "
          "the fib_fvg rows use only the coins listed above.", ""]
    (out / "REPORT.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
