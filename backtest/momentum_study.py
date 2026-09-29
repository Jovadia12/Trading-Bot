"""BTC Momentum Breakout study (pre-registered: MOMENTUM_BREAKOUT_PROTOCOL.md).

    PAPER_MODE=true python3 -m backtest.momentum_study

Versions A (4h), B (1h), C (15m) x execution {taker, maker}. Per candidate: parameters selected on TRAIN only
(B is a single pre-specified configuration) -> VALIDATION gate -> one OOS look -> rolling walk-forward ->
robustness checks -> pre-registered acceptance. Writes research_results/momentum/. Earlier studies untouched.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.costs import ZERO, default_costs
from backtest.daily_study import (_v, buy_and_hold, daily_sharpe, fmt, key, trade_concentration, unkey,
                                  year_dependence, year_table)
from backtest.data import REPO_ROOT, TF_SECONDS, data_path, load_timeframe, quality_report
from backtest.metrics import by_regime, regime_labels, summarize
from backtest.momentum_engine import generate_positions, simulate_positions
from backtest.strategies_momentum import VERSIONS, Version

OUT = REPO_ROOT / "research_results" / "momentum"
MODES = ("taker", "maker")


@dataclass(frozen=True)
class MomentumProtocol:
    train_frac: float = 0.70
    val_frac: float = 0.15
    risk: float = 0.01                    # research / selection runs
    start_equity: float = 10_000.0
    val_pf_gate: float = 1.20
    accept_pf: float = 1.50
    marginal_pf: float = 1.25
    max_dd_2pct: float = 0.30             # full history, $200 start at 2% risk
    best_year_max_share: float = 0.50
    neighbour_pf: float = 1.20
    wf_train_days: int = 730
    wf_test_days: int = 182
    paper_start: float = 200.0
    paper_risks: tuple = (0.02, 0.05, 0.10)
    penetration: float = 0.001            # maker fills must trade THROUGH the limit by 0.10%


P = MomentumProtocol()


def splits(df):
    t0, t1 = df.index[0], df.index[-1]
    span = t1 - t0
    tr = (t0, t0 + span * P.train_frac)
    va = (tr[1], t0 + span * (P.train_frac + P.val_frac))
    return {"train": tr, "val": va, "oos": (va[1], t1 + pd.Timedelta(seconds=1)), "full": None}


class Runner:
    """Caches signals per (version, params) so each is computed once on the full frame."""

    def __init__(self, df, version: Version, costs):
        self.df, self.v, self.costs, self._sig = df, version, costs, {}

    def sig(self, combo):
        k = key(combo)
        if k not in self._sig:
            self._sig[k] = self.v.build(self.df, combo)
        return self._sig[k]

    def run(self, combo, window, mode, costs=None, risk=None, start=None, stats=None):
        pos = generate_positions(self.df, self.sig(combo), window, mode, P.penetration, stats)
        res = simulate_positions(self.df, pos, costs or self.costs, start or P.start_equity, risk or P.risk)
        if window is None:
            return res, len(self.df)
        lo, hi = self.df.index.searchsorted(window[0]), self.df.index.searchsorted(window[1])
        res.equity = res.equity.iloc[lo:hi]
        return res, hi - lo

    def metrics(self, res, bars):
        m = summarize(res, bars, TF_SECONDS[self.v.tf])
        if m.get("trades"):
            m["sharpe"], m["sortino"] = daily_sharpe(res.equity)
        return m

    def grid_neighbours(self, combo):
        out = []
        for k, vals in self.v.grid.items():
            i = vals.index(combo[k])
            out += [{**combo, k: vals[j]} for j in (i - 1, i + 1) if 0 <= j < len(vals)]
        return out

    def select(self, window, mode, min_trades):
        rows = {}
        for combo in self.v.combos():
            res, bars = self.run(combo, window, mode)
            rows[key(combo)] = (combo, self.metrics(res, bars))
        table = []
        for k, (combo, m) in rows.items():
            nb = [rows[key(c)][1] for c in self.grid_neighbours(combo)]
            eligible = m["trades"] >= min_trades and (m.get("profit_factor") or 0) > 1.0
            score = np.nanmean([m.get("tstat", 0)] + [x.get("tstat", 0) for x in nb])
            table.append({"mode": mode, "version": self.v.key, "params": k, "train_trades": m["trades"],
                          "train_pf": m.get("profit_factor"), "train_expectancy_pct": m.get("expectancy_pct"),
                          "train_tstat": m.get("tstat"), "eligible": eligible, "score": score if eligible else -np.inf})
        t = pd.DataFrame(table).sort_values("score", ascending=False, kind="stable")
        if not self.v.grid:            # B: one pre-specified configuration, no selection
            return {}, t
        best = t.iloc[0]
        return (unkey(best.params) if np.isfinite(best.score) else None), t

    def walk_forward(self, mode):
        df = self.df
        start, end = df.index[0], df.index[-1]
        folds, pos, t0 = [], [], start
        while True:
            tr_end = t0 + pd.Timedelta(days=P.wf_train_days)
            if tr_end >= end:
                break
            te_end = min(tr_end + pd.Timedelta(days=P.wf_test_days), end + pd.Timedelta(seconds=1))
            chosen, _ = self.select((t0, tr_end), mode, self.v.wf_min_train_trades)
            if chosen is not None:
                pos += generate_positions(df, self.sig(chosen), (tr_end, te_end), mode, P.penetration)
            folds.append({"train": f"{t0:%Y-%m-%d}..{tr_end:%Y-%m-%d}", "test": f"{tr_end:%Y-%m-%d}..{te_end:%Y-%m-%d}",
                          "params": key(chosen) if chosen is not None else "none eligible"})
            if te_end > end:
                break
            t0 += pd.Timedelta(days=P.wf_test_days)
        pos.sort(key=lambda p: p.entry_i)
        res = simulate_positions(df, pos, self.costs, P.start_equity, P.risk)
        first = df.index.searchsorted(start + pd.Timedelta(days=P.wf_train_days))
        res.equity = res.equity.iloc[first:]
        return self.metrics(res, len(df) - first), folds


def acceptance(r: dict, v: Version) -> tuple[str, list[str]]:
    hard, soft = [], []
    if not r.get("val_pass"): hard.append("validation gate")
    if not _v(r, "oos_trades", 0) >= v.min_oos_trades: hard.append(f"< {v.min_oos_trades} OOS trades")
    if not _v(r, "oos_expectancy_pct", -1) > 0: hard.append("OOS expectancy <= 0")
    if not _v(r, "oos_net_return", -1) > 0: hard.append("OOS net return <= 0")
    if not _v(r, "wf_trades", 0) >= v.min_wf_trades: hard.append(f"< {v.min_wf_trades} walk-forward trades")
    if not _v(r, "wf_expectancy_pct", -1) > 0: hard.append("walk-forward expectancy <= 0")
    for k, name in (("oos_profit_factor", "OOS PF"), ("wf_profit_factor", "walk-forward PF")):
        pf = _v(r, k, 0)
        if pf < P.marginal_pf: hard.append(f"{name} < {P.marginal_pf}")
        elif pf < P.accept_pf: soft.append(f"{name} {pf:.2f} < {P.accept_pf}")
    if not _v(r, "full_profit_factor", 0) > 1.0: hard.append("full-history PF after costs <= 1")
    if not _v(r, "sim_2pct_max_drawdown", 1) <= P.max_dd_2pct: hard.append(f"max DD at 2% risk > {P.max_dd_2pct:.0%}")
    if not _v(r, "best_year_share_of_net", 9) <= P.best_year_max_share: hard.append("best year > 50% of net profit")
    if not _v(r, "pf_without_best_year", 0) > 1.0: hard.append("PF without best year <= 1")
    if not _v(r, "neighbour_median_pf", 0) >= P.neighbour_pf: hard.append(f"nearby-parameter median PF < {P.neighbour_pf}")
    if not _v(r, "net_without_topk", -1) > 0: hard.append("unprofitable without its best few trades")
    if r.get("mode") == "maker" and not _v(r, "taker_check_pf", 0) > 1.0:
        hard.append("same params unprofitable under taker costs")
    if hard:
        return "FAIL", hard + soft
    return ("MARGINAL", soft) if soft else ("PASS", [])


def evaluate(rn: Runner, mode: str, sp: dict, log):
    v, df = rn.v, rn.df
    chosen, table = rn.select(sp["train"], mode, v.min_train_trades)
    row = {"mode": mode, "version": v.key, "tf": v.tf, "params": key(chosen) if chosen is not None else None}
    extra = {}
    if chosen is None:
        row["status"], row["reasons"] = "FAIL", f"no grid setting with >= {v.min_train_trades} train trades and PF > 1 after costs"
        log(f"  [{mode}] {v.key}: no eligible parameters on train")
        return row, table, extra
    row["full_params"] = key({k: x for k, x in v.params(chosen).items() if k != "bar_hours"})
    for label, w in sp.items():
        st = {}
        res, bars = rn.run(chosen, w, mode, stats=st)
        m = rn.metrics(res, bars)
        row.update({f"{label}_{k}": x for k, x in m.items() if not isinstance(x, (list, dict))})
        g, gb = rn.run(chosen, w, mode, costs=ZERO)
        row[f"{label}_gross_pf"] = rn.metrics(g, gb).get("profit_factor")
        row[f"{label}_partial_rate"] = st["partials"] / len(res.trades) if len(res.trades) else np.nan
        row[f"{label}_time_exit_rate"] = st["time_exits"] / len(res.trades) if len(res.trades) else np.nan
        if mode == "maker":
            row[f"{label}_missed_entry_rate"] = st["missed_entries"] / st["entry_signals"] if st["entry_signals"] else np.nan
        if label == "full":
            extra["full_res"] = res
            row.update(year_dependence(res.trades))
            row.update(trade_concentration(res.trades))
        for rk in (P.paper_risks if label in ("full", "oos") else ()):
            ps, pb = rn.run(chosen, w, mode, risk=rk, start=P.paper_start)
            pm = rn.metrics(ps, pb)
            tag = f"sim_{int(rk * 100)}pct" + ("" if label == "full" else f"_{label}")
            monthly = ps.equity.resample("ME").last().pct_change().dropna()
            row.update({f"{tag}_final": float(ps.equity.iloc[-1]), f"{tag}_net_return": pm.get("net_return"),
                        f"{tag}_max_drawdown": pm.get("max_drawdown"), f"{tag}_trades": pm.get("trades"),
                        f"{tag}_fees": pm.get("fees"), f"{tag}_skipped": ps.skipped_min_order,
                        f"{tag}_worst_month": float(monthly.min()) if len(monthly) else np.nan})
    nb = []
    for c in v.neighbours(chosen):
        r2, b2 = rn.run(c, None, mode)
        pf = rn.metrics(r2, b2).get("profit_factor")
        nb.append(min(pf if pf is not None and not np.isnan(pf) else 0.0, 10.0))
    row["neighbour_pfs"] = json.dumps([round(x, 2) for x in nb])
    row["neighbour_median_pf"] = float(np.median(nb)) if nb else np.nan
    if mode == "maker":
        rt, bt = rn.run(chosen, None, "taker")
        row["taker_check_pf"] = rn.metrics(rt, bt).get("profit_factor")
    row["val_pass"] = bool(_v(row, "val_trades", 0) >= v.min_val_trades and _v(row, "val_profit_factor", 0) >= P.val_pf_gate
                           and _v(row, "val_expectancy_pct", -1) > 0)
    wf, folds = rn.walk_forward(mode)
    row.update({"wf_trades": wf.get("trades"), "wf_profit_factor": wf.get("profit_factor"),
                "wf_expectancy_pct": wf.get("expectancy_pct"), "wf_net_return": wf.get("net_return"),
                "wf_max_drawdown": wf.get("max_drawdown")})
    extra["folds"] = folds
    extra["regimes"] = by_regime(extra["full_res"].trades, regime_labels(df))
    extra["years"] = year_table(extra["full_res"], df)
    row["status"], reasons = acceptance(row, v)
    row["reasons"] = "; ".join(reasons)
    log(f"  [{mode}] {v.key} {row['params']}: trades {row.get('full_trades')} train PF {fmt(row.get('train_profit_factor'))} "
        f"val {fmt(row.get('val_profit_factor'))} OOS {fmt(row.get('oos_profit_factor'))} WF {fmt(row.get('wf_profit_factor'))} "
        f"(gross {fmt(row.get('full_gross_pf'))}) -> {row['status']}")
    return row, table, extra


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pre-registered BTC Momentum Breakout study")
    ap.add_argument("--versions", nargs="+", default=[v.key for v in VERSIONS])
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not data_path("5m").is_file():
        print("MISSING DATA: needs research_data/coinbase_btcusd_5m.csv.gz. No results were produced.", file=sys.stderr)
        return 3
    t_start = time.time()
    log = lambda *a: print(*a, flush=True)
    costs = default_costs()
    report = {"protocol": asdict(P), "costs": asdict(costs), "data": {}}
    rows, tables, extras, bh = [], [], {}, {}
    for v in [x for x in VERSIONS if x.key in args.versions]:
        df = load_timeframe(v.tf)
        q = quality_report(df, v.tf).to_dict()
        sp = splits(df)
        q["splits"] = {k: f"{a:%Y-%m-%d %H:%M}..{b:%Y-%m-%d %H:%M}" for k, w in sp.items() if w for a, b in [w]}
        report["data"][v.tf] = q
        bh[v.tf] = {k: buy_and_hold(df, w, costs) for k, w in sp.items()}
        bh[v.tf]["sim_full"] = buy_and_hold(df, None, costs, P.paper_start)
        bh[v.tf]["sim_oos"] = buy_and_hold(df, sp["oos"], costs, P.paper_start)
        log(f"[{v.key} {v.tf}] {q['rows']:,} bars; splits {q['splits']}")
        rn = Runner(df, v, costs)
        for mode in MODES:
            row, table, extra = evaluate(rn, mode, sp, log)
            rows.append(row)
            tables.append(table)
            extras[(v.key, mode)] = extra
    summ = pd.DataFrame(rows)
    summ.to_csv(out / "strategy_summary.csv", index=False)
    pd.concat(tables).to_csv(out / "train_grid_results.csv", index=False)
    write_report(out, summ, extras, bh, report, costs, time.time() - t_start)
    (out / "report.json").write_text(json.dumps(report, indent=2, default=str))
    log(f"wrote {out / 'REPORT.md'}")
    return 0


def _pl(r) -> str:
    return "fixed spec" if r.get("params") == "{}" else r["params"]


def write_report(out, summ, extras, bh, report, costs, secs):
    has = summ.params.apply(lambda p: isinstance(p, str))
    as_int = lambda x: f"{int(x)}" if isinstance(x, (int, float)) and np.isfinite(x) else "n/a"
    passed = summ[summ.status == "PASS"]
    L = ["# BTC Momentum Breakout Study (`momentum`)", "",
         f"Generated {pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC in {secs:.0f}s by `python3 -m backtest.momentum_study`. "
         "Pre-registered protocol: `MOMENTUM_BREAKOUT_PROTOCOL.md` (committed before this run).", "",
         "**Not a blind study**: three earlier studies (5m-6h and 1d-3d) failed on this same data and the OOS window "
         "(2025-04..2026-09) has been viewed repeatedly; Version A is a close relative of the failed HTF `donchian_ema`/"
         "`htf_breakout` families. See the protocol.", "",
         f"**Costs.** Taker legs {costs.taker_fee:.2%} + {costs.half_spread:.3%} half-spread + {costs.slippage:.3%} slippage "
         f"(+{costs.stop_slippage:.3%} on stops); maker legs {costs.maker_fee:.2%} at the limit price. Stops are always "
         f"taker, also in the maker case. Fee source: {costs.source}. Spread/slippage ASSUMED.", "",
         f"**Maker model.** One-bar post-only limit at the signal close, filled only if price trades {P.penetration:.2%} "
         "through it (missed otherwise, never chased); time exits likewise with taker fallback; partial take-profit is a "
         "resting maker limit; the maker entry bar's high never counts. OHLC approximation, no queue data.", "",
         "## Verdict", ""]
    if passed.empty:
        L += ["**NO STRATEGY PASSED.** No candidate met every pre-registered acceptance criterion. Nothing is "
              "implemented and no paper session should be started on the basis of this study.", ""]
    else:
        L += ["**PASSED:** " + ", ".join(f"{r.version} [{r['mode']}] {r.full_params}" for _, r in passed.iterrows()), ""]
    L += [f"Status counts: {summ.status.value_counts().to_dict()}", "", "## Data and splits", ""]
    for tf, d in report["data"].items():
        L.append(f"- **{tf}**: {d['rows']:,} bars {d['first'][:16]} -> {d['last'][:16]}; missing {d['missing_pct']}%; "
                 f"bad OHLC {d['bad_ohlc_rows']}. Splits: {d['splits']}")
    L += ["", "## BTC buy-and-hold (taker in/out, after costs)", "", "| TF | Split | Return | CAGR | Max DD | Sharpe |",
          "|---|---|---|---|---|---|"]
    for tf, b in bh.items():
        for s in ("train", "val", "oos", "full"):
            L.append(f"| {tf} | {s} | {fmt(b[s]['net_return'], True, 1)} | {fmt(b[s]['cagr'], True, 1)} | "
                     f"{fmt(b[s]['max_drawdown'], True, 1)} | {fmt(b[s]['sharpe'])} |")
    L += ["", "## Every candidate: full history (1% risk, after costs) + OOS + walk-forward", "",
          "| Version | Mode | Params | Trades | Win% | PF before costs | PF after costs | Expectancy | Avg trade $ | Net return | "
          "Max DD | Sharpe | Fees $ | Exposure | OOS trades | OOS PF | OOS return | WF trades | WF PF | Status | Reasons |",
          "|" + "---|" * 21]
    for r in summ.to_dict("records"):
        if not isinstance(r.get("params"), str):
            L.append(f"| {r['version']} | {r['mode']} | – |" + " – |" * 16 + f" FAIL | {r['reasons']} |")
            continue
        L.append(f"| {r['version']} | {r['mode']} | `{_pl(r)}` | {_v(r, 'full_trades', 0):.0f} | "
                 f"{fmt(r.get('full_win_rate'), True, 1)} | {fmt(r.get('full_gross_pf'))} | {fmt(r.get('full_profit_factor'))} | "
                 f"{fmt(r.get('full_expectancy_pct'), True, 3)} | ${fmt(r.get('full_expectancy_usd'))} | {fmt(r.get('full_net_return'), True, 1)} | "
                 f"{fmt(r.get('full_max_drawdown'), True, 1)} | {fmt(r.get('full_sharpe'))} | ${fmt(r.get('full_fees'), d=0)} | "
                 f"{fmt(r.get('full_exposure'), True, 1)} | {_v(r, 'oos_trades', 0):.0f} | {fmt(r.get('oos_profit_factor'))} | "
                 f"{fmt(r.get('oos_net_return'), True, 1)} | {_v(r, 'wf_trades', 0):.0f} | {fmt(r.get('wf_profit_factor'))} | "
                 f"{r['status']} | {r['reasons']} |")
    L += ["", "## Maker vs taker", "",
          "| Version | Taker params | Taker PF (full / OOS / WF) | Maker params | Maker PF (full / OOS / WF) | Maker missed entries | "
          "Maker params under taker costs PF | Taker fees $ (full) | Maker fees $ (full) |", "|" + "---|" * 9]
    for vk, g in summ.groupby("version", sort=False):
        t, m = (g[g["mode"] == x].iloc[0].to_dict() for x in MODES)
        pk = lambda r: f"`{_pl(r)}`" if isinstance(r.get("params"), str) else "none eligible"
        tri = lambda r: f"{fmt(r.get('full_profit_factor'))} / {fmt(r.get('oos_profit_factor'))} / {fmt(r.get('wf_profit_factor'))}"
        L.append(f"| {vk} | {pk(t)} | {tri(t)} | {pk(m)} | {tri(m)} | {fmt(m.get('full_missed_entry_rate'), True, 0)} | "
                 f"{fmt(m.get('taker_check_pf'))} | ${fmt(t.get('full_fees'), d=0)} | ${fmt(m.get('full_fees'), d=0)} |")
    L += ["", "## Split detail (1% risk, after costs)", "",
          "| Version | Mode | Split | Trades | Win% | PF before costs | PF after costs | Expectancy | Net return | Max DD | Sharpe | "
          "Exposure | Fees $ | Partial-exit rate | Time-exit rate |", "|" + "---|" * 15]
    for r in summ[has].to_dict("records"):
        for s in ("train", "val", "oos", "full"):
            L.append(f"| {r['version']} | {r['mode']} | {s} | {_v(r, f'{s}_trades', 0):.0f} | {fmt(r.get(f'{s}_win_rate'), True, 1)} | "
                     f"{fmt(r.get(f'{s}_gross_pf'))} | {fmt(r.get(f'{s}_profit_factor'))} | {fmt(r.get(f'{s}_expectancy_pct'), True, 3)} | "
                     f"{fmt(r.get(f'{s}_net_return'), True, 1)} | {fmt(r.get(f'{s}_max_drawdown'), True, 1)} | {fmt(r.get(f'{s}_sharpe'))} | "
                     f"{fmt(r.get(f'{s}_exposure'), True, 1)} | ${fmt(r.get(f'{s}_fees'), d=0)} | "
                     f"{fmt(r.get(f'{s}_partial_rate'), True, 0)} | {fmt(r.get(f'{s}_time_exit_rate'), True, 0)} |")
    L += ["", "## Robustness (full history, after costs)", "",
          "| Version | Mode | Nearby-parameter PFs | Median | Best year | Best-year share | PF w/o best year | Best trade share | "
          "Top-3 share | Net w/o top k (k) |", "|" + "---|" * 10]
    for r in summ[has].to_dict("records"):
        L.append(f"| {r['version']} | {r['mode']} | {r.get('neighbour_pfs')} | {fmt(r.get('neighbour_median_pf'))} | "
                 f"{as_int(r.get('best_year'))} | {fmt(r.get('best_year_share_of_net'), True, 0)} | {fmt(r.get('pf_without_best_year'))} | "
                 f"{fmt(r.get('best_trade_share'), True, 0)} | {fmt(r.get('top3_share'), True, 0)} | "
                 f"${fmt(r.get('net_without_topk'), d=0)} ({as_int(r.get('top_k'))}) |")
    L += ["", "## $200 simulation (cash-capped, no leverage, long only, after costs)", "",
          "| Version | Mode | Risk | Full: end $ | Return | Max DD | Trades | Fees $ | Worst month | OOS: end $ | OOS max DD | "
          "B&H full end $ | B&H OOS end $ |", "|" + "---|" * 13]
    for r in summ[has].to_dict("records"):
        b = bh[r["tf"]]
        for rk in P.paper_risks:
            t = f"sim_{int(rk * 100)}pct"
            L.append(f"| {r['version']} | {r['mode']} | {rk:.0%} | ${fmt(r.get(f'{t}_final'))} | {fmt(r.get(f'{t}_net_return'), True, 1)} | "
                     f"{fmt(r.get(f'{t}_max_drawdown'), True, 1)} | {_v(r, f'{t}_trades', 0):.0f} | ${fmt(r.get(f'{t}_fees'))} | "
                     f"{fmt(r.get(f'{t}_worst_month'), True, 1)} | ${fmt(r.get(f'{t}_oos_final'))} | "
                     f"{fmt(r.get(f'{t}_oos_max_drawdown'), True, 1)} | ${fmt(b['sim_full']['final'])} | ${fmt(b['sim_oos']['final'])} |")
    L += ["", "## Per-candidate detail: by year, by regime, walk-forward folds", ""]
    for r in summ[has].to_dict("records"):
        ex = extras[(r["version"], r["mode"])]
        L += [f"### {r['version']} [{r['mode']}] `{r['full_params']}` -> {r['status']}", "",
              "| Year | Trades | Win% | PF | Net $ | Strategy return (1% risk) | BTC return |", "|---|---|---|---|---|---|---|"]
        for y in ex["years"].to_dict("records"):
            L.append(f"| {y['year']} | {y['trades']} | {fmt(y['win_rate'], True, 0)} | {fmt(y['pf'])} | ${fmt(y['net_usd'], d=0)} | "
                     f"{fmt(y['strategy_return'], True, 1)} | {fmt(y['btc_return'], True, 1)} |")
        L += ["", "| Regime (entry day, lagged daily label) | Trades | Win% | PF | Expectancy | Net $ |", "|---|---|---|---|---|---|"]
        for x in ex["regimes"].to_dict("records"):
            L.append(f"| {x['regime']} | {x['trades']} | {fmt(x['win_rate'], True, 0)} | {fmt(x['profit_factor'])} | "
                     f"{fmt(x['expectancy_pct'], True, 3)} | ${fmt(x['net_profit'], d=0)} |")
        L += ["", f"Walk-forward: PF {fmt(r.get('wf_profit_factor'))}, {_v(r, 'wf_trades', 0):.0f} trades, expectancy "
              f"{fmt(r.get('wf_expectancy_pct'), True, 3)}, return {fmt(r.get('wf_net_return'), True, 1)}, max DD "
              f"{fmt(r.get('wf_max_drawdown'), True, 1)}", ""]
        L += [f"- {f['train']} -> {f['test']}: {f['params']}" for f in ex["folds"]] + [""]
    (out / "REPORT.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
