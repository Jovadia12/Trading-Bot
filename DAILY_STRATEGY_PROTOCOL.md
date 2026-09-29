# Daily / 2-Day / 3-Day BTC Strategy Study: Pre-registered Protocol (study `daily`)

Written 2026-09-29 and committed **before** this study was run on real data. The families, grids, execution models, costs and acceptance rules below are fixed in code (`backtest/strategies_daily.py`, `backtest/exec_model.py`, `backtest/daily_study.py`). Before this commit the code was run only on synthetic random-walk data (tests). Any later change must be a dated amendment, and results are reported under these rules whatever they show.

Previous studies (`research_results/REPORT.md`, `research_results/htf/`), their code paths and Version A are untouched. This study has its own runner and output folder (`research_results/daily/`).

## 1. What this study is NOT blind to (read first)

- **Earlier failures are known.** Both earlier studies failed after costs:
  - the intraday study: 0 of 268 configurations on 5m–1h;
  - the HTF study: 0 of 96 on 2h/4h/6h.
  
  This study was designed **after** seeing that, specifically that longer holding periods were the one untested way to clear ~1.85% round-trip taker costs. It's a follow-up hypothesis, not a naive test.
- **The data has already been seen.** The same Coinbase BTC-USD 2017-01..2026-09 data was used before. The chronological OOS window (the last 15%, roughly **2025-04 → 2026-09**) has already been viewed:
  - its aggregate behaviour was seen through the earlier OOS results;
  - year-by-year results were seen (2023 was the dominant profit year for several HTF trend candidates).
- **General market history is known.** BTC's history is public knowledge: the 2017 bubble, 2018 bear, 2020–21 bull, 2022 bear and 2023–24 recovery. Long-only daily trend following on BTC is a widely published idea that looks good **in hindsight** on an asset that rose ~100× over the sample. That is a hindsight and survivorship bias this study cannot remove, which is why it is benchmarked against buy-and-hold.
- **Families 2 and 5 are relatives of earlier ones.** They are close relatives of the earlier Donchian/breakout and pullback families, now on daily bars.
- **Consequences:**
  - **the only clean test is forward (paper) trading on future data**;
  - a PASS here is necessary, not sufficient;
  - daily-bar samples are small (tens of trades, not hundreds), so OOS and walk-forward statistics are noisy. The criteria below must all hold together, and marginal results are not implemented.

## 2. Market and data

- **Market:** BTC-USD spot on Coinbase, long only; no leverage, margin, borrowing or shorting.
- **Data:** `research_data/coinbase_btcusd_5m.csv.gz` (SHA-256 in `MANIFEST.json`), aggregated to UTC daily bars (00:00–24:00 UTC).
- **2-day and 3-day bars** group consecutive daily bars:
  - buckets are anchored to 1970-01-01 UTC (`origin="epoch"`), independent of where the data starts;
  - only **complete** buckets with exactly 2 or 3 daily bars are kept. Partial edge buckets are dropped.
- The engine is bar-agnostic, so 2d/3d need no engine change. **All lookbacks are in bars of the tested timeframe**; for example, EMA200 on 3d bars spans about 600 days.

## 3. Execution cases (tested separately; `backtest/exec_model.py`)

Signals always use **closed bars only**.

### A. Taker (identical to the existing engine, `backtest/engine.py`)
- **Entry:** market order at the next bar's open. Fee **0.90%** + 0.005% half-spread + 0.02% slippage.
- **Stops:** stop-market orders, triggered from the bar's low. A gap below the stop fills at the open. Stops add 0.05% extra slippage.
- **Signal exits:** market order at the next open, fee **0.90%**.
- **Ambiguous bars:** if the stop and another exit are both inside one bar, the stop is assumed first.
- **Trailing stops** update at the close and apply from the next bar.

A taker round trip costs about **1.85%**.

### B. Maker-oriented (conservative OHLC approximation)

