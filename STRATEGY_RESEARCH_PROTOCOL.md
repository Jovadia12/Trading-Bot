# BTC Intraday Strategy Research: Pre-registered Protocol

Written 2026-09-28, **before any price data was available to this repository**. The strategy grids, selection rules and acceptance criteria below were fixed without seeing any data, and can't have been tuned to it. After the first research run, results are reported under these exact rules; any later change must be recorded as a dated amendment.

---

## 1. Repository inspection (what exists today)

| Question | Finding |
|---|---|
| BTC historical data in the repo | **None.** Only result summaries from earlier work (`accounts_500usd.csv`, `candidates_dev_by_cost.csv`, `dev_landscape.csv`, `versionA_axiom.csv`, `pullback_study.zip`). No OHLCV candles at any timeframe |
| Data used by earlier research | Binance BTC/USDT 1-minute (2018-03 to 2026-09) and Bitstamp BTC/USD (2014–2017), loaded from a Claude Chat sandbox (`/home/claude/data/m1/…`). **Not in this repository** |
| Existing backtester | **None in this repository.** Earlier research used `spotlab/lab.py` (simulator) and `btc_backtester.zip` (Version A); neither was ever committed, so neither could be read or verified. `backtest/candle_fill_model.py` holds only 41 lines of helpers |
| Fees / slippage in earlier work | Modelled in `pullback/plab.py` (`net()`), but that depends on the missing simulator for fills (see RESEARCH_AUDIT.md §11) |
| Entry / exit execution, stop & take-profit detection, look-ahead in earlier work | Can't be verified: the simulator source is missing. The visible code enters at the next open and lags the daily trend filter correctly (RESEARCH_AUDIT.md §11.1) |
| Data reachable from the cloud container | **None.** Every exchange and data host is blocked by the environment's network policy |

**Consequence:** a new backtester was written (§3) and fully unit-tested. Data must be downloaded on a machine with Coinbase access (§2). **No strategy results exist until then.**

## 2. Data

- **Source:** Coinbase Advanced public candles, BTC-USD. This is the intended execution venue.
- **Download command:**
  ```bash
  PAPER_MODE=true python3 -m backtest.fetch_coinbase --start 2017-01-01 --tf 5m 1h
  ```
  - It uses the existing read-only client, with 350 candles per request and pacing.
  - It resumes if interrupted.
  - It writes `research_data/coinbase_btcusd_{5m,1h}.csv.gz`, plus `MANIFEST.json` (SHA-256, date range and a quality report: gaps, duplicates, bad OHLC, zero volume, extreme returns).
  - If API keys work, it also writes `fees.json` with your actual maker/taker rates. Rates only, no secrets.
- **Timeframes:** 15m, 30m and 1h are resampled from 5m (UTC-aligned). The 1h file cross-checks the resampling.
- **Known limitation:** Coinbase candles contain trades only. There is no historical bid/ask, so spread and slippage are modelled (§4), not measured.

## 3. Backtest engine (`backtest/engine.py`): execution rules

- **Signals:** use data up to the **close** of bar *i* only.
- **Entry:** taker at the **open of bar i+1**, paying the taker fee, half-spread and slippage.
- **Stop:** stop-market (taker) when a bar's **low ≤ stop**. If the bar opens below the stop (a gap), the fill is the open. Extra stop slippage applies.
- **Take-profit:** resting limit (maker fee). It fills only if the **high is strictly above** the target; touching isn't enough.
- **Stop and target in the same bar:** the stop is assumed to fill first (worst case).
- **Entry bar:** stops and targets are checked on the entry bar itself, after the open.
- **Signal and time exits:** taker at the next bar's open.
- **Trailing stops:** updated at each close, applied from the next bar.
- **Positions:** one at a time, long only. **Cash is the hard cap** (no leverage), and orders under $1 are skipped.
- **Equity:** marked to market at every bar close, so drawdowns include open-trade losses.
- **Train/test separation:** research windows admit only entries signalled inside the window, and trades still open at the window end are closed there. No trade spans two windows.
- **Tests** (`tests/test_backtest_engine.py`) cover:
  - every execution rule above;
  - exact fee and slippage arithmetic, the cash cap and the minimum order;
  - metrics;
  - a **look-ahead test for all 10 families**: all data after bar *t* is rewritten, and signals up to *t* must not change;
  - the data quality checks, pagination, and a synthetic end-to-end run. A random walk must produce no accepted strategy.

## 4. Cost model (`backtest/costs.py`)

| Component | Value | Status |
|---|---|---|
| Maker fee | 0.50% | Coinbase Advanced US entry tier (the tier a $200 account stays in). UNCONFIRMED; replaced automatically by your account's rates from `research_data/fees.json` |
| Taker fee | 0.90% | as above |
| Half-spread (taker legs) | 0.005% | ASSUMED |
| Slippage (taker legs) | 0.02% | ASSUMED |
| Extra stop slippage | 0.05% | ASSUMED |

A taker-in/taker-out round trip therefore costs about **1.85%** at this tier; with a maker take-profit it is about 1.43%. Every result is reported **after** costs, and a zero-cost ("gross") profit factor is shown alongside for diagnosis only.

