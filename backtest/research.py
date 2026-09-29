"""Strategy research pipeline (pre-registered; see STRATEGY_RESEARCH_PROTOCOL.md).

    python3 -m backtest.research                 # needs research_data/coinbase_btcusd_5m.csv.gz
    python3 -m backtest.research --tf 1h 15m     # subset of timeframes

Stages: data quality -> chronological 70/15/15 split -> per (family, timeframe) parameter selection on
TRAIN only -> VALIDATION gate -> single OUT-OF-SAMPLE look -> rolling WALK-FORWARD -> acceptance
criteria -> (only if something passes) sensitivity, regimes, risk levels, $200 simulation, Monte
Carlo. Writes research_results/REPORT.md and CSVs. It never fabricates: missing data -> exit code 3.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.costs import ZERO, CostModel, default_costs
from backtest.data import DATA_DIR, REPO_ROOT, TF_SECONDS, data_path, load_timeframe, quality_report
from backtest.engine import generate_trades, simulate_account
from backtest.metrics import by_regime, regime_labels, summarize
from backtest.strategies import FAMILIES, Family, build

OUT = REPO_ROOT / "research_results"
TIMEFRAMES = ["5m", "15m", "30m", "1h"]


@dataclass(frozen=True)
class Protocol:
    train_frac: float = 0.70
    val_frac: float = 0.15
    risk: float = 0.01                    # risk per trade used for all selection/comparison runs
    start_equity: float = 10_000.0        # large enough that the $1 minimum never binds in research runs
    min_train_trades: int = 100
    min_val_trades: int = 30
    val_pf_gate: float = 1.30
    accept_pf: float = 1.50               # OOS and walk-forward PF must both reach this
    accept_trades: int = 500              # full-history trades
    accept_max_dd: float = 0.25           # at 1% risk, full history
    robust_neighbor_pf: float = 1.20      # mean TRAIN PF of grid neighbours
    wf_train_days: int = 730
    wf_test_days: int = 182
    mc_paths: int = 10_000
    seed: int = 20260928


P = Protocol()


@dataclass(frozen=True)
class Study:
    name: str
    families: list
    timeframes: list
    protocol: Protocol
    out: Path
    extra_checks: bool = False      # neighbourhood robustness + best-year dependence (HTF study)


def _studies() -> dict:
    from backtest.strategies_htf import HTF_FAMILIES, HTF_TIMEFRAMES
    return {
        "intraday": Study("intraday", FAMILIES, TIMEFRAMES, Protocol(), OUT),
        # Pre-registered in HTF_STRATEGY_PROTOCOL.md before this study was run.
        "htf": Study("htf", HTF_FAMILIES, HTF_TIMEFRAMES,
                     Protocol(min_train_trades=60, min_val_trades=15, accept_trades=150),
                     OUT / "htf", extra_checks=True),
    }


def neighbours(family: Family, combo: dict) -> list[dict]:
    out = []
    for k, vals in family.grid.items():
        i = vals.index(combo[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                out.append({**combo, k: vals[j]})
    return out


def run(df, family, params, window, costs, risk=P.risk, start=P.start_equity):
    sig = build(family, df, params)
    raw = generate_trades(df, sig, window)
    res = simulate_account(df, raw, costs, start=start, risk=risk)
    if window is not None:
        lo, hi = df.index.searchsorted(window[0]), df.index.searchsorted(window[1])
        res.equity = res.equity.iloc[lo:hi]
        bars = hi - lo
    else:
        bars = len(df)
    return res, raw, bars


def key(params: dict) -> str:
    return json.dumps(params, sort_keys=True, default=str)


def select_on_train(df, tf, family, train_w, costs, log):
    rows = {}
    for combo in family.combos():
        res, _raw, bars = run(df, family, combo, train_w, costs)
        m = summarize(res, bars, TF_SECONDS[tf])
        rows[key(combo)] = (combo, m)
    table = []
    for k, (combo, m) in rows.items():
        nb = [rows[key(c)][1] for c in neighbours(family, combo) if key(c) in rows]
        nb_pf = np.nanmean([min(x.get("profit_factor", np.nan), 5) for x in nb]) if nb else np.nan
        eligible = m["trades"] >= P.min_train_trades and m.get("profit_factor", 0) > 1.0
        smooth = np.nanmean([m.get("tstat", 0)] + [x.get("tstat", 0) for x in nb])
        table.append({"family": family.key, "tf": tf, "params": k, **{f"train_{a}": m.get(a) for a in
                      ("trades", "win_rate", "profit_factor", "expectancy_pct", "max_drawdown", "tstat", "net_return")},
                      "neighbour_train_pf": nb_pf, "eligible": eligible, "score": smooth if eligible else -np.inf})
    t = pd.DataFrame(table).sort_values("score", ascending=False)
    best = t.iloc[0]
    chosen = json.loads(best.params) if np.isfinite(best.score) else None
    if chosen is not None:   # restore tuple-typed params (json turns tuples into lists)
        chosen = {k: (tuple(v) if isinstance(v, list) else v) for k, v in chosen.items()}
    return chosen, t


def walk_forward(df, tf, family, costs, log):
    start, end = df.index[0], df.index[-1]
    folds, raws = [], []
    t0 = start
    while True:
        tr_end = t0 + pd.Timedelta(days=P.wf_train_days)
        te_end = tr_end + pd.Timedelta(days=P.wf_test_days)
        if tr_end >= end:
            break
        te_end = min(te_end, end + pd.Timedelta(seconds=1))
        chosen, _ = select_on_train(df, tf, family, (t0, tr_end), costs, log)
        if chosen is not None:
            sig = build(family, df, chosen)
            raws += generate_trades(df, sig, (tr_end, te_end))
        folds.append({"train": f"{t0:%Y-%m-%d}..{tr_end:%Y-%m-%d}", "test": f"{tr_end:%Y-%m-%d}..{te_end:%Y-%m-%d}",
                      "params": key(chosen) if chosen else "none eligible"})
        if te_end > end:
            break
        t0 = t0 + pd.Timedelta(days=P.wf_test_days)
    raws.sort(key=lambda r: r.entry_i)
    res = simulate_account(df, raws, costs, start=P.start_equity, risk=P.risk)
    first = df.index.searchsorted(start + pd.Timedelta(days=P.wf_train_days))
    res.equity = res.equity.iloc[first:]
    return summarize(res, len(df) - first, TF_SECONDS[tf]), folds, res


def monte_carlo(rets: np.ndarray, n_trades: int, paths: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    sample = rng.choice(rets, size=(paths, n_trades), replace=True)
    eq = np.cumprod(1 + sample, axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.ones((paths, 1)), eq], axis=1), axis=1)[:, 1:]
    mdd = (1 - eq / peak).max(axis=1)
    final = eq[:, -1]
    q = lambda a, p: float(np.quantile(a, p))
    return {"paths": paths, "trades_per_path": n_trades,
            "final_multiple_p05": q(final, .05), "final_multiple_p25": q(final, .25), "final_multiple_median": q(final, .5),
            "final_multiple_p75": q(final, .75), "final_multiple_p95": q(final, .95),
            "max_dd_median": q(mdd, .5), "max_dd_p95": q(mdd, .95),
            "prob_end_below_start": float((final < 1).mean()), "prob_dd_over_25pct": float((mdd > .25).mean()),
            "prob_dd_over_50pct": float((mdd > .5).mean()), "prob_lose_half": float((final < .5).mean())}


def fmt(x, pct=False, d=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a" if x is None or np.isnan(x) else "inf"
    return f"{x * 100:.{d}f}%" if pct else f"{x:,.{d}f}"


def num(r, k, missing):
    """Missing/None/NaN metrics (e.g. zero trades) count as a FAIL via the `missing` default."""
    v = r.get(k)
    return missing if v is None or (isinstance(v, float) and np.isnan(v)) else v

def acceptance(r) -> tuple[bool, list[str]]:
    why = []
    if "neighbour_median_net_pf" in r and not (num(r, "neighbour_median_net_pf", 0) >= P.robust_neighbor_pf):
        why.append(f"parameter neighbourhood median PF < {P.robust_neighbor_pf}")
    if "pf_without_best_year" in r and not (num(r, "pf_without_best_year", 0) > 1.0):
        why.append("edge depends on a single calendar year")
    if not r.get("val_pass"): why.append("validation gate")
    if not (num(r, "oos_profit_factor", 0) >= P.accept_pf): why.append(f"OOS PF < {P.accept_pf}")
    if not (num(r, "oos_expectancy_pct", -1) > 0): why.append("OOS expectancy <= 0")
    if not (num(r, "wf_profit_factor", 0) >= P.accept_pf): why.append(f"walk-forward PF < {P.accept_pf}")
    if not (num(r, "wf_expectancy_pct", -1) > 0): why.append("walk-forward expectancy <= 0")
    if not (num(r, "full_trades", 0) >= P.accept_trades): why.append(f"< {P.accept_trades} trades")
    if not (num(r, "full_max_drawdown", 1) <= P.accept_max_dd): why.append(f"max DD > {P.accept_max_dd:.0%}")
    return (not why), why



def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pre-registered BTC strategy research")
    ap.add_argument("--study", default="intraday", choices=["intraday", "htf"])
    ap.add_argument("--tf", nargs="+", default=None)
    ap.add_argument("--families", nargs="+", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    study = _studies()[args.study]
    global P
    P = study.protocol
    args.tf = args.tf or study.timeframes
    args.families = args.families or [f.key for f in study.families]
    out = Path(args.out) if args.out else study.out
    out.mkdir(parents=True, exist_ok=True)
    base = data_path("5m")
    if not base.is_file() and not all(data_path(tf).is_file() for tf in args.tf):
        print("MISSING DATA: research needs research_data/coinbase_btcusd_5m.csv.gz (or one file per timeframe).\n"
              "Download it on a machine with Coinbase access:\n"
              "    PAPER_MODE=true python3 -m backtest.fetch_coinbase --start 2017-01-01 --tf 5m 1h\n"
              "No results were produced.", file=sys.stderr)
        return 3
    costs = default_costs()
    fams = [f for f in study.families if f.key in args.families]
    t_start = time.time()
    log = lambda *a: print(*a, flush=True)
    log(f"costs: maker {costs.maker_fee:.4%} taker {costs.taker_fee:.4%} half-spread {costs.half_spread:.4%} "
        f"slippage {costs.slippage:.4%} (+stop {costs.stop_slippage:.4%}) -- {costs.source}")

    report = {"costs": costs.__dict__, "protocol": P.__dict__, "data": {}, "selections": [], "final": None}
    train_tables, summary_rows = [], []
    frames = {}
    for tf in args.tf:
        df = load_timeframe(tf)
        frames[tf] = df
        q = quality_report(df, tf)
        report["data"][tf] = q.to_dict()
        t0, t1 = df.index[0], df.index[-1]
        span = t1 - t0
        train_w = (t0, t0 + span * P.train_frac)
        val_w = (train_w[1], t0 + span * (P.train_frac + P.val_frac))
        oos_w = (val_w[1], t1 + pd.Timedelta(seconds=1))
        report["data"][tf]["splits"] = {k: f"{a:%Y-%m-%d %H:%M}..{b:%Y-%m-%d %H:%M}" for k, (a, b) in
                                        {"train": train_w, "validation": val_w, "oos": oos_w}.items()}
        log(f"[{tf}] {q.rows:,} bars {q.first} -> {q.last}, missing {q.missing_pct}%")
        for fam in fams:
            chosen, table = select_on_train(df, tf, fam, train_w, costs, log)
            train_tables.append(table)
            row = {"family": fam.key, "name": fam.name, "tf": tf, "params": key(chosen) if chosen else None}
            if chosen is None:
                row["status"] = "no eligible params on train"
                summary_rows.append(row)
                log(f"  {fam.key:14s} no eligible parameters on train")
                continue
            for label, w in (("train", train_w), ("val", val_w), ("oos", oos_w), ("full", None)):
                res, _r, bars = run(df, fam, chosen, w, costs)
                m = summarize(res, bars, TF_SECONDS[tf])
                row.update({f"{label}_{k}": v for k, v in m.items()})
                if label in ("full", "oos"):
                    g, _r2, gb = run(df, fam, chosen, w, ZERO)
                    row[f"{label}_gross_pf"] = summarize(g, gb, TF_SECONDS[tf]).get("profit_factor")
                if label == "full" and study.extra_checks and len(res.trades):
                    tr = res.trades
                    yearly = tr.groupby(tr.exit_time.dt.year).net.sum()
                    rest = tr[tr.exit_time.dt.year != yearly.idxmax()]
                    gl = -rest.net[rest.net <= 0].sum()
                    row["best_year"] = int(yearly.idxmax())
                    row["best_year_share_of_net"] = float(yearly.max() / tr.net.sum()) if tr.net.sum() > 0 else np.nan
                    row["pf_without_best_year"] = float(rest.net[rest.net > 0].sum() / gl) if gl > 0 else np.nan
            if study.extra_checks:
                nb_pfs = []
                for c in neighbours(fam, chosen):
                    rn, _x, bn = run(df, fam, c, None, costs)
                    nb_pfs.append(min(summarize(rn, bn, TF_SECONDS[tf]).get("profit_factor", 0) or 0, 10))
                row["neighbour_median_net_pf"] = float(np.median(nb_pfs)) if nb_pfs else np.nan
                row["neighbour_net_pfs"] = json.dumps([round(x, 2) for x in nb_pfs])
            row["val_pass"] = (row.get("val_trades", 0) >= P.min_val_trades and row.get("val_profit_factor", 0) >= P.val_pf_gate
                               and row.get("val_expectancy_pct", -1) > 0)
            row["status"] = "validation PASS" if row["val_pass"] else "validation fail"
            summary_rows.append(row)
            log(f"  {fam.key:14s} {row['params']}: train PF {fmt(row.get('train_profit_factor'))} "
                f"val PF {fmt(row.get('val_profit_factor'))} oos PF {fmt(row.get('oos_profit_factor'))} "
                f"(gross PF {fmt(row.get('full_gross_pf'))}) -> {row['status']}")

    summ = pd.DataFrame(summary_rows)
    pd.concat(train_tables).to_csv(out / "train_grid_results.csv", index=False)
    # walk-forward: validation passers, else the 3 best by validation PF (informational)
    wf_pool = summ[summ.get("val_pass", False) == True] if "val_pass" in summ else summ.iloc[0:0]
    informational = False
    if wf_pool.empty and "val_profit_factor" in summ:
        wf_pool = summ.dropna(subset=["val_profit_factor"]).sort_values("val_profit_factor", ascending=False).head(3)
        informational = True
    fam_by_key = {f.key: f for f in study.families}
    wf_results = {}
    for _, r in wf_pool.iterrows():
        m, folds, res = walk_forward(frames[r.tf], r.tf, fam_by_key[r.family], costs, log)
        wf_results[(r.family, r.tf)] = (m, folds, res)
        summ.loc[(summ.family == r.family) & (summ.tf == r.tf), "wf_profit_factor"] = m.get("profit_factor")
        summ.loc[(summ.family == r.family) & (summ.tf == r.tf), "wf_trades"] = m.get("trades")
        summ.loc[(summ.family == r.family) & (summ.tf == r.tf), "wf_expectancy_pct"] = m.get("expectancy_pct")
        log(f"  walk-forward {r.family} {r.tf}: PF {fmt(m.get('profit_factor'))} over {m.get('trades')} trades")

    has_params = lambda r: isinstance(r.get("params"), str) and bool(r.get("params"))
    summ["accepted"], summ["rejection_reasons"] = zip(*[acceptance(r) if has_params(r) else
                                                        (False, ["no parameter set profitable after costs on TRAIN "
                                                                 f"(>= {P.min_train_trades} trades and PF > 1)"])
                                                        for r in summ.to_dict("records")]) if len(summ) else ([], [])
    summ["rejection_reasons"] = summ["rejection_reasons"].apply(lambda w: "; ".join(w))
    summ.to_csv(out / "strategy_summary.csv", index=False)

    winners = summ[summ.accepted == True]
    lines = [f"# BTC Strategy Research Report -- study `{study.name}` ({', '.join(args.tf)})", "",
             f"Generated {pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC in {time.time() - t_start:.0f}s by `python3 -m backtest.research` "
             f"(pre-registered protocol: {'HTF_STRATEGY_PROTOCOL.md' if study.name == 'htf' else 'STRATEGY_RESEARCH_PROTOCOL.md'}).", "",
             f"**Costs:** maker {costs.maker_fee:.2%}, taker {costs.taker_fee:.2%}, half-spread {costs.half_spread:.3%}, "
             f"slippage {costs.slippage:.3%} (+{costs.stop_slippage:.3%} on stops) -- {costs.source}. "
             "Spread/slippage are ASSUMED until measured.", "", "## Data", ""]
    for tf, d in report["data"].items():
        lines.append(f"- **{tf}**: {d['rows']:,} bars {d['first']} -> {d['last']}; missing {d['missing_pct']}% "
                     f"(largest gap {d['largest_gap_bars']} bars); bad OHLC {d['bad_ohlc_rows']}; zero-volume "
                     f"{d['zero_volume_rows']}. Splits: {d['splits']}")
    lines += ["", "## Final comparison table (selected parameters per family/timeframe; 1% risk, after costs)", "",
              "| Strategy | TF | Trades | Win% | PF | Gross PF | Expectancy | Net return | Max DD | Sharpe | Fees | Slippage | "
              "OOS PF | WF PF | Accepted |", "|" + "---|" * 15]
    for r in summ.sort_values(["accepted", "oos_profit_factor"], ascending=False).to_dict("records") if "oos_profit_factor" in summ else []:
        if not has_params(r):
            lines.append(f"| {r['family']} | {r['tf']} | – | – | – | – | – | – | – | – | – | – | – | – | no: {r['rejection_reasons']} |")
            continue
        lines.append(f"| {r['family']} {r.get('params') or ''} | {r['tf']} | {r.get('full_trades', 0):.0f} | {fmt(r.get('full_win_rate'), True, 1)} | "
                     f"{fmt(r.get('full_profit_factor'))} | {fmt(r.get('full_gross_pf'))} | {fmt(r.get('full_expectancy_pct'), True, 3)} | "
                     f"{fmt(r.get('full_net_return'), True, 1)} | {fmt(r.get('full_max_drawdown'), True, 1)} | {fmt(r.get('full_sharpe'))} | "
                     f"${fmt(r.get('full_fees'), d=0)} | ${fmt(r.get('full_slippage'), d=0)} | {fmt(r.get('oos_profit_factor'))} | "
                     f"{fmt(r.get('wf_profit_factor'))} | {'YES' if r.get('accepted') else 'no: ' + r.get('rejection_reasons', '')} |")
    sel = summ[summ.apply(has_params, axis=1)] if len(summ) else summ
    if len(sel):
        lines += ["", "## Detailed metrics of every selected configuration (1% risk, after costs)", "",
                  "| Strategy | TF | Split | Trades | Win% | PF before costs | PF after costs | Avg trade | Median trade | "
                  "Net return | Max DD | Sharpe | Sortino | Avg dur (h) | Exposure | Fees | Slippage | Longest losing streak |",
                  "|" + "---|" * 18]
        for r in sel.to_dict("records"):
            for sp in ("train", "val", "oos", "full"):
                gp = fmt(r.get(f"{sp}_gross_pf")) if sp in ("oos", "full") else "–"
                lines.append(f"| {r['family']} {r['params']} | {r['tf']} | {sp} | {r.get(f'{sp}_trades', 0):.0f} | "
                             f"{fmt(r.get(f'{sp}_win_rate'), True, 1)} | {gp} | {fmt(r.get(f'{sp}_profit_factor'))} | "
                             f"{fmt(r.get(f'{sp}_expectancy_pct'), True, 3)} | {fmt(r.get(f'{sp}_median_trade_pct'), True, 3)} | "
                             f"{fmt(r.get(f'{sp}_net_return'), True, 1)} | {fmt(r.get(f'{sp}_max_drawdown'), True, 1)} | "
                             f"{fmt(r.get(f'{sp}_sharpe'))} | {fmt(r.get(f'{sp}_sortino'))} | {fmt(r.get(f'{sp}_avg_duration_h'), d=1)} | "
                             f"{fmt(r.get(f'{sp}_exposure'), True, 1)} | ${fmt(r.get(f'{sp}_fees'), d=0)} | ${fmt(r.get(f'{sp}_slippage'), d=0)} | "
                             f"{r.get(f'{sp}_longest_loss_streak', 'n/a')} |")
        if study.extra_checks:
            lines += ["", "## Robustness checks (full history, after costs)", "",
                      "| Strategy | TF | Neighbour net PFs | Neighbour median PF | Best year | Best-year share of net | PF without best year |",
                      "|---|---|---|---|---|---|---|"]
            for r in sel.to_dict("records"):
                lines.append(f"| {r['family']} {r['params']} | {r['tf']} | {r.get('neighbour_net_pfs')} | {fmt(r.get('neighbour_median_net_pf'))} | "
                             f"{r.get('best_year', 'n/a')} | {fmt(r.get('best_year_share_of_net'), True, 0)} | {fmt(r.get('pf_without_best_year'))} |")
    lines += ["", f"Walk-forward pool: {'INFORMATIONAL (no strategy passed validation)' if informational else 'validation passers'}.", ""]
    if winners.empty:
        lines += ["## Verdict", "", "**No strategy met the pre-registered acceptance criteria.** No strategy is recommended; "
                  "nothing should be paper- or live-traded on the basis of this research.", ""]
    else:
        best = winners.sort_values(["wf_profit_factor", "oos_profit_factor"], ascending=False).iloc[0]
        fam, tf, df = fam_by_key[best.family], best.tf, frames[best.tf]
        params = {k: (tuple(v) if isinstance(v, list) else v) for k, v in json.loads(best.params).items()}
        lines += ["## Verdict", "", f"**Candidate: {fam.name}, {tf}, params {best.params}.** It passed every "
                  "pre-registered criterion. See the sections below before trusting it.", ""]
        # sensitivity
        lines += ["### Parameter sensitivity (full history, 1% risk)", "", "| Params | Trades | PF | Expectancy | Max DD |", "|---|---|---|---|---|"]
        for combo in fam.combos():
            res, _r, bars = run(df, fam, combo, None, costs)
            m = summarize(res, bars, TF_SECONDS[tf])
            lines.append(f"| {key(combo)} | {m['trades']} | {fmt(m.get('profit_factor'))} | {fmt(m.get('expectancy_pct'), True, 3)} | {fmt(m.get('max_drawdown'), True, 1)} |")
        # regimes
        res, raw, bars = run(df, fam, params, None, costs)
        reg = by_regime(res.trades, regime_labels(df))
        reg.to_csv(out / "winner_regimes.csv", index=False)
        lines += ["", "### Regimes (trades by entry-day regime)", "", "| Regime | Trades | Win% | PF | Expectancy | Net |", "|---|---|---|---|---|---|"]
        lines += [f"| {x['regime']} | {x['trades']} | {fmt(x['win_rate'], True, 1)} | {fmt(x['profit_factor'])} | "
                  f"{fmt(x['expectancy_pct'], True, 3)} | ${fmt(x['net_profit'])} |" for x in reg.to_dict('records')] or ["| n/a |"]
        lines += [""]
        # risk levels + MC
        lines += ["### Risk levels (full history)", "", "| Risk | Net return | CAGR | Max DD | Longest losing streak | P(DD>25%) MC | P(lose half) MC |", "|---|---|---|---|---|---|---|"]
        for rk in (0.005, 0.01, 0.02, 0.03):
            r2 = simulate_account(df, raw, costs, start=P.start_equity, risk=rk)
            m = summarize(r2, len(df), TF_SECONDS[tf])
            mc = monte_carlo(r2.trades.ret.to_numpy(), len(r2.trades), 2000, P.seed)
            lines.append(f"| {rk:.1%} | {fmt(m.get('net_return'), True, 1)} | {fmt(m.get('cagr'), True, 1)} | {fmt(m.get('max_drawdown'), True, 1)} | "
                         f"{m.get('longest_loss_streak')} | {mc['prob_dd_over_25pct']:.1%} | {mc['prob_lose_half']:.1%} |")
        # $200 simulation at 1%
        r200 = simulate_account(df, raw, costs, start=200.0, risk=P.risk)
        m200 = summarize(r200, len(df), TF_SECONDS[tf])
        monthly = r200.equity.resample("ME").last().pct_change().dropna()
        mc = monte_carlo(r200.trades.ret.to_numpy(), len(r200.trades), P.mc_paths, P.seed)
        lines += ["", "### $200 simulation (1% risk, full history, compounding)", "",
                  f"- Start $200.00 -> end ${r200.equity.iloc[-1]:,.2f} ({fmt(m200.get('net_return'), True, 1)}); max DD {fmt(m200.get('max_drawdown'), True, 1)}; "
                  f"longest losing streak {m200.get('longest_loss_streak')}; trades {m200.get('trades')} (skipped below $1 minimum: {r200.skipped_min_order}); "
                  f"fees ${m200.get('fees', 0):,.2f}; slippage ${m200.get('slippage', 0):,.2f}; worst month {fmt(monthly.min(), True, 1)}; best month {fmt(monthly.max(), True, 1)}",
                  "", "### Monte Carlo (bootstrap of the historical per-trade returns)", "", "```", json.dumps(mc, indent=2), "```", ""]
        json.dump({"family": fam.key, "tf": tf, "params": best.params}, open(out / "winner.json", "w"), indent=2)
    if wf_results:
        lines += ["## Walk-forward folds", ""]
        for (fk, tf), (m, folds, _res) in wf_results.items():
            lines += [f"**{fk} {tf}**: combined PF {fmt(m.get('profit_factor'))}, trades {m.get('trades')}, expectancy "
                      f"{fmt(m.get('expectancy_pct'), True, 3)}, max DD {fmt(m.get('max_drawdown'), True, 1)}", ""]
            lines += [f"- train {f['train']} -> test {f['test']}: {f['params']}" for f in folds] + [""]
    (out / "REPORT.md").write_text("\n".join(lines))
    (out / "report.json").write_text(json.dumps(report, indent=2, default=str))
    log(f"wrote {out / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