- **Entry:**
  - a post-only limit **buy** at the signal bar's close, working for **one bar** only;
  - **filled only if that bar's low trades *through* the limit by 0.10%**. Touching the price, or trading exactly at it, is not a fill, because we assume we're last in the queue;
  - the fill price is the limit, never better, with a **0.50%** maker fee and no spread or slippage;
  - **an unfilled order is cancelled and the trade is missed.** It is never chased with a market order.
- **Adverse selection is built in:**
  - we're only filled when price moves against us after the signal;
  - we miss the breakouts that run away immediately, which are often the best trades.
  
  The missed-entry rate is reported.
- **Stops** are always taker (stop-market) with stop slippage, active from the fill. If the entry bar's low also reaches the stop, the stop is assumed hit.
- **Signal exits:**
  - a post-only limit **sell** at the exit-signal bar's close, working for one bar;
  - filled only if the high trades through it by 0.10%;
  - **if the stop is also inside that bar, the stop is assumed first**;
  - if unfilled, the exit is a **taker market order at the following open** (0.90% + spread/slippage), and the stop stays active meanwhile.
- **Robustness requirement:** the same parameters must also be profitable (full-history PF > 1) under taker costs. This protects against an optimistic maker model.
- **Limitation, stated plainly:** there is no historical order-book, queue-position or trade-by-trade data for 2017–2026. The fill model is therefore an approximation from OHLC bars:
  - it can't know whether our order would really have been reached in the queue;
  - it can't know the intrabar order of events beyond the worst-case rules above.
  
  The 0.10% trade-through requirement and the no-chase rule are deliberately conservative, but real maker fill rates may be lower still.

### Both cases
- **Sizing:** risk-based, at 1% of equity per trade for research runs. Position value plus fees is capped by cash (no leverage). Orders under $1 are skipped.
- **Equity** is marked to market at every bar close.
- **Windows are isolated:** a trade never spans train/validation/OOS, and trades still open at a window end are closed with a taker order at the open.

## 4. Strategy families and grids (`backtest/strategies_daily.py`)

52 parameter sets per timeframe × 3 timeframes × 2 execution cases = **312 evaluated configurations**. The winner of each (case × timeframe × family) selection gives **30 train-selected candidates**. ATR = Wilder ATR(14). "Turns on" means the entry fires on the bar where the state changes from false to true.

