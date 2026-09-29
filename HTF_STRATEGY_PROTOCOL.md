# 2H/4H/6H Trend-Strategy Study: Pre-registered Protocol (study `htf`)

Written 2026-09-29 and committed **before** this study was run. The families, grids, costs and acceptance rules below are fixed. Results are reported under these rules, and any later change must be a dated amendment.

## Why this study, and what it is NOT blind to

- **Why:** the intraday study (`research_results/REPORT.md`, `DIAGNOSTICS.md`) found 0 of 268 configurations on 5m–1h profitable after costs. The closest were 1h trend-following strategies (gross PF 1.7–1.8, average gross move per trade 1.4–1.7%) that fell just short of the ~1.85% taker round trip. Hypothesis: on 2H/4H/6H, trend trades are longer and move enough to beat the fees.
- **What it can't claim:**
  - This hypothesis was formed **after** seeing the intraday results. It's not a naive test.
  - Families 1 and 3 are close relatives of the intraday families 6/7.
  - The chronological OOS window (the last 15% of 2017-01..2026-09, i.e. 2025-04..2026-09) has already been looked at in the intraday study, for other strategies and timeframes.
  - The only truly unseen data is future data. **Forward paper trading remains the only clean test.**

## Data and costs

- **Data:** Coinbase BTC-USD 5m, 2017-01-01..2026-09-28 (`research_data/`, SHA-256 in `MANIFEST.json`), resampled to UTC-aligned 2h / 4h / 6h.
- **Costs:** your confirmed **Intro tier, 0.50% maker / 0.90% taker** (`research_data/fees.json`), plus 0.005% half-spread, 0.02% slippage and 0.05% extra stop slippage on taker legs. That's about 1.85% per taker round trip. **No zero-fee results are used for any decision**; the PF before costs is shown for diagnosis only.
- **Execution:** unchanged engine (`backtest/engine.py`):
  - signals on closed bars, executed at the next bar's open (taker);
  - stops from intrabar lows, with gap fills at the open;
  - stop first when the stop and an exit fall in the same bar;
  - trailing stops update at the close and apply from the next bar;
  - cash-capped sizing, no leverage.

## Families and grids (`backtest/strategies_htf.py`)

32 parameter sets per timeframe × 3 timeframes = **96 configurations**. ATR = Wilder ATR(14).

| # | Family | Entry | Exit | Grid |
|---|---|---|---|---|
| 1 | `htf_breakout` | close > previous-N high **and** close > EMA(slow) | stop s×ATR; then **only** a chandelier trail at close − 3×ATR (ratchets up) | N {10, 20, 30} × slow {100, 200} × s {1.5, 2.5} |
| 2 | `ema_pullback_cont` | EMA(fast) > EMA(slow), close > EMA(slow), a low ≤ EMA(fast) within the last 5 bars, **and** close > previous-5-bar high | stop s×ATR; close < EMA(fast) → next open | fast {20, 50} × slow {100, 200} × s {1.5, 2.5} |
| 3 | `donchian_ema` | close > previous-N high **and** EMA50 > EMA200 | stop s×ATR; close < previous-(N//2) low → next open | N {10, 15, 20, 30} × s {1.5, 2.0, 2.5} |

## Method (same pipeline as the intraday study: `python3 -m backtest.research --study htf`)

1. **Split:** chronological 70% train / 15% validation / 15% OOS, per timeframe.
2. **Selection per family × timeframe on TRAIN only:**
   - eligible if ≥ **60** train trades and PF > 1 after costs;
   - score = t-statistic of per-trade net return averaged with its one-step grid neighbours.
3. **Validation gate:** ≥ **15** trades, PF ≥ 1.30 and expectancy > 0.
4. **OOS:** one look.
5. **Walk-forward:** 2-year train / 6-month test, rolled every 6 months, with parameters re-selected per window. It runs for validation passers, or the best 3 by validation PF labelled INFORMATIONAL.
6. **Acceptance** (all required, at 1% risk, after costs):

| Criterion | Threshold |
|---|---|
| Validation gate | passed |
| OOS PF / walk-forward PF | ≥ 1.5 / ≥ 1.5 |
| OOS and walk-forward expectancy | > 0 |
| Full-history trades | ≥ **150** (500+ preferred, but not required on these timeframes) |
| Full-history max drawdown | ≤ 25% |
| **Parameter neighbourhood** | median full-history net PF of the one-step grid neighbours ≥ 1.2 |
| **Single-period dependence** | full-history PF with the best calendar year's trades removed > 1.0 |

7. **If nothing is accepted:** the study says so, **no strategy is implemented, and no paper session is started**.
8. **If a candidate is accepted:** it's implemented as a new strategy (Version A is kept), unit-tested, and run in paper mode at $200 starting cash and 15% `PAPER_RISK_PER_TRADE` (cash-capped). The 8-hour paper run is an **integration test only**.
