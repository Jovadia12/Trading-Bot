"""DESCRIPTIVE diagnostics over every pre-registered configuration (NOT used for selection).

    python3 -m backtest.diagnostics

For each of the 268 configurations, on the FULL history (in-sample by construction): trades, win
rate, profit factor before costs (gross) and after costs (net), and the average gross price move
per trade versus the round-trip cost. It answers "is there any edge before costs, and how large is
it relative to fees?" It must never be used to pick a strategy -- selection is research.py's job.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from backtest.costs import ZERO, default_costs
from backtest.data import TF_SECONDS, load_timeframe
from backtest.engine import generate_trades, simulate_account
from backtest.metrics import summarize
from backtest.research import OUT, TIMEFRAMES, key
from backtest.strategies import FAMILIES, build


def main() -> int:
    costs = default_costs()
    taker_rt = 2 * (costs.taker_fee + costs.taker_price_impact())
    rows = []
    for tf in TIMEFRAMES:
        df = load_timeframe(tf)
        for fam in FAMILIES:
            for combo in fam.combos():
                raw = generate_trades(df, build(fam, df, combo))
                if not raw:
                    rows.append({"family": fam.key, "tf": tf, "params": key(combo), "trades": 0})
                    continue
                gross_move = np.array([(t.exit_ref - t.entry_ref) / t.entry_ref for t in raw])
                net = summarize(simulate_account(df, raw, costs, 10_000, 0.01), len(df), TF_SECONDS[tf])
                gross = summarize(simulate_account(df, raw, ZERO, 10_000, 0.01), len(df), TF_SECONDS[tf])
                rows.append({"family": fam.key, "tf": tf, "params": key(combo), "trades": len(raw),
                             "trades_per_year": net["trades_per_year"], "win_rate_net": net["win_rate"],
                             "gross_pf": gross["profit_factor"], "net_pf": net["profit_factor"],
                             "avg_gross_move_pct": 100 * gross_move.mean(),
                             "median_abs_move_pct": 100 * np.median(np.abs(gross_move)),
                             "taker_round_trip_cost_pct": 100 * taker_rt,
                             "net_return_1pct_risk": net["net_return"], "max_dd_1pct_risk": net["max_drawdown"]})
        print(f"{tf}: done", flush=True)
    d = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "diagnostics_all_configs_full_history.csv", index=False)
    write_markdown(d, costs, taker_rt)
    print(d.sort_values("gross_pf", ascending=False).head(15).round(3).to_string(index=False))
    return 0


def _row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"


def write_markdown(d: pd.DataFrame, costs, taker_rt: float) -> None:
    big = d[d.trades >= 100]
    L = ["# Descriptive diagnostics: all 268 configurations, full history (NOT used for selection)", "",
         f"Costs as in the research run: maker {costs.maker_fee:.2%}, taker {costs.taker_fee:.2%}; "
         f"taker round trip incl. spread/slippage ~{taker_rt:.2%}. 1% risk per trade, $10,000 start. "
         "Full history is in-sample by construction; these figures explain WHY nothing passed and must not be used to pick a strategy.", "",
         "## Counts", "",
         f"- Configurations with gross (pre-cost) PF > 1: **{(d.gross_pf > 1).sum()} of {len(d)}**",
         f"- Gross PF >= 1.5: **{(d.gross_pf >= 1.5).sum()}** (with >= 500 trades: **{((d.gross_pf >= 1.5) & (d.trades >= 500)).sum()}**)",
         f"- **Net (after-cost) PF > 1: {(d.net_pf > 1).sum()} of {len(d)}**", "",
         "## By timeframe", "", _row(["TF", "Median trades", "Median gross PF", "Best gross PF (>=100 trades)",
                                      "Best net PF (>=100 trades)", "Median avg gross move / trade"]), _row(["---"] * 6)]
    for tf in ["5m", "15m", "30m", "1h"]:
        x, y = d[d.tf == tf], big[big.tf == tf]
        L.append(_row([tf, f"{x.trades.median():.0f}", f"{x.gross_pf.median():.2f}", f"{y.gross_pf.max():.2f}",
                       f"{y.net_pf.max():.2f}", f"{x.avg_gross_move_pct.median():+.3f}%"]))
    L += ["", "## Best configuration per family (by net PF, >= 100 trades)", "",
          _row(["Family", "TF", "Params", "Trades", "Win% (net)", "Gross PF", "Net PF", "Avg gross move/trade",
                "Net return (1% risk)", "Max DD"]), _row(["---"] * 10)]
    for r in big.sort_values("net_pf", ascending=False).groupby("family").head(1).to_dict("records"):
        L.append(_row([r["family"], r["tf"], r["params"], r["trades"], f"{r['win_rate_net']:.1%}", f"{r['gross_pf']:.2f}",
                       f"{r['net_pf']:.2f}", f"{r['avg_gross_move_pct']:+.2f}%", f"{r['net_return_1pct_risk']:.1%}",
                       f"{r['max_dd_1pct_risk']:.1%}"]))
    (OUT / "DIAGNOSTICS.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
