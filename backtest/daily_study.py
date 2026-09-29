"""Daily / 2-day / 3-day BTC-USD long-only study (pre-registered: DAILY_STRATEGY_PROTOCOL.md).

    PAPER_MODE=true python3 -m backtest.daily_study

Separate from backtest.research (intraday + htf studies stay untouched). Two execution cases are run
independently: TAKER and MAKER-oriented (backtest/exec_model.py). Per (mode, timeframe, family):
parameters selected on TRAIN only -> VALIDATION gate -> one OOS look -> rolling walk-forward (params
re-selected per fold) -> robustness checks -> pre-registered acceptance. Writes research_results/daily/.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.costs import ZERO, CostModel, default_costs
from backtest.data import REPO_ROOT, TF_SECONDS, data_path, load_timeframe, quality_report
from backtest.engine import AccountResult
from backtest.exec_model import MODES, MakerRules, generate_trades_exec, simulate_exec
from backtest.metrics import by_regime, regime_labels, summarize
from backtest.strategies import Family, build
from backtest.strategies_daily import DAILY_FAMILIES, DAILY_TIMEFRAMES

OUT = REPO_ROOT / "research_results" / "daily"


@dataclass(frozen=True)
class DailyProtocol:
    train_frac: float = 0.70
    val_frac: float = 0.15
    risk: float = 0.01                 # research/selection runs
    start_equity: float = 10_000.0
    min_train_trades: int = 15
    min_val_trades: int = 5
    val_pf_gate: float = 1.20
    min_oos_trades: int = 5
    accept_pf: float = 1.50            # OOS and walk-forward PF for PASS
    marginal_pf: float = 1.25          # both in [1.25, 1.5) and everything else passing -> MARGINAL (not implemented)
    min_full_trades: int = 30
    min_wf_trades: int = 20
    max_dd_research: float = 0.25      # full history at 1% risk
    max_dd_operating: float = 0.50     # full history, $200 start at 15% risk (the paper-trading setting)
    best_year_max_share: float = 0.50
    neighbour_pf: float = 1.20
    top_trades_frac: float = 0.05      # remove the best max(2, ceil(5%)) trades -> net must stay > 0
    wf_train_days: int = 1095
    wf_test_days: int = 182
    wf_min_train_trades: int = 8
    paper_start: float = 200.0
    paper_risk: float = 0.15


P = DailyProtocol()


# ----------------------------------------------------------------------------------------------- data
def load_bars(tf: str) -> pd.DataFrame:
    """1d from the 5m file (UTC days); 2d/3d aggregate COMPLETE groups of k daily bars (epoch-anchored)."""
    d = load_timeframe("1d")
    if tf == "1d":
        return d
    k = {"2d": 2, "3d": 3}[tf]
    g = d.resample(f"{24 * k}h", label="left", closed="left", origin="epoch")
    out = g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out[g.close.count() == k]


def splits(df: pd.DataFrame) -> dict:
    t0, t1 = df.index[0], df.index[-1]
    span = t1 - t0
    tr = (t0, t0 + span * P.train_frac)
    va = (tr[1], t0 + span * (P.train_frac + P.val_frac))
    return {"train": tr, "val": va, "oos": (va[1], t1 + pd.Timedelta(seconds=1)), "full": None}


# -------------------------------------------------------------------------------------------- helpers
def key(params: dict) -> str:
    return json.dumps(params, sort_keys=True, default=str)


def unkey(s: str) -> dict:
    return {k: (tuple(v) if isinstance(v, list) else v) for k, v in json.loads(s).items()}


def neighbours(family: Family, combo: dict) -> list[dict]:
    out = []
    for k, vals in family.grid.items():
        i = vals.index(combo[k])
        out += [{**combo, k: vals[j]} for j in (i - 1, i + 1) if 0 <= j < len(vals)]
    return out


def daily_sharpe(eq: pd.Series) -> tuple[float, float]:
    """Sharpe/Sortino from calendar-daily (forward-filled) equity, valid for 1d/2d/3d bars alike."""
    d = eq.resample("1D").last().ffill().pct_change().dropna()
    if len(d) < 2 or d.std() == 0:
        return 0.0, 0.0
    dn = d[d < 0]
    return float(d.mean() / d.std() * np.sqrt(365)), float(d.mean() / dn.std() * np.sqrt(365)) if len(dn) > 1 else 0.0


def metrics(res: AccountResult, bars: int, tf: str) -> dict:
    m = summarize(res, bars, TF_SECONDS[tf])
    if m.get("trades"):
        m["sharpe"], m["sortino"] = daily_sharpe(res.equity)
    return m


def run(df, family, params, window, costs, mode, risk=None, start=None, stats=None):
    sig = build(family, df, params)
    raw = generate_trades_exec(df, sig, window, mode, MakerRules(), stats)
    res = simulate_exec(df, raw, costs, start=start or P.start_equity, risk=risk or P.risk)
    if window is not None:
        lo, hi = df.index.searchsorted(window[0]), df.index.searchsorted(window[1])
        res.equity = res.equity.iloc[lo:hi]
        return res, raw, hi - lo
    return res, raw, len(df)


def select_on_train(df, tf, family, window, costs, mode, min_trades):
    rows = {}
    for combo in family.combos():
        res, _r, bars = run(df, family, combo, window, costs, mode)
        rows[key(combo)] = (combo, metrics(res, bars, tf))
    table = []
    for k, (combo, m) in rows.items():
        nb = [rows[key(c)][1] for c in neighbours(family, combo)]
        eligible = m["trades"] >= min_trades and (m.get("profit_factor") or 0) > 1.0
        score = np.nanmean([m.get("tstat", 0)] + [x.get("tstat", 0) for x in nb])
        table.append({"mode": mode, "family": family.key, "tf": tf, "params": k, "train_trades": m["trades"],
                      "train_pf": m.get("profit_factor"), "train_expectancy_pct": m.get("expectancy_pct"),
                      "train_tstat": m.get("tstat"), "eligible": eligible, "score": score if eligible else -np.inf})
    t = pd.DataFrame(table).sort_values("score", ascending=False, kind="stable")
    best = t.iloc[0]
    return (unkey(best.params) if np.isfinite(best.score) else None), t


def walk_forward(df, tf, family, costs, mode):
    start, end = df.index[0], df.index[-1]
    folds, raws, t0 = [], [], start
    while True:
        tr_end = t0 + pd.Timedelta(days=P.wf_train_days)
        if tr_end >= end:
            break
        te_end = min(tr_end + pd.Timedelta(days=P.wf_test_days), end + pd.Timedelta(seconds=1))
        chosen, _ = select_on_train(df, tf, family, (t0, tr_end), costs, mode, P.wf_min_train_trades)
        if chosen is not None:
            raws += generate_trades_exec(df, build(family, df, chosen), (tr_end, te_end), mode, MakerRules())
        folds.append({"train": f"{t0:%Y-%m-%d}..{tr_end:%Y-%m-%d}", "test": f"{tr_end:%Y-%m-%d}..{te_end:%Y-%m-%d}",
                      "params": key(chosen) if chosen else "none eligible"})
        if te_end > end:
            break
        t0 += pd.Timedelta(days=P.wf_test_days)
    raws.sort(key=lambda r: r.entry_i)
    res = simulate_exec(df, raws, costs, start=P.start_equity, risk=P.risk)
    first = df.index.searchsorted(start + pd.Timedelta(days=P.wf_train_days))
    res.equity = res.equity.iloc[first:]
    return metrics(res, len(df) - first, tf), folds


def buy_and_hold(df: pd.DataFrame, window, costs: CostModel, start: float = 10_000.0) -> dict:
    """Taker buy at the window's first open, mark to market, taker sell at its last close."""
    lo, hi = (0, len(df)) if window is None else (df.index.searchsorted(window[0]), df.index.searchsorted(window[1]))
    d = df.iloc[lo:hi]
    qty = start / (d.open.iloc[0] * (1 + costs.taker_price_impact()) * (1 + costs.taker_fee))
    eq = qty * d.close
    final = qty * d.close.iloc[-1] * (1 - costs.taker_price_impact()) * (1 - costs.taker_fee)
    eq.iloc[-1] = final
    eq = pd.concat([pd.Series([start], index=[d.index[0] - pd.Timedelta(seconds=1)]), eq])
    years = max((d.index[-1] - d.index[0]).total_seconds() / (365.25 * 86400), 1e-9)
    sh, so = daily_sharpe(eq)
    return {"net_return": final / start - 1, "cagr": (final / start) ** (1 / years) - 1,
            "max_drawdown": float((1 - eq / eq.cummax()).max()), "sharpe": sh, "final": final, "equity": eq}