| # | Family | Entry | Exit | Grid |
|---|---|---|---|---|
| 1 | `ema_trend` | EMA(fast) > EMA(slow) **and** close > EMA(fast), when that turns on | stop s×ATR; exit rule `cross`: EMA(fast) < EMA(slow), or `price`: close < EMA(fast), at the next open | (fast, slow) {(20,50), (50,200)} × s {2, 3} × exit {cross, price} = 8 |
| 2 | `breakout` | close > previous-N-bar high; optional filter close > SMA200 | stop s×ATR; close < previous-(N//2)-bar low → next open | N {10, 20, 30, 50} × s {2, 3} × filter {none, sma200} = 16 |
| 3 | `pullback` | strong trend (close > EMA200, EMA50 > EMA200, EMA50 above its value 10 bars ago) **and** a low ≤ EMA(p) within the last 5 bars **and** close > previous-3-bar high | stop s×ATR; then only a chandelier trail at close − t×ATR (ratchets up) | p {20, 50} × s {2, 3} × t {3, 5} = 8 |
| 4 | `regime_trend` | close > SMA(L) **and** ATR%(14) percentile rank over 250 bars ≤ q (q = 100 means no volatility filter), when that turns on | stop s×ATR; close < SMA(L) → next open | L {100, 200} × q {50, 80, 100} × s {3, 5} = 12 |
| 5 | `hybrid` | trend (close > EMA200, EMA50 > EMA200) **and** (close > previous-N-bar high **or** [a low ≤ EMA20 within the last 5 bars and close > previous-3-bar high]) | stop s×ATR; then only a chandelier trail at close − t×ATR | N {20, 30} × s {2, 3} × t {3, 5} = 8 |

## 5. Method (`PAPER_MODE=true python3 -m backtest.daily_study`)

1. **Split:** chronological **70% train / 15% validation / 15% OOS**, per timeframe, never shuffled.
2. **Selection** per (execution case × timeframe × family), on **train only**:
   - a parameter set is eligible if it has ≥ **15** train trades and PF > 1 after costs, in that execution case;
   - score = t-statistic of per-trade net return, averaged with its one-step grid neighbours. This favours stable regions over isolated peaks.
   - **Highest return is never the selection criterion.**
3. **Validation gate:** ≥ **5** trades, PF ≥ **1.20** and expectancy > 0.
4. **OOS:** one look, reported for every selection. Nothing is re-selected afterwards.
5. **Walk-forward:** run for **every** selection (not just validation passers).
   - Rolling **3-year train / 6-month test**, stepped every 6 months.
   - Parameters are re-selected on each training window with the rule in step 2, needing ≥ 8 trades in the window.
   - The test-window trades are combined into one compounded result.
6. **Benchmark:** BTC buy-and-hold (taker in and out, after costs) over the same train, validation, OOS and full periods, and for the $200 simulation.
7. **Reported for every candidate:**
   - trades, win rate, and PF before and after costs;
   - net return, max drawdown, expectancy and Sharpe (from calendar-daily equity);
   - OOS PF and return, walk-forward PF;
   - neighbourhood PFs, best-year share, PF without the best year;
   - best/worst-trade contribution;
   - the $200 simulation;
   - maker vs taker comparison, including the maker missed-entry rate and the share of exits filled as maker.
   
   Deep-dives (by year, by regime, walk-forward folds) are given for PASS / MARGINAL / validation passers. If there are none, they're given for the best 3 by validation PF, labelled INFORMATIONAL.
8. **$200 simulation:** $200 start, **15% risk per trade**, cash-capped, no leverage, long only, after costs, over the full history and the OOS window. This is the paper-trading setting.

## 6. Acceptance criteria (all required for PASS)

| # | Criterion | Threshold |
|---|---|---|
| 1 | Validation gate | passed (§5.3) |
| 2 | OOS | ≥ 5 trades, expectancy > 0 after costs, **PF ≥ 1.5** |
| 3 | Walk-forward | ≥ 20 trades, expectancy > 0 after costs, **PF ≥ 1.5** |
| 4 | Profitable after realistic costs | full-history PF > 1 after costs; ≥ 30 full-history trades |
| 5 | No catastrophic drawdown | full-history max DD ≤ **25%** at 1% risk **and** ≤ **50%** in the $200 / 15%-risk simulation |
| 6 | No single year responsible for most profits | best calendar year ≤ **50%** of full-history net profit **and** PF with that year removed > 1 |
| 7 | Parameter-neighbourhood robustness | median full-history PF (after costs) of the one-step grid neighbours ≥ **1.2** |
| 8 | Not dependent on a tiny group of trades | net profit stays > 0 after removing the best max(2, ⌈5% of trades⌉) trades |
| 9 | Maker case only | the same parameters are profitable (PF > 1) under taker costs |

- **MARGINAL:** every criterion met, except the OOS and/or walk-forward PF is in [1.25, 1.5). It's **reported but not implemented**.
- **Buy-and-hold** is always reported alongside, but beating its return is **not** a criterion. A long-only strategy with much smaller drawdowns can be useful. The report states plainly whether a candidate under- or over-performed it.
- Win rate is reported, never a criterion.

## 7. What happens next

- **If nothing is PASS:**
  - the report says so;
  - **nothing is implemented and no paper session is started**;
  - the reasons for failure and the next research direction are reported.
- **If a candidate is PASS:**
  1. It's implemented as a new named paper strategy; **Version A is not touched**.
  2. Comprehensive tests are added.
  3. `PAPER_MODE=true` and the absence of any live-order path are confirmed, and Coinbase market-data/auth is checked.
  4. Then **stop** and report. **No overnight paper session is started automatically.**
