# BTC Momentum Breakout Study: Pre-registered Protocol (study `momentum`)

Written 2026-09-29 and committed **before** this study was run on real data. Before this commit, the code ran only on synthetic random-walk data (tests). Versions, parameters, execution models, costs and acceptance rules are fixed in code:
- `backtest/strategies_momentum.py`
- `backtest/momentum_engine.py`
- `backtest/momentum_study.py`

Any later change must be a dated amendment. Results are reported under these rules whatever they show.

Version A (the paper strategy), all earlier studies and their code paths are untouched. This study has its own modules and output folder (`research_results/momentum/`). The "Version A/B/C" names below are this study's own labels, unrelated to the paper strategy "Version A".

## 1. What this study is NOT blind to

- **Three earlier studies failed** on this same Coinbase BTC-USD 2017-01..2026-09 data:
  - intraday 5m–1h: 0 of 268;
  - HTF 2h–6h: 0 of 96;
  - daily 1d–3d: 0 of 30 selections.
- **The OOS window has been viewed repeatedly.** It is the last 15%, about 2025-04 → 2026-09.
- **Close relatives already failed:**
  - Version A (4h Donchian + EMA50>EMA200, ATR stop, trail) is a close relative of the HTF study's `donchian_ema` and `htf_breakout` families, which failed OOS (PF 0.29–0.73);
  - 1h and 15m breakouts failed after costs in the intraday study.
- **The configuration was proposed after those results.** Its filters (volume, RSI, ATR band, partial exit, time exit) come from a strategy discussed after seeing them.
- **Consequences:**
  - a PASS here would be necessary, not sufficient;
  - **forward paper trading on future data remains the only clean test.**
- **Fees.** At the 0.90% taker Intro tier, a round trip costs about 1.85%. At 1h/15m, the earlier studies found that typical breakout moves don't cover that. We expect B and C to struggle, and have **not** tuned C aggressively for that reason.

## 2. Data

- Coinbase BTC-USD from `research_data/` (SHA-256 in `MANIFEST.json`):
  - **4h** and **15m** are resampled (UTC-aligned) from the 5m file;
  - **1h** comes from the separately downloaded 1h file, as in the intraday study.
- Signals use **completed candles only**. Entries happen on the **next bar**. The Donchian high and the volume SMA use the **previous** N bars, excluding the signal bar.

## 3. The three versions (all long only; ATR = Wilder ATR(14))

**Common entry rule:** EMA50 > EMA200 **and** close > EMA50 **and** close > highest high of the previous N completed bars. Entries only start after the first 200 bars (indicator warm-up).