def trade_concentration(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    net = trades.net.sort_values(ascending=False)
    tot = net.sum()
    k = max(2, math.ceil(P.top_trades_frac * len(net)))
    share = lambda x: float(x / tot) if tot > 0 else np.nan
    return {"top_k": k, "net_total": float(tot), "best_trade_share": share(net.iloc[0]),
            "top3_share": share(net.iloc[:3].sum()), "topk_share": share(net.iloc[:k].sum()),
            "net_without_topk": float(net.iloc[k:].sum()), "best_trade_pct": float(trades.ret.max()),
            "worst_trade_pct": float(trades.ret.min()), "worst3_net": float(net.iloc[-3:].sum())}


def year_table(res: AccountResult, df: pd.DataFrame) -> pd.DataFrame:
    t = res.trades
    eq_y = res.equity.resample("YE").last()
    eq_ret = eq_y.pct_change()
    eq_ret.iloc[0] = eq_y.iloc[0] / res.start - 1
    px = df.close.resample("YE").last()
    first_open = df.open.resample("YE").first()
    bh = px / px.shift(1) - 1
    bh.iloc[0] = px.iloc[0] / first_open.iloc[0] - 1
    rows = []
    for ts in eq_y.index:
        y = ts.year
        ty = t[t.exit_time.dt.year == y] if len(t) else t
        w = ty.net > 0 if len(ty) else pd.Series(dtype=bool)
        gl = -ty.net[~w].sum() if len(ty) else 0
        rows.append({"year": y, "trades": len(ty), "win_rate": float(w.mean()) if len(ty) else np.nan,
                     "pf": float(ty.net[w].sum() / gl) if len(ty) and gl > 0 else (np.inf if len(ty) else np.nan),
                     "net_usd": float(ty.net.sum()) if len(ty) else 0.0, "strategy_return": float(eq_ret.loc[ts]),
                     "btc_return": float(bh.loc[ts])})
    return pd.DataFrame(rows)


def year_dependence(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    yearly = trades.groupby(trades.exit_time.dt.year).net.sum()
    best = int(yearly.idxmax())
    rest = trades[trades.exit_time.dt.year != best]
    gl = -rest.net[rest.net <= 0].sum()
    return {"best_year": best,
            "best_year_share_of_net": float(yearly.max() / trades.net.sum()) if trades.net.sum() > 0 else np.nan,
            "pf_without_best_year": float(rest.net[rest.net > 0].sum() / gl) if gl > 0 else
            (np.inf if len(rest) and rest.net.sum() > 0 else np.nan)}


# ----------------------------------------------------------------------------------------- acceptance
def _v(r, k, missing):
    v = r.get(k)
    return missing if v is None or (isinstance(v, float) and np.isnan(v)) else v


def acceptance(r: dict) -> tuple[str, list[str]]:
    """PASS / MARGINAL / FAIL with the reasons. MARGINAL = every criterion met except OOS and/or
    walk-forward PF in [marginal_pf, accept_pf); it is reported but NOT implemented."""
    hard, soft = [], []
    if not r.get("val_pass"): hard.append("validation gate")
    if not _v(r, "oos_trades", 0) >= P.min_oos_trades: hard.append(f"< {P.min_oos_trades} OOS trades")
    if not _v(r, "oos_expectancy_pct", -1) > 0: hard.append("OOS expectancy <= 0")
    if not _v(r, "wf_trades", 0) >= P.min_wf_trades: hard.append(f"< {P.min_wf_trades} walk-forward trades")
    if not _v(r, "wf_expectancy_pct", -1) > 0: hard.append("walk-forward expectancy <= 0")
    for k, name in (("oos_profit_factor", "OOS PF"), ("wf_profit_factor", "walk-forward PF")):
        pf = _v(r, k, 0)
        if pf < P.marginal_pf: hard.append(f"{name} < {P.marginal_pf}")
        elif pf < P.accept_pf: soft.append(f"{name} {pf:.2f} < {P.accept_pf}")
    if not _v(r, "full_profit_factor", 0) > 1.0: hard.append("full-history PF after costs <= 1")
    if not _v(r, "full_trades", 0) >= P.min_full_trades: hard.append(f"< {P.min_full_trades} full-history trades")
    if not _v(r, "full_max_drawdown", 1) <= P.max_dd_research: hard.append(f"max DD (1% risk) > {P.max_dd_research:.0%}")
    if not _v(r, "paper_max_drawdown", 1) <= P.max_dd_operating:
        hard.append(f"max DD at 15% risk ($200) > {P.max_dd_operating:.0%}")
    if not _v(r, "best_year_share_of_net", 9) <= P.best_year_max_share: hard.append("best year > 50% of net profit")
    if not _v(r, "pf_without_best_year", 0) > 1.0: hard.append("PF without best year <= 1")
    if not _v(r, "neighbour_median_pf", 0) >= P.neighbour_pf: hard.append(f"neighbour median PF < {P.neighbour_pf}")
    if not _v(r, "net_without_topk", -1) > 0: hard.append("unprofitable without its best few trades")
    if r.get("mode") == "maker" and not _v(r, "taker_check_pf", 0) > 1.0:
        hard.append("same params unprofitable under taker costs")
    if hard:
        return "FAIL", hard + soft
    return ("MARGINAL", soft) if soft else ("PASS", [])


# ------------------------------------------------------------------------------------------- report
def fmt(x, pct=False, d=2):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    if isinstance(x, float) and not np.isfinite(x):
        return "inf"
    return f"{x * 100:.{d}f}%" if pct else f"{x:,.{d}f}"


def evaluate(df, daily_df, tf, fam, mode, costs, sp, log) -> tuple[dict, pd.DataFrame, dict]:
    chosen, table = select_on_train(df, tf, fam, sp["train"], costs, mode, P.min_train_trades)
    row = {"mode": mode, "family": fam.key, "tf": tf, "params": key(chosen) if chosen else None}
    extra = {}
    if chosen is None:
        row["status"], row["reasons"] = "FAIL", f"no parameter set with >= {P.min_train_trades} train trades and PF > 1 after costs"
        log(f"  [{mode}] {fam.key:13s} {tf}: no eligible parameters on train")
        return row, table, extra
    for label, w in sp.items():
        st = {}
        res, raw, bars = run(df, fam, chosen, w, costs, mode, stats=st)
        m = metrics(res, bars, tf)
        row.update({f"{label}_{k}": v for k, v in m.items() if not isinstance(v, (list, dict))})
        g, _r, gb = run(df, fam, chosen, w, ZERO, mode)
        row[f"{label}_gross_pf"] = metrics(g, gb, tf).get("profit_factor")
        if mode == "maker":
            row[f"{label}_missed_entry_rate"] = st["missed_entries"] / st["entry_signals"] if st.get("entry_signals") else np.nan
            row[f"{label}_maker_exit_rate"] = (st["maker_exits"] / (st["maker_exits"] + st["fallback_exits"])
                                               if st["maker_exits"] + st["fallback_exits"] else np.nan)
        if label == "full":
            extra["full_res"], extra["full_raw"] = res, raw
            row.update(year_dependence(res.trades))
            row.update(trade_concentration(res.trades))
            p = simulate_exec(df, raw, costs, start=P.paper_start, risk=P.paper_risk)
            pm = metrics(p, len(df), tf)
            monthly = p.equity.resample("ME").last().pct_change().dropna()
            row.update({"paper_final": float(p.equity.iloc[-1]), "paper_net_return": pm.get("net_return"),
                        "paper_cagr": pm.get("cagr"), "paper_max_drawdown": pm.get("max_drawdown"),
                        "paper_trades": pm.get("trades"), "paper_skipped": p.skipped_min_order,
                        "paper_fees": pm.get("fees"), "paper_worst_month": float(monthly.min()) if len(monthly) else np.nan,
                        "paper_best_month": float(monthly.max()) if len(monthly) else np.nan,
                        "paper_longest_loss_streak": pm.get("longest_loss_streak")})
        if label == "oos":
            po, _ro, bo = run(df, fam, chosen, w, costs, mode, risk=P.paper_risk, start=P.paper_start)
            row["paper_oos_final"] = float(po.equity.iloc[-1])
            row["paper_oos_max_drawdown"] = metrics(po, bo, tf).get("max_drawdown")
    nb = []
    for c in neighbours(fam, chosen):
        rn, _x, bn = run(df, fam, c, None, costs, mode)
        pf = metrics(rn, bn, tf).get("profit_factor")
        nb.append(min(pf if pf is not None and not np.isnan(pf) else 0.0, 10.0))
    row["neighbour_pfs"] = json.dumps([round(x, 2) for x in nb])
    row["neighbour_median_pf"] = float(np.median(nb)) if nb else np.nan
    if mode == "maker":
        rt, _x, bt = run(df, fam, chosen, None, costs, "taker")
        row["taker_check_pf"] = metrics(rt, bt, tf).get("profit_factor")
    row["val_pass"] = bool(_v(row, "val_trades", 0) >= P.min_val_trades and _v(row, "val_profit_factor", 0) >= P.val_pf_gate
                           and _v(row, "val_expectancy_pct", -1) > 0)
    wf, folds = walk_forward(df, tf, fam, costs, mode)
    row.update({"wf_trades": wf.get("trades"), "wf_profit_factor": wf.get("profit_factor"),
                "wf_expectancy_pct": wf.get("expectancy_pct"), "wf_net_return": wf.get("net_return"),
                "wf_max_drawdown": wf.get("max_drawdown")})
    extra["folds"] = folds
    extra["regimes"] = by_regime(extra["full_res"].trades, regime_labels(daily_df))
    extra["years"] = year_table(extra["full_res"], df)
    row["status"], reasons = acceptance(row)
    row["reasons"] = "; ".join(reasons)
    log(f"  [{mode}] {fam.key:13s} {tf} {row['params']}: train PF {fmt(row.get('train_profit_factor'))} "
        f"val {fmt(row.get('val_profit_factor'))} OOS {fmt(row.get('oos_profit_factor'))} "
        f"WF {fmt(row.get('wf_profit_factor'))} -> {row['status']}")
    return row, table, extra


def main(argv=None) -> int:
    global P
    ap = argparse.ArgumentParser(description="Pre-registered daily/2d/3d BTC study")
    ap.add_argument("--tf", nargs="+", default=DAILY_TIMEFRAMES)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not data_path("5m").is_file() and not data_path("1d").is_file():
        print("MISSING DATA: needs research_data/coinbase_btcusd_5m.csv.gz. No results were produced.", file=sys.stderr)
        return 3
    t_start = time.time()
    log = lambda *a: print(*a, flush=True)
    costs = default_costs()
    daily_df = load_bars("1d")
    frames = {tf: (daily_df if tf == "1d" else load_bars(tf)) for tf in args.tf}
    report = {"protocol": asdict(P), "costs": asdict(costs), "maker_rules": asdict(MakerRules()), "data": {}}
    rows, tables, extras, bh = [], [], {}, {}
    for tf, df in frames.items():
        q = quality_report(df, tf).to_dict()
        sp = splits(df)
        q["splits"] = {k: f"{a:%Y-%m-%d}..{b:%Y-%m-%d}" for k, v in sp.items() if v for a, b in [v]}
        report["data"][tf] = q
        bh[tf] = {k: buy_and_hold(df, w, costs) for k, w in sp.items()}
        bh[tf]["paper_full"] = buy_and_hold(df, None, costs, P.paper_start)
        bh[tf]["paper_oos"] = buy_and_hold(df, sp["oos"], costs, P.paper_start)
        log(f"[{tf}] {q['rows']:,} bars {q['first']} -> {q['last']}; splits {q['splits']}")
        for mode in MODES:
            for fam in DAILY_FAMILIES:
                row, table, extra = evaluate(df, daily_df, tf, fam, mode, costs, sp, log)
                rows.append(row)
                tables.append(table)
                extras[(mode, fam.key, tf)] = extra
    summ = pd.DataFrame(rows)
    summ.to_csv(out / "strategy_summary.csv", index=False)
    pd.concat(tables).to_csv(out / "train_grid_results.csv", index=False)
    write_report(out, summ, extras, bh, frames, report, costs, time.time() - t_start)
    (out / "report.json").write_text(json.dumps(report, indent=2, default=str))
    log(f"wrote {out / 'REPORT.md'}")
    return 0


def write_report(out, summ, extras, bh, frames, report, costs, secs):
    has = summ.params.apply(lambda p: isinstance(p, str))
    L = ["# BTC Daily / 2-day / 3-day Strategy Study (`daily`)", "",
         f"Generated {pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC in {secs:.0f}s by `python3 -m backtest.daily_study`. "
         "Pre-registered protocol: `DAILY_STRATEGY_PROTOCOL.md` (committed before this run).", "",
         "**Not a blind study.** The earlier 5m-6h studies failed and their OOS window (2025-04..2026-09) was "
         "already viewed; see the protocol. Only future data (forward paper trading) is a clean test.", "",
         f"**Costs.** Taker legs: {costs.taker_fee:.2%} fee + {costs.half_spread:.3%} half-spread + {costs.slippage:.3%} "
         f"slippage (+{costs.stop_slippage:.3%} on stops). Maker legs: {costs.maker_fee:.2%} fee at the limit price. "
         f"Fee source: {costs.source}. Spread/slippage ASSUMED.", "",
         f"**Maker model.** Post-only limit at the signal close, valid for one bar, filled only if price trades "
         f"through it by {MakerRules().penetration:.2%}; otherwise the entry is MISSED (never chased) and an "
         "unfilled exit falls back to a taker order at the next open. Stops are always taker. No order-book or "
         "queue data exists for 2017-2026, so this is an OHLC approximation (see protocol).", "",
         f"**Multiple testing.** {sum(len(f.combos()) for f in DAILY_FAMILIES)} parameter sets per timeframe x "
         f"{len(frames)} timeframes x 2 execution cases = "
         f"{sum(len(f.combos()) for f in DAILY_FAMILIES) * len(frames) * 2} evaluated configurations; "
         f"{len(summ)} train-selected candidates.", "", "## Data and splits", ""]
    for tf, d in report["data"].items():
        L.append(f"- **{tf}**: {d['rows']:,} bars {d['first'][:10]} -> {d['last'][:10]}; missing {d['missing_pct']}%; "
                 f"bad OHLC {d['bad_ohlc_rows']}. Splits: {d['splits']}")
    L += ["", "## BTC buy-and-hold benchmark (taker in/out, after costs)", "",
          "| TF | Split | Return | CAGR | Max DD | Sharpe |", "|---|---|---|---|---|---|"]
    for tf, b in bh.items():
        for sp in ("train", "val", "oos", "full"):
            x = b[sp]
            L.append(f"| {tf} | {sp} | {fmt(x['net_return'], True, 1)} | {fmt(x['cagr'], True, 1)} | "
                     f"{fmt(x['max_drawdown'], True, 1)} | {fmt(x['sharpe'])} |")
    counts = summ.status.value_counts().to_dict()
    L += ["", f"## Verdict counts: {counts}", ""]
    passed = summ[summ.status == "PASS"]
    marginal = summ[summ.status == "MARGINAL"]
    if passed.empty:
        L += ["**No candidate passed every pre-registered acceptance criterion.** Nothing is implemented and no "
              "paper session should be started on the basis of this study." +
              (f" {len(marginal)} candidate(s) were MARGINAL (reported, not implemented)." if len(marginal) else ""), ""]
    else:
        L += [f"**{len(passed)} candidate(s) passed every pre-registered criterion:** " +
              ", ".join(f"{r.family} {r.tf} [{r['mode']}] {r.params}" for _, r in passed.iterrows()), ""]

    L += ["## Summary of every train-selected candidate (1% risk, after costs)", "",
          "| Mode | TF | Family | Params | Full trades | Win% | PF before costs | PF after costs | Net return | Max DD | "
          "Expectancy | Sharpe | OOS trades | OOS PF | OOS return | WF trades | WF PF | Status | Reasons |",
          "|" + "---|" * 19]
    for r in summ.sort_values(["mode", "tf", "family"]).to_dict("records"):
        if not isinstance(r.get("params"), str):
            L.append(f"| {r['mode']} | {r['tf']} | {r['family']} | – |" + " – |" * 13 + f" FAIL | {r['reasons']} |")
            continue
        L.append(f"| {r['mode']} | {r['tf']} | {r['family']} | `{r['params']}` | {r.get('full_trades', 0):.0f} | "
                 f"{fmt(r.get('full_win_rate'), True, 1)} | {fmt(r.get('full_gross_pf'))} | {fmt(r.get('full_profit_factor'))} | "
                 f"{fmt(r.get('full_net_return'), True, 1)} | {fmt(r.get('full_max_drawdown'), True, 1)} | "
                 f"{fmt(r.get('full_expectancy_pct'), True, 2)} | {fmt(r.get('full_sharpe'))} | {r.get('oos_trades', 0):.0f} | "
                 f"{fmt(r.get('oos_profit_factor'))} | {fmt(r.get('oos_net_return'), True, 1)} | {_v(r, 'wf_trades', 0):.0f} | "
                 f"{fmt(r.get('wf_profit_factor'))} | {r['status']} | {r['reasons']} |")

    L += ["", "## Maker vs taker (each case selects its own parameters on train)", "",
          "| TF | Family | Taker params | Taker full PF | Taker OOS PF | Taker WF PF | Maker params | Maker full PF | "
          "Maker OOS PF | Maker WF PF | Maker missed entries (full) | Maker exits filled as maker | Maker params under taker costs PF |",
          "|" + "---|" * 13]
    for (tf, fam), g in summ.groupby(["tf", "family"], sort=False):
        t = g[g["mode"] == "taker"].iloc[0].to_dict()
        m = g[g["mode"] == "maker"].iloc[0].to_dict()
        pk = lambda r: f"`{r['params']}`" if isinstance(r.get("params"), str) else "none eligible"
        L.append(f"| {tf} | {fam} | {pk(t)} | {fmt(t.get('full_profit_factor'))} | {fmt(t.get('oos_profit_factor'))} | "
                 f"{fmt(t.get('wf_profit_factor'))} | {pk(m)} | {fmt(m.get('full_profit_factor'))} | "
                 f"{fmt(m.get('oos_profit_factor'))} | {fmt(m.get('wf_profit_factor'))} | {fmt(m.get('full_missed_entry_rate'), True, 0)} | "
                 f"{fmt(m.get('full_maker_exit_rate'), True, 0)} | {fmt(m.get('taker_check_pf'))} |")

    L += ["", "## Split detail (1% risk, after costs)", "",
          "| Mode | TF | Family | Split | Trades | Win% | PF before costs | PF after costs | Expectancy | Net return | Max DD | Sharpe | Exposure | Fees |",
          "|" + "---|" * 14]
    for r in summ[has].sort_values(["mode", "tf", "family"]).to_dict("records"):
        for sp in ("train", "val", "oos", "full"):
            L.append(f"| {r['mode']} | {r['tf']} | {r['family']} | {sp} | {_v(r, f'{sp}_trades', 0):.0f} | "
                     f"{fmt(r.get(f'{sp}_win_rate'), True, 1)} | {fmt(r.get(f'{sp}_gross_pf'))} | {fmt(r.get(f'{sp}_profit_factor'))} | "
                     f"{fmt(r.get(f'{sp}_expectancy_pct'), True, 2)} | {fmt(r.get(f'{sp}_net_return'), True, 1)} | "
                     f"{fmt(r.get(f'{sp}_max_drawdown'), True, 1)} | {fmt(r.get(f'{sp}_sharpe'))} | "
                     f"{fmt(r.get(f'{sp}_exposure'), True, 0)} | ${fmt(r.get(f'{sp}_fees'), d=0)} |")

    L += ["", "## Robustness (full history, after costs)", "",
          "| Mode | TF | Family | Neighbour PFs | Neighbour median | Best year | Best-year share | PF w/o best year | "
          "Best trade share | Top-3 share | Net w/o top k (k) | Worst trade |", "|" + "---|" * 12]
    for r in summ[has].sort_values(["mode", "tf", "family"]).to_dict("records"):
        L.append(f"| {r['mode']} | {r['tf']} | {r['family']} | {r.get('neighbour_pfs')} | {fmt(r.get('neighbour_median_pf'))} | "
                 f"{r.get('best_year', 'n/a')} | {fmt(r.get('best_year_share_of_net'), True, 0)} | {fmt(r.get('pf_without_best_year'))} | "
                 f"{fmt(r.get('best_trade_share'), True, 0)} | {fmt(r.get('top3_share'), True, 0)} | "
                 f"${fmt(r.get('net_without_topk'), d=0)} ({r.get('top_k', 'n/a')}) | {fmt(r.get('worst_trade_pct'), True, 1)} |")

    L += ["", "## $200 simulation (15% risk per trade, cash-capped, no leverage, long only, after costs)", "",
          "| Mode | TF | Family | Full: end $ | Return | CAGR | Max DD | Trades | Fees $ | Worst month | Best month | "
          "OOS: end $ | OOS max DD | B&H full end $ | B&H OOS end $ |", "|" + "---|" * 15]
    for r in summ[has].sort_values(["mode", "tf", "family"]).to_dict("records"):
        b = bh[r["tf"]]
        L.append(f"| {r['mode']} | {r['tf']} | {r['family']} | ${fmt(r.get('paper_final'))} | {fmt(r.get('paper_net_return'), True, 0)} | "
                 f"{fmt(r.get('paper_cagr'), True, 1)} | {fmt(r.get('paper_max_drawdown'), True, 1)} | {_v(r, 'paper_trades', 0):.0f} | "
                 f"${fmt(r.get('paper_fees'))} | {fmt(r.get('paper_worst_month'), True, 1)} | {fmt(r.get('paper_best_month'), True, 1)} | "
                 f"${fmt(r.get('paper_oos_final'))} | {fmt(r.get('paper_oos_max_drawdown'), True, 1)} | "
                 f"${fmt(b['paper_full']['final'])} | ${fmt(b['paper_oos']['final'])} |")

    # serious candidates: PASS/MARGINAL/validation passers; else the 3 best by validation PF (informational)
    serious = summ[has & (summ.status.isin(["PASS", "MARGINAL"]) | (summ.get("val_pass", False) == True))]
    label = "validation passers / PASS / MARGINAL"
    if serious.empty:
        serious = summ[has].sort_values("val_profit_factor", ascending=False).head(3)
        label = "INFORMATIONAL: nothing passed validation; the 3 best by validation PF"
    L += ["", f"## Candidate deep-dives ({label})", ""]
    for r in serious.to_dict("records"):
        ex = extras[(r["mode"], r["family"], r["tf"])]
        L += [f"### {r['family']} {r['tf']} [{r['mode']}] `{r['params']}` -> {r['status']}", "",
              f"Reasons: {r['reasons'] or 'none'}", "", "**By year** (strategy at 1% risk vs BTC):", "",
              "| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |", "|---|---|---|---|---|---|---|"]
        for y in ex["years"].to_dict("records"):
            L.append(f"| {y['year']} | {y['trades']} | {fmt(y['win_rate'], True, 0)} | {fmt(y['pf'])} | ${fmt(y['net_usd'], d=0)} | "
                     f"{fmt(y['strategy_return'], True, 1)} | {fmt(y['btc_return'], True, 1)} |")
        L += ["", "**By regime** (entry-day regime, lagged daily labels):", "",
              "| Regime | Trades | Win% | PF | Expectancy | Net $ |", "|---|---|---|---|---|---|"]
        for x in ex["regimes"].to_dict("records"):
            L.append(f"| {x['regime']} | {x['trades']} | {fmt(x['win_rate'], True, 0)} | {fmt(x['profit_factor'])} | "
                     f"{fmt(x['expectancy_pct'], True, 2)} | ${fmt(x['net_profit'], d=0)} |")
        L += ["", "**Walk-forward folds** (params re-selected on each 3-year train window): "
              f"combined PF {fmt(r.get('wf_profit_factor'))}, {_v(r, 'wf_trades', 0):.0f} trades, "
              f"expectancy {fmt(r.get('wf_expectancy_pct'), True, 2)}, return {fmt(r.get('wf_net_return'), True, 1)}, "
              f"max DD {fmt(r.get('wf_max_drawdown'), True, 1)}", ""]
        L += [f"- {f['train']} -> {f['test']}: {f['params']}" for f in ex["folds"]] + [""]
    (out / "REPORT.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