> **Expectation, stated in advance:** earlier work in this repo found intraday pullback edges of only +0.06% to +0.27% per trade *before* costs (RESEARCH_AUDIT.md). A strategy on 5m–1h must earn more than ~1.4–1.9% gross **per trade** just to break even at this fee tier. Failing to find an acceptable strategy is a likely, legitimate outcome.

## 5. Strategy families and grids (`backtest/strategies.py`)

Every family has an ATR(14)-based protective stop. EMA and ATR use standard Wilder and EMA definitions.

| # | Family | Entry | Exit | Grid |
|---|---|---|---|---|
| 1 | BB mean reversion | close < lower BB(20,k) | close ≥ middle band; stop s×ATR; 60-bar time stop | k {1.5, 2, 2.5} × s {2, 3} |
| 2 | BB + RSI + EMA | close < lower BB(20,k) & RSI14 < r & close > EMA(e) | middle band; stop 2 ATR; 60 bars | k {1.5, 2, 2.5} × r {30, 40} × e {100, 200} |
| 3 | EMA pullback | EMA50 > EMA200, close > EMA200; low ≤ EMA20 < close; previous close > EMA20 | target t×R, stop s×ATR, 100 bars | s {1.5, 2} × t {1.5, 2, 3} |
| 4 | RSI mean reversion | RSI(n) < level & close > EMA200 | close > SMA5; stop 2.5 ATR; 20 bars | (n, level) {(2,5), (2,10), (2,15), (14,25), (14,30)} |
| 5 | VWAP reversion | close < session VWAP − k×ATR (optionally close > EMA200) | close ≥ VWAP; stop 2 ATR; 96 bars | k {1, 1.5, 2} × trend {on, off} |
| 6 | Momentum | EMA fast crosses above slow | fast < slow; stop s×ATR | (fast, slow) {(10,30), (20,60), (50,150)} × s {2, 3} |
| 7 | Breakout + ATR | close > previous N-bar high | close < previous N/2-bar low; stop s×ATR | N {20, 50, 100} × s {1.5, 2.5} |
| 8 | Volatility regime | BB-width percentile (500 bars) < p, then close > upper BB | target t×R; stop 2 ATR; 100 bars | p {10, 20, 30} × t {2, 3} |
| 9 | Regime switching | ADX ≥ a: 20-bar breakout; ADX < a: close < lower BB | trend: < 10-bar low; range: ≥ middle band; stop s×ATR; 200 bars | a {20, 25, 30} × s {2, 3} |
| 10 | Hybrid | EMA(e) rising & close > EMA(e) & RSI14 < r | chandelier trail t×ATR from the close; initial stop 2 ATR | r {30, 40} × t {2, 3} × e {100, 200} |

That's 67 parameter sets per timeframe × 4 timeframes (5m, 15m, 30m, 1h) = **268 configurations**. That count is reported alongside every result (multiple testing).

## 6. Selection and validation (`backtest/research.py`)

1. **Split:** chronological **70% train / 15% validation / 15% out-of-sample**, per timeframe, never shuffled.
2. **Selection (train only), per family and timeframe:**
   - eligible if ≥ 100 train trades **and** train PF > 1 after costs, at 1% risk;
   - score = t-statistic of per-trade net return, **averaged with its one-step grid neighbours** (favours stable regions over isolated peaks).
3. **Validation gate:** ≥ 30 trades, PF ≥ 1.30 and expectancy > 0.
4. **Out-of-sample:** one look, for all selections. Nothing is re-selected afterwards.
5. **Walk-forward:** for validation passers (or the best 3 by validation PF, labelled INFORMATIONAL if none pass).
   - Rolling 2-year train, 6-month test, 6-month step.
   - Parameters are re-selected on each training window with the rule in step 2.
   - The test trades are combined into one compounded result.
6. **Acceptance** (all required):

| Criterion | Threshold |
|---|---|
| Validation gate | passed |
| OOS profit factor | ≥ 1.5 |
| Walk-forward profit factor | ≥ 1.5 |
| OOS and walk-forward expectancy | > 0 |
| Full-history trades | ≥ 500 |
| Max drawdown (1% risk, full history) | ≤ 25% |

   Win rate is reported but is never a selection criterion.
7. **Only for an accepted strategy:**
   - a full parameter-sensitivity table;
   - bull/bear/sideways and high/low-volatility breakdowns;
   - risk levels 0.5 / 1 / 2 / 3% with Monte Carlo probabilities of large drawdowns and of losing half;
   - a $200 compounding simulation (worst and best month);
   - a 10,000-path Monte Carlo.
8. **If nothing is accepted:** the report says so, and **no strategy is recommended or implemented**.

## 7. Running it

```bash
PAPER_MODE=true python3 -m backtest.fetch_coinbase --start 2017-01-01 --tf 5m 1h   # on your Mac
git add research_data && git commit -m "Add Coinbase BTC-USD research data" && git push
python3 -m backtest.research                                                        # anywhere
```

Outputs go to `research_results/`: `REPORT.md`, `strategy_summary.csv`, `train_grid_results.csv`, `report.json` and, if accepted, `winner*.{json,csv}`.