| | A) 4H Conservative | B) 1H Main | C) 15M Faster |
|---|---|---|---|
| Donchian N | {20, 30} (grid) | 20 | {20, 40} (grid) |
| Volume filter | none | volume > 1.2 × SMA20 of the previous 20 bars' volume | same as B |
| RSI14 | none | 55 ≤ RSI ≤ 75 | same |
| ATR14 / close | none | 0.4% – 3% | **0.2% – 1.5%** (B's band scaled by √(15m/1h) = ½, since volatility scales with √time) |
| Initial stop (1R) | {1.5, 2.0} × ATR (grid) | 1.5 × ATR | {1.5, 2.0} × ATR (grid) |
| Partial exit | none | **50% at +2R** | same as B |
| After the partial | – | remaining stop → **breakeven** (entry price); trail active | same |
| Trailing stop | highest close since entry − **2 × ATR**, active **from entry**; A's only exit besides the stop | highest close since entry − 2 × ATR, **after the partial** | same |
| Time exit | none | after **24 h** (24 bars), if no bar's high has exceeded **+0.5R** and no partial has filled: exit at the next bar | same, 24 h = 96 bars |
| Selection | 4 settings, selected on train | **single pre-specified configuration, no selection** | 4 settings, selected on train |

**Interpretation choices** (fixed here because the spec leaves them open):
- **Trail timing in B/C.** The trail applies to the remaining position after the +2R partial. Before that, only the initial stop is active.
- **Stops only rise.** The stop never moves down; trails ratchet.
- **Timing of the breakeven/trail move.** It takes effect from the bar **after** the partial fills, because the order within that bar is unknown.
- **"Reached +0.5R"** means some bar's high was strictly above entry + 0.5R.
- **ATR for the trail** is ATR at the current bar close; 1R uses ATR at the signal bar.

**Selection grid:** 4 + 1 + 4 = **9 settings**, × 2 execution cases = 18 evaluations, giving **6 candidates** (version × case).

**Nearby-parameter robustness sets** (one change at a time, never used for selection):
- **A:** the grid neighbours, plus trail {1.5, 2.5} ATR.
- **B:** N {15, 25}; stop {1.25, 1.75}; volume multiple {1.0, 1.5}; partial at {1.5, 2.5}R; trail {1.5, 2.5}; time exit {12, 48} h. That's 12 variants.
- **C:** the grid neighbours, plus volume multiple {1.0, 1.5} and trail {1.5, 2.5}.

## 4. Execution cases (`backtest/momentum_engine.py`)

**Taker case:**
- Entry is a market order at the next open. Every exit is charged as taker, including the +2R partial (conservative).
- Costs: **0.90% fee per side**, plus 0.005% half-spread and 0.02% slippage per taker leg, plus 0.05% extra on stop fills.

**Maker case:**
- **Entry:** a one-bar post-only limit at the signal close. It fills only if the next bar's low trades **0.10% through** it; otherwise the trade is **missed** (never chased), and the missed-entry rate is reported.
- **+2R partial:** a resting maker limit.
- **Time exits:** a one-bar limit at the close, with a taker fallback at the next open.
- **Maker fees:** **0.50%** per maker leg, with no spread/slippage.
- **Stops are always stop-market taker orders**, since there is no honest way to stop out as maker. So the maker case isn't "0.50% in and out" on losing trades.
- **Maker entry bar:** its high may have printed before our fill, so it never counts toward the +2R target or the +0.5R check.
- The maker case must also be profitable under taker costs with the same parameters (criterion 9).
- **Limitation:** there's no historical order-book or queue data, so maker fills are approximated from OHLC bars with the conservative rules above.

**Both cases:**
- **Stops:**
  - triggered by the bar's low;
  - a bar that opens below the stop fills at the open;
  - if the stop and the target are in the same bar, **the stop is assumed first**.
- **Sizing:** risk-based sizing with a cash cap and no leverage; orders under $1 are skipped. Equity is marked to market every bar, including partly closed positions.
- **Windows are isolated.**
- **Cash cap at higher risk levels:** on 1h/15m bars the 1R stop is often under 1% of price. So risk ≥ 2% frequently hits the cash cap, and 5%/10% risk usually means a **full-cash position**. The $200 results at 5% and 10% can therefore be identical.

## 5. Method (`PAPER_MODE=true python3 -m backtest.momentum_study`)

1. **Split:** chronological **70% train / 15% validation / 15% OOS**, per timeframe.
2. **Selection (A and C only, train only):**
   - eligible if train trades ≥ minimum (A: 40, C: 150) and PF > 1 after costs, at 1% risk;
   - score = t-statistic of per-trade net return averaged with its grid neighbours;
   - **never the highest return.**
   
   B isn't selected; it's evaluated as specified.
3. **Validation gate:** trades ≥ minimum (A: 8, B: 20, C: 30), PF ≥ 1.20 and expectancy > 0.
4. **OOS:** a single look.
5. **Walk-forward** for every candidate:
   - rolling **2-year train / 6-month test**, stepped every 6 months;
   - A and C re-select from their grid on each training window (minimum trades A: 12, C: 40);
   - B runs its fixed specification over the test windows;
   - test trades are combined into one compounded result.
6. **Reported for each candidate:**
   - trades, win rate, PF before and after costs;
   - expectancy, average trade, net return, max drawdown, Sharpe (calendar-daily), fees paid, exposure;
   - OOS PF and return, walk-forward PF;
   - results by year and by market regime (bull/bear/sideways, high/mid/low volatility);
   - maker vs taker, and comparison with BTC buy-and-hold;
   - nearby-parameter PFs, best-year share, best/worst-trade contribution;
   - partial-exit and time-exit rates.
7. **$200 simulations at 2%, 5% and 10% risk per trade** (cash-capped, no leverage, after costs), over the full history and over OOS. 15% is not used.

## 6. Acceptance criteria (all required for PASS)

| # | Criterion | Threshold |
|---|---|---|
| 1 | Validation gate | passed |
| 2 | Meaningful OOS sample | OOS trades ≥ A: 15, B: 30, C: 50 |
| 3 | OOS | expectancy > 0 **and** net return > 0 **and** PF ≥ **1.5** |
| 4 | Walk-forward | trades ≥ A: 40, B: 80, C: 150; expectancy > 0; PF ≥ **1.5** |
| 5 | Profitable after costs | full-history PF > 1 after costs |
| 6 | Reasonable drawdown | full-history max drawdown ≤ **30%** in the $200 simulation at **2% risk** |
| 7 | No single year responsible for most profits | best year ≤ 50% of full-history net profit **and** PF without that year > 1 |
| 8 | Robust nearby parameters | median full-history PF after costs of the nearby-parameter set (§3) ≥ **1.2** |
| 9 | Not a few lucky trades | net profit > 0 after removing the best max(2, ⌈5% of trades⌉) trades |
| 10 | Maker case only | same parameters profitable (PF > 1) under taker costs |

- **MARGINAL:** everything passes except the OOS and/or walk-forward PF, which falls in [1.25, 1.5). It's reported, **not implemented**.
- A high full-history PF is **never** enough on its own.
- Buy-and-hold is always reported alongside, but isn't a pass criterion.

## 7. What happens next

- **If nothing is PASS:**
  - the report says **NO STRATEGY PASSED**;
  - nothing is implemented;
  - no paper session is started.
- **If a candidate is PASS:**
  1. It's implemented as a new named paper strategy; the paper strategy Version A is untouched.
  2. Tests are added.
  3. `PAPER_MODE=true` safety and the absence of live-order endpoints are verified.
  4. Then **stop** and report. **No overnight paper session is started automatically.**
