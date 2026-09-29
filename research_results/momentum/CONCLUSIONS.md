# Momentum Breakout study: conclusions

The protocol, `MOMENTUM_BREAKOUT_PROTOCOL.md`, was committed in `7123a6b` **before** this run. Full generated results are in `REPORT.md`, `strategy_summary.csv` and `train_grid_results.csv`.

## Verdict: NO STRATEGY PASSED

**0 of 6 candidates passed**, and none was marginal. Per the protocol:
- nothing is implemented;
- no paper session is started;
- the paper strategy Version A is untouched.

| Candidate | Full-history PF before → after costs | OOS PF (trades) | OOS return (1% risk) | Walk-forward PF (trades) |
|---|---|---|---|---|
| A 4h, taker `{"n": 30, "stop_atr": 1.5}` | 2.54 → 1.03 | 0.25 (32) | −31.4% | 1.04 (114) |
| A 4h, maker (same parameters) | 2.41 → 1.15 | 0.33 (32) | −25.2% | 1.15 (126) |
| B 1h, taker (fixed spec) | 1.26 → **0.36** | 0.05 (73) | −71.5% | 0.24 (492) |
| B 1h, maker (fixed spec) | 1.10 → **0.47** | 0.10 (65) | −58.1% | 0.30 (456) |
| C 15m, taker / maker | no grid setting was profitable on train after costs (train PF 0.02–0.13, 537–680 trades) | – | – | – |

Buy-and-hold over the same OOS window: about −3% to −4%, with a 54% drawdown.

## Why

1. **Costs versus the size of the move.** This was measured with zero costs over the full history (taker case):

| | Mean gross move per trade | Median 1R (stop distance) | Taker round trip |
|---|---|---|---|
| A 4h | +1.86% | 2.39% | ≈ 1.85% |
| B 1h | +0.29% | 1.14% | ≈ 1.85% |
| C 15m | +0.05% | 0.73% | ≈ 1.85% |

   - B's and C's breakouts make a fraction of their own fees. The volume, RSI and ATR filters, the +2R partial and the breakeven move don't change that.
   - The maker case doesn't rescue them. Stops are still taker orders, and 10–16% of maker entries are missed.
2. **B at 1% risk loses ~100%.** Its 1.5-ATR stop is about 1.1% away, so even 1% risk is roughly a full-cash position. Every trade then pays ~1.85% in costs; over 628 trades that destroys the account.
3. **A barely breaks even over the full history, then collapses.**
   - Full-history PF after costs is 1.03 (taker) and 1.15 (maker).
   - Validation PF is 0.73/0.82 and OOS PF 0.25/0.33.
   - Its profits depend on a few trades: removing the best 11 turns it deeply negative.
   - Nearby parameters sit around PF 1.0.
   - This repeats the HTF study's finding for the same idea (`donchian_ema` and `htf_breakout`, OOS PF 0.29–0.73).
4. **$200 simulations (full history).**

| Candidate | 2% risk | 5% risk | 10% risk | Max drawdown |
|---|---|---|---|---|
| A maker | $249 | $245 | $242 | 57–69% |
| A taker | $151 | $131 | $128 | 71–81% |
| B, either case | $1 (all risk levels; the account is wiped out) | | | |

   Buy-and-hold turned $200 into $16,834. 5% and 10% give nearly identical results because the cash cap binds.
5. **The time exit almost never triggers.** Only 1 of 628 B trades used it. Trades that survive 24 h have almost always already traded above +0.5R; 36% do so on the entry bar itself.

## Implication

Four pre-registered studies have now tested 5m, 15m, 1h, 2h, 4h, 6h, 1d, 2d and 3d. At Coinbase Intro-tier fees, none found a long-only BTC breakout or trend rule that survives costs and out-of-sample testing.
- **Sub-daily breakouts don't move far enough to pay 1.85% per round trip.** The fee tier makes that a structural problem, not a tuning problem.
- **Daily trend filters mostly act as exposure/drawdown control relative to buy-and-hold,** not as a source of trade-level profit (see `research_results/daily/CONCLUSIONS.md`).
