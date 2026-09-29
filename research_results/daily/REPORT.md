# BTC Daily / 2-day / 3-day Strategy Study (`daily`)

Generated 2026-09-29 04:07 UTC in 58s by `python3 -m backtest.daily_study`. Pre-registered protocol: `DAILY_STRATEGY_PROTOCOL.md` (committed before this run).

**Not a blind study.** The earlier 5m-6h studies failed and their OOS window (2025-04..2026-09) was already viewed; see the protocol. Only future data (forward paper trading) is a clean test.

**Costs.** Taker legs: 0.90% fee + 0.005% half-spread + 0.020% slippage (+0.050% on stops). Maker legs: 0.50% fee at the limit price. Fee source: user-confirmed Coinbase fee tier (reported 2026-09-29; not fetched via API by this tool) (Intro, 2026-09-29). Spread/slippage ASSUMED.

**Maker model.** Post-only limit at the signal close, valid for one bar, filled only if price trades through it by 0.10%; otherwise the entry is MISSED (never chased) and an unfilled exit falls back to a taker order at the next open. Stops are always taker. No order-book or queue data exists for 2017-2026, so this is an OHLC approximation (see protocol).

**Multiple testing.** 52 parameter sets per timeframe x 3 timeframes x 2 execution cases = 312 evaluated configurations; 30 train-selected candidates.

## Data and splits

- **1d**: 3,558 bars 2017-01-01 -> 2026-09-28; missing 0.0%; bad OHLC 0. Splits: {'train': '2017-01-01..2023-10-26', 'val': '2023-10-26..2025-04-12', 'oos': '2025-04-12..2026-09-28'}
- **2d**: 1,778 bars 2017-01-02 -> 2026-09-26; missing 0.0%; bad OHLC 0. Splits: {'train': '2017-01-02..2023-10-25', 'val': '2023-10-25..2025-04-10', 'oos': '2025-04-10..2026-09-26'}
- **3d**: 1,185 bars 2017-01-03 -> 2026-09-25; missing 0.0%; bad OHLC 0. Splits: {'train': '2017-01-03..2023-10-25', 'val': '2023-10-25..2025-04-10', 'oos': '2025-04-10..2026-09-25'}

## BTC buy-and-hold benchmark (taker in/out, after costs)

| TF | Split | Return | CAGR | Max DD | Sharpe |
|---|---|---|---|---|---|
| 1d | train | 3344.6% | 68.1% | 83.8% | 1.07 |
| 1d | val | 145.1% | 84.8% | 28.2% | 1.43 |
| 1d | oos | -3.9% | -2.7% | 53.1% | 0.14 |
| 1d | full | 8316.8% | 57.6% | 83.8% | 1.01 |
| 2d | train | 3311.4% | 68.0% | 83.5% | 1.06 |
| 2d | val | 137.2% | 81.0% | 26.0% | 1.45 |
| 2d | oos | -0.6% | -0.4% | 52.1% | 0.20 |
| 2d | full | 8250.2% | 57.6% | 83.5% | 1.00 |
| 3d | train | 3248.8% | 67.6% | 83.7% | 1.05 |
| 3d | val | 137.2% | 81.2% | 27.0% | 1.39 |
| 3d | oos | -0.6% | -0.4% | 51.4% | 0.22 |
| 3d | full | 8097.0% | 57.3% | 83.7% | 1.00 |

## Verdict counts: {'FAIL': 30}

**No candidate passed every pre-registered acceptance criterion.** Nothing is implemented and no paper session should be started on the basis of this study.

## Summary of every train-selected candidate (1% risk, after costs)

| Mode | TF | Family | Params | Full trades | Win% | PF before costs | PF after costs | Net return | Max DD | Expectancy | Sharpe | OOS trades | OOS PF | OOS return | WF trades | WF PF | Status | Reasons |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| maker | 1d | breakout | `{"n": 10, "stop_atr": 2.0, "trend_filter": "sma200"}` | 62 | 41.9% | 2.28 | 1.82 | 39.5% | 9.5% | 0.57% | 0.69 | 10 | 0.59 | -2.9% | 45 | 1.65 | FAIL | OOS expectancy <= 0; OOS PF < 1.25; max DD at 15% risk ($200) > 50% |
| maker | 1d | ema_trend | `{"exit_rule": "cross", "pair": [20, 50], "stop_atr": 3.0}` | 30 | 36.7% | 5.66 | 4.84 | 99.2% | 13.4% | 2.60% | 0.83 | 6 | 0.55 | -1.6% | 44 | 2.02 | FAIL | validation gate; OOS expectancy <= 0; OOS PF < 1.25; max DD at 15% risk ($200) > 50% |
| maker | 1d | hybrid | `{"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}` | 30 | 40.0% | 3.89 | 3.35 | 50.2% | 10.2% | 1.52% | 0.67 | 4 | 0.71 | -0.6% | 33 | 1.84 | FAIL | < 5 OOS trades; OOS expectancy <= 0; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit; unprofitable without its best few trades |
| maker | 1d | pullback | `{"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}` | 40 | 37.5% | 2.71 | 2.15 | 38.0% | 8.9% | 0.85% | 0.67 | 6 | 0.18 | -4.8% | 27 | 1.68 | FAIL | OOS expectancy <= 0; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit |
| maker | 1d | regime_trend | `{"sma_n": 200, "stop_atr": 5.0, "vol_pct": 50}` | 24 | 33.3% | 8.48 | 6.98 | 31.2% | 11.3% | 1.18% | 0.56 | 2 | inf | 2.3% | 39 | 2.73 | FAIL | < 5 OOS trades; < 30 full-history trades; max DD at 15% risk ($200) > 50% |
| maker | 2d | breakout | `{"n": 20, "stop_atr": 3.0, "trend_filter": "none"}` | 27 | 44.4% | 4.89 | 4.23 | 43.5% | 8.5% | 1.46% | 0.69 | 7 | 0.26 | -3.4% | 33 | 1.83 | FAIL | validation gate; OOS expectancy <= 0; OOS PF < 1.25; < 30 full-history trades; best year > 50% of net profit |
| maker | 2d | ema_trend | `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` | 47 | 31.9% | 7.02 | 5.46 | 55.8% | 6.4% | 1.03% | 0.93 | 8 | 0.89 | -0.2% | 37 | 3.52 | FAIL | OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit |
| maker | 2d | hybrid | `{"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}` | 30 | 33.3% | 1.99 | 1.72 | 10.0% | 8.3% | 0.35% | 0.38 | 3 | 1.13 | 0.2% | 25 | 1.39 | FAIL | < 5 OOS trades; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit; PF without best year <= 1; unprofitable without its best few trades; walk-forward PF 1.39 < 1.5 |
| maker | 2d | pullback | – | – | – | – | – | – | – | – | – | – | – | – | – | – | FAIL | no parameter set with >= 15 train trades and PF > 1 after costs |
| maker | 2d | regime_trend | – | – | – | – | – | – | – | – | – | – | – | – | – | – | FAIL | no parameter set with >= 15 train trades and PF > 1 after costs |
| maker | 3d | breakout | `{"n": 10, "stop_atr": 3.0, "trend_filter": "none"}` | 32 | 46.9% | 3.92 | 3.51 | 34.3% | 6.4% | 0.99% | 0.69 | 7 | 0.40 | -2.4% | 21 | 2.27 | FAIL | OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit |
| maker | 3d | ema_trend | `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` | 42 | 31.0% | 4.23 | 3.55 | 27.4% | 6.8% | 0.62% | 0.68 | 6 | 0.80 | -0.2% | 32 | 2.05 | FAIL | OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit; unprofitable without its best few trades |
| maker | 3d | hybrid | – | – | – | – | – | – | – | – | – | – | – | – | – | – | FAIL | no parameter set with >= 15 train trades and PF > 1 after costs |
| maker | 3d | pullback | – | – | – | – | – | – | – | – | – | – | – | – | – | – | FAIL | no parameter set with >= 15 train trades and PF > 1 after costs |
| maker | 3d | regime_trend | `{"sma_n": 100, "stop_atr": 5.0, "vol_pct": 100}` | 21 | 42.9% | 6.08 | 5.14 | 9.8% | 7.5% | 0.45% | 0.40 | 2 | 1.48 | 0.1% | 6 | 1.38 | FAIL | validation gate; < 5 OOS trades; < 20 walk-forward trades; < 30 full-history trades; best year > 50% of net profit; OOS PF 1.48 < 1.5; walk-forward PF 1.38 < 1.5 |
| taker | 1d | breakout | `{"n": 10, "stop_atr": 2.0, "trend_filter": "sma200"}` | 62 | 41.9% | 2.50 | 1.77 | 36.9% | 10.3% | 0.54% | 0.65 | 10 | 0.60 | -2.6% | 42 | 1.81 | FAIL | validation gate; OOS expectancy <= 0; OOS PF < 1.25 |
| taker | 1d | ema_trend | `{"exit_rule": "cross", "pair": [20, 50], "stop_atr": 3.0}` | 31 | 32.3% | 5.53 | 4.42 | 96.0% | 13.6% | 2.47% | 0.80 | 6 | 0.72 | -1.1% | 45 | 1.85 | FAIL | validation gate; OOS expectancy <= 0; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit |
| taker | 1d | hybrid | `{"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}` | 30 | 40.0% | 4.04 | 3.35 | 49.7% | 10.4% | 1.51% | 0.67 | 4 | 1.03 | 0.0% | 33 | 1.82 | FAIL | < 5 OOS trades; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit; unprofitable without its best few trades |
| taker | 1d | pullback | `{"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}` | 40 | 40.0% | 2.86 | 2.13 | 37.3% | 8.7% | 0.84% | 0.66 | 6 | 0.23 | -4.2% | 28 | 1.58 | FAIL | OOS expectancy <= 0; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit |
| taker | 1d | regime_trend | `{"sma_n": 100, "stop_atr": 5.0, "vol_pct": 100}` | 60 | 20.0% | 7.02 | 4.26 | 51.8% | 10.3% | 0.75% | 0.80 | 10 | 1.13 | 0.3% | 39 | 3.04 | FAIL | OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit |
| taker | 2d | breakout | `{"n": 20, "stop_atr": 3.0, "trend_filter": "none"}` | 27 | 48.1% | 5.14 | 4.15 | 42.4% | 8.9% | 1.43% | 0.67 | 7 | 0.30 | -3.1% | 33 | 1.83 | FAIL | validation gate; OOS expectancy <= 0; OOS PF < 1.25; < 30 full-history trades; max DD at 15% risk ($200) > 50%; best year > 50% of net profit |
| taker | 2d | ema_trend | `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` | 48 | 31.2% | 7.44 | 4.68 | 52.3% | 6.6% | 0.96% | 0.88 | 9 | 0.54 | -1.0% | 38 | 2.67 | FAIL | OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit |
| taker | 2d | hybrid | `{"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}` | 30 | 33.3% | 1.99 | 1.65 | 9.3% | 8.4% | 0.32% | 0.35 | 3 | 1.05 | 0.1% | 25 | 1.32 | FAIL | < 5 OOS trades; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit; PF without best year <= 1; unprofitable without its best few trades; walk-forward PF 1.32 < 1.5 |
| taker | 2d | pullback | – | – | – | – | – | – | – | – | – | – | – | – | – | – | FAIL | no parameter set with >= 15 train trades and PF > 1 after costs |
| taker | 2d | regime_trend | `{"sma_n": 100, "stop_atr": 3.0, "vol_pct": 100}` | 26 | 26.9% | 6.69 | 4.68 | 26.7% | 11.9% | 0.96% | 0.51 | 5 | 2.07 | 1.0% | 10 | 6.78 | FAIL | validation gate; < 20 walk-forward trades; < 30 full-history trades; max DD at 15% risk ($200) > 50% |
| taker | 3d | breakout | `{"n": 10, "stop_atr": 3.0, "trend_filter": "none"}` | 32 | 46.9% | 4.71 | 3.85 | 34.7% | 6.4% | 1.00% | 0.70 | 7 | 0.43 | -2.0% | 21 | 2.25 | FAIL | OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit |
| taker | 3d | ema_trend | `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` | 43 | 30.2% | 5.28 | 3.82 | 32.3% | 7.3% | 0.70% | 0.71 | 6 | 0.56 | -0.5% | 32 | 2.29 | FAIL | OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit |
| taker | 3d | hybrid | – | – | – | – | – | – | – | – | – | – | – | – | – | – | FAIL | no parameter set with >= 15 train trades and PF > 1 after costs |
| taker | 3d | pullback | – | – | – | – | – | – | – | – | – | – | – | – | – | – | FAIL | no parameter set with >= 15 train trades and PF > 1 after costs |
| taker | 3d | regime_trend | `{"sma_n": 100, "stop_atr": 5.0, "vol_pct": 100}` | 21 | 38.1% | 6.07 | 4.50 | 9.3% | 7.6% | 0.43% | 0.38 | 2 | 1.25 | 0.1% | 6 | 1.29 | FAIL | validation gate; < 5 OOS trades; < 20 walk-forward trades; < 30 full-history trades; best year > 50% of net profit; OOS PF 1.25 < 1.5; walk-forward PF 1.29 < 1.5 |

## Maker vs taker (each case selects its own parameters on train)

| TF | Family | Taker params | Taker full PF | Taker OOS PF | Taker WF PF | Maker params | Maker full PF | Maker OOS PF | Maker WF PF | Maker missed entries (full) | Maker exits filled as maker | Maker params under taker costs PF |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1d | ema_trend | `{"exit_rule": "cross", "pair": [20, 50], "stop_atr": 3.0}` | 4.42 | 0.72 | 1.85 | `{"exit_rule": "cross", "pair": [20, 50], "stop_atr": 3.0}` | 4.84 | 0.55 | 2.02 | 6% | 94% | 4.42 |
| 1d | breakout | `{"n": 10, "stop_atr": 2.0, "trend_filter": "sma200"}` | 1.77 | 0.60 | 1.81 | `{"n": 10, "stop_atr": 2.0, "trend_filter": "sma200"}` | 1.82 | 0.59 | 1.65 | 3% | 97% | 1.77 |
| 1d | pullback | `{"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}` | 2.13 | 0.23 | 1.58 | `{"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}` | 2.15 | 0.18 | 1.68 | 9% | n/a | 2.13 |
| 1d | regime_trend | `{"sma_n": 100, "stop_atr": 5.0, "vol_pct": 100}` | 4.26 | 1.13 | 3.04 | `{"sma_n": 200, "stop_atr": 5.0, "vol_pct": 50}` | 6.98 | inf | 2.73 | 0% | 100% | 6.06 |
| 1d | hybrid | `{"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}` | 3.35 | 1.03 | 1.82 | `{"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}` | 3.35 | 0.71 | 1.84 | 6% | n/a | 3.35 |
| 2d | ema_trend | `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` | 4.68 | 0.54 | 2.67 | `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` | 5.46 | 0.89 | 3.52 | 2% | 98% | 4.68 |
| 2d | breakout | `{"n": 20, "stop_atr": 3.0, "trend_filter": "none"}` | 4.15 | 0.30 | 1.83 | `{"n": 20, "stop_atr": 3.0, "trend_filter": "none"}` | 4.23 | 0.26 | 1.83 | 7% | 100% | 4.15 |
| 2d | pullback | none eligible | n/a | n/a | n/a | none eligible | n/a | n/a | n/a | n/a | n/a | n/a |
| 2d | regime_trend | `{"sma_n": 100, "stop_atr": 3.0, "vol_pct": 100}` | 4.68 | 2.07 | 6.78 | none eligible | n/a | n/a | n/a | n/a | n/a | n/a |
| 2d | hybrid | `{"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}` | 1.65 | 1.05 | 1.32 | `{"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}` | 1.72 | 1.13 | 1.39 | 0% | n/a | 1.65 |
| 3d | ema_trend | `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` | 3.82 | 0.56 | 2.29 | `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` | 3.55 | 0.80 | 2.05 | 2% | 100% | 3.82 |
| 3d | breakout | `{"n": 10, "stop_atr": 3.0, "trend_filter": "none"}` | 3.85 | 0.43 | 2.25 | `{"n": 10, "stop_atr": 3.0, "trend_filter": "none"}` | 3.51 | 0.40 | 2.27 | 0% | 100% | 3.85 |
| 3d | pullback | none eligible | n/a | n/a | n/a | none eligible | n/a | n/a | n/a | n/a | n/a | n/a |
| 3d | regime_trend | `{"sma_n": 100, "stop_atr": 5.0, "vol_pct": 100}` | 4.50 | 1.25 | 1.29 | `{"sma_n": 100, "stop_atr": 5.0, "vol_pct": 100}` | 5.14 | 1.48 | 1.38 | 0% | 100% | 4.50 |
| 3d | hybrid | none eligible | n/a | n/a | n/a | none eligible | n/a | n/a | n/a | n/a | n/a | n/a |

## Split detail (1% risk, after costs)

| Mode | TF | Family | Split | Trades | Win% | PF before costs | PF after costs | Expectancy | Net return | Max DD | Sharpe | Exposure | Fees |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| maker | 1d | breakout | train | 38 | 47.4% | 3.17 | 2.58 | 0.87% | 37.6% | 7.8% | 0.89 | 27% | $637 |
| maker | 1d | breakout | val | 15 | 33.3% | 1.68 | 1.33 | 0.26% | 3.5% | 5.7% | 0.47 | 40% | $250 |
| maker | 1d | breakout | oos | 10 | 30.0% | 0.89 | 0.59 | -0.29% | -2.9% | 6.4% | -0.53 | 26% | $226 |
| maker | 1d | breakout | full | 62 | 41.9% | 2.28 | 1.82 | 0.57% | 39.5% | 9.5% | 0.69 | 29% | $1,276 |
| maker | 1d | ema_trend | train | 21 | 38.1% | 6.85 | 6.01 | 3.11% | 77.2% | 13.4% | 0.88 | 49% | $329 |
| maker | 1d | ema_trend | val | 4 | 50.0% | 7.21 | 6.09 | 2.04% | 8.3% | 5.4% | 1.06 | 67% | $45 |
| maker | 1d | ema_trend | oos | 6 | 33.3% | 0.76 | 0.55 | -0.27% | -1.6% | 5.4% | -0.41 | 40% | $89 |
| maker | 1d | ema_trend | full | 30 | 36.7% | 5.66 | 4.84 | 2.60% | 99.2% | 13.4% | 0.83 | 51% | $571 |
| maker | 1d | hybrid | train | 21 | 47.6% | 4.18 | 3.72 | 1.63% | 35.9% | 10.2% | 0.73 | 41% | $266 |
| maker | 1d | hybrid | val | 7 | 28.6% | 2.69 | 2.22 | 0.71% | 4.9% | 7.4% | 0.59 | 92% | $87 |
| maker | 1d | hybrid | oos | 4 | 25.0% | 1.04 | 0.71 | -0.13% | -0.6% | 3.3% | -0.15 | 37% | $59 |
| maker | 1d | hybrid | full | 30 | 40.0% | 3.89 | 3.35 | 1.52% | 50.2% | 10.2% | 0.67 | 49% | $447 |
| maker | 1d | pullback | train | 27 | 44.4% | 3.15 | 2.56 | 0.93% | 27.5% | 7.1% | 0.80 | 22% | $483 |
| maker | 1d | pullback | val | 8 | 37.5% | 3.45 | 2.68 | 1.14% | 9.0% | 6.6% | 0.96 | 41% | $172 |
| maker | 1d | pullback | oos | 6 | 16.7% | 0.29 | 0.18 | -0.81% | -4.8% | 4.8% | -1.43 | 15% | $150 |
| maker | 1d | pullback | full | 40 | 37.5% | 2.71 | 2.15 | 0.85% | 38.0% | 8.9% | 0.67 | 25% | $906 |
| maker | 1d | regime_trend | train | 17 | 29.4% | 7.89 | 6.60 | 1.17% | 20.9% | 11.3% | 0.52 | 44% | $104 |
| maker | 1d | regime_trend | val | 6 | 33.3% | 5.56 | 4.41 | 0.69% | 4.1% | 3.7% | 0.67 | 79% | $38 |
| maker | 1d | regime_trend | oos | 2 | 100.0% | inf | inf | 1.16% | 2.3% | 1.1% | 0.92 | 41% | $20 |
| maker | 1d | regime_trend | full | 24 | 33.3% | 8.48 | 6.98 | 1.18% | 31.2% | 11.3% | 0.56 | 49% | $165 |
| maker | 2d | breakout | train | 18 | 50.0% | 8.09 | 7.17 | 2.10% | 41.1% | 8.5% | 0.82 | 43% | $158 |
| maker | 2d | breakout | val | 3 | 100.0% | inf | inf | 1.46% | 4.4% | 2.1% | 0.86 | 67% | $25 |
| maker | 2d | breakout | oos | 7 | 14.3% | 0.32 | 0.26 | -0.49% | -3.4% | 5.0% | -1.30 | 35% | $70 |
| maker | 2d | breakout | full | 27 | 44.4% | 4.89 | 4.23 | 1.46% | 43.5% | 8.5% | 0.69 | 46% | $282 |
| maker | 2d | ema_trend | train | 29 | 31.0% | 12.25 | 9.40 | 1.46% | 47.5% | 6.4% | 1.01 | 36% | $230 |
| maker | 2d | ema_trend | val | 10 | 30.0% | 2.62 | 2.15 | 0.35% | 3.5% | 3.0% | 0.84 | 47% | $67 |
| maker | 2d | ema_trend | oos | 8 | 37.5% | 1.50 | 0.89 | -0.02% | -0.2% | 2.6% | -0.07 | 33% | $70 |
| maker | 2d | ema_trend | full | 47 | 31.9% | 7.02 | 5.46 | 1.03% | 55.8% | 6.4% | 0.93 | 40% | $436 |
| maker | 2d | hybrid | train | 21 | 33.3% | 1.96 | 1.72 | 0.34% | 6.7% | 8.3% | 0.36 | 41% | $139 |
| maker | 2d | hybrid | val | 8 | 37.5% | 1.87 | 1.55 | 0.24% | 1.9% | 4.5% | 0.44 | 80% | $70 |
| maker | 2d | hybrid | oos | 3 | 33.3% | 1.46 | 1.13 | 0.06% | 0.2% | 2.2% | 0.08 | 33% | $32 |
| maker | 2d | hybrid | full | 30 | 33.3% | 1.99 | 1.72 | 0.35% | 10.0% | 8.3% | 0.38 | 46% | $229 |
| maker | 3d | breakout | train | 21 | 52.4% | 7.61 | 6.81 | 1.47% | 33.7% | 6.4% | 0.85 | 53% | $127 |
| maker | 3d | breakout | val | 5 | 60.0% | 2.51 | 2.24 | 0.43% | 2.1% | 3.1% | 0.54 | 65% | $31 |
| maker | 3d | breakout | oos | 7 | 28.6% | 0.48 | 0.40 | -0.35% | -2.4% | 4.0% | -1.05 | 40% | $51 |
| maker | 3d | breakout | full | 32 | 46.9% | 3.92 | 3.51 | 0.99% | 34.3% | 6.4% | 0.69 | 53% | $226 |
| maker | 3d | ema_trend | train | 28 | 25.0% | 5.03 | 4.26 | 0.78% | 22.2% | 6.8% | 0.72 | 35% | $149 |
| maker | 3d | ema_trend | val | 8 | 37.5% | 2.63 | 2.27 | 0.35% | 2.8% | 3.1% | 0.81 | 56% | $40 |
| maker | 3d | ema_trend | oos | 6 | 50.0% | 1.33 | 0.80 | -0.03% | -0.2% | 1.9% | -0.09 | 33% | $44 |
| maker | 3d | ema_trend | full | 42 | 31.0% | 4.23 | 3.55 | 0.62% | 27.4% | 6.8% | 0.68 | 41% | $252 |
| maker | 3d | regime_trend | train | 17 | 35.3% | 4.50 | 3.81 | 0.35% | 6.0% | 7.5% | 0.34 | 47% | $48 |
| maker | 3d | regime_trend | val | 1 | 100.0% | inf | inf | 0.75% | 0.7% | 1.2% | 0.51 | 40% | $3 |
| maker | 3d | regime_trend | oos | 2 | 50.0% | 2.04 | 1.48 | 0.05% | 0.1% | 0.3% | 0.17 | 8% | $9 |
| maker | 3d | regime_trend | full | 21 | 42.9% | 6.08 | 5.14 | 0.45% | 9.8% | 7.5% | 0.40 | 55% | $64 |
| taker | 1d | breakout | train | 38 | 47.4% | 3.45 | 2.53 | 0.85% | 36.3% | 6.8% | 0.87 | 27% | $987 |
| taker | 1d | breakout | val | 15 | 26.7% | 1.68 | 1.19 | 0.17% | 2.1% | 6.0% | 0.30 | 39% | $375 |
| taker | 1d | breakout | oos | 10 | 40.0% | 1.23 | 0.60 | -0.25% | -2.6% | 6.9% | -0.45 | 26% | $342 |
| taker | 1d | breakout | full | 62 | 41.9% | 2.50 | 1.77 | 0.54% | 36.9% | 10.3% | 0.65 | 28% | $1,945 |
| taker | 1d | ema_trend | train | 22 | 31.8% | 6.43 | 5.34 | 2.88% | 73.9% | 13.6% | 0.85 | 49% | $499 |
| taker | 1d | ema_trend | val | 4 | 50.0% | 7.21 | 5.57 | 1.96% | 7.9% | 5.6% | 1.02 | 67% | $75 |
| taker | 1d | ema_trend | oos | 6 | 33.3% | 1.10 | 0.72 | -0.18% | -1.1% | 5.4% | -0.24 | 44% | $138 |
| taker | 1d | ema_trend | full | 31 | 32.3% | 5.53 | 4.42 | 2.47% | 96.0% | 13.6% | 0.80 | 51% | $889 |
| taker | 1d | hybrid | train | 21 | 42.9% | 4.16 | 3.57 | 1.60% | 34.9% | 10.4% | 0.71 | 41% | $330 |
| taker | 1d | hybrid | val | 7 | 28.6% | 2.70 | 2.11 | 0.67% | 4.6% | 7.5% | 0.56 | 92% | $111 |
| taker | 1d | hybrid | oos | 4 | 50.0% | 1.81 | 1.03 | 0.01% | 0.0% | 2.9% | 0.02 | 37% | $76 |
| taker | 1d | hybrid | full | 30 | 40.0% | 4.04 | 3.35 | 1.51% | 49.7% | 10.4% | 0.67 | 49% | $557 |
| taker | 1d | pullback | train | 27 | 44.4% | 3.18 | 2.44 | 0.89% | 26.2% | 7.2% | 0.77 | 23% | $608 |
| taker | 1d | pullback | val | 8 | 37.5% | 3.51 | 2.56 | 1.12% | 8.8% | 6.8% | 0.94 | 42% | $217 |
| taker | 1d | pullback | oos | 6 | 33.3% | 0.47 | 0.23 | -0.70% | -4.2% | 4.5% | -1.13 | 16% | $195 |
| taker | 1d | pullback | full | 40 | 40.0% | 2.86 | 2.13 | 0.84% | 37.3% | 8.7% | 0.66 | 25% | $1,142 |
| taker | 1d | regime_trend | train | 38 | 23.7% | 8.16 | 5.46 | 0.99% | 41.6% | 10.3% | 0.86 | 49% | $444 |
| taker | 1d | regime_trend | val | 12 | 8.3% | 2.48 | 1.33 | 0.06% | 0.7% | 1.7% | 0.25 | 38% | $110 |
| taker | 1d | regime_trend | oos | 10 | 20.0% | 2.55 | 1.13 | 0.03% | 0.3% | 2.9% | 0.12 | 44% | $133 |
| taker | 1d | regime_trend | full | 60 | 20.0% | 7.02 | 4.26 | 0.75% | 51.8% | 10.3% | 0.80 | 52% | $818 |
| taker | 2d | breakout | train | 18 | 50.0% | 8.10 | 6.67 | 2.05% | 39.9% | 8.9% | 0.80 | 42% | $263 |
| taker | 2d | breakout | val | 3 | 100.0% | inf | inf | 1.39% | 4.2% | 2.2% | 0.82 | 66% | $45 |
| taker | 2d | breakout | oos | 7 | 28.6% | 0.44 | 0.30 | -0.44% | -3.1% | 4.7% | -1.15 | 35% | $104 |
| taker | 2d | breakout | full | 27 | 48.1% | 5.14 | 4.15 | 1.43% | 42.4% | 8.9% | 0.67 | 45% | $458 |
| taker | 2d | ema_trend | train | 29 | 31.0% | 12.75 | 8.02 | 1.42% | 45.7% | 6.6% | 0.98 | 34% | $398 |
| taker | 2d | ema_trend | val | 10 | 30.0% | 3.06 | 2.11 | 0.34% | 3.3% | 2.9% | 0.81 | 43% | $116 |
| taker | 2d | ema_trend | oos | 9 | 33.3% | 1.37 | 0.54 | -0.11% | -1.0% | 3.2% | -0.37 | 32% | $139 |
| taker | 2d | ema_trend | full | 48 | 31.2% | 7.44 | 4.68 | 0.96% | 52.3% | 6.6% | 0.88 | 37% | $788 |
| taker | 2d | hybrid | train | 21 | 33.3% | 1.96 | 1.66 | 0.32% | 6.3% | 8.4% | 0.34 | 41% | $176 |
| taker | 2d | hybrid | val | 8 | 37.5% | 1.87 | 1.48 | 0.21% | 1.7% | 4.6% | 0.40 | 80% | $89 |
| taker | 2d | hybrid | oos | 3 | 33.3% | 1.46 | 1.05 | 0.03% | 0.1% | 2.3% | 0.04 | 33% | $42 |
| taker | 2d | hybrid | full | 30 | 33.3% | 1.99 | 1.65 | 0.32% | 9.3% | 8.4% | 0.35 | 46% | $290 |
| taker | 2d | regime_trend | train | 15 | 26.7% | 6.89 | 5.28 | 1.17% | 18.2% | 11.9% | 0.49 | 40% | $163 |
| taker | 2d | regime_trend | val | 6 | 16.7% | 1.22 | 0.71 | -0.07% | -0.4% | 3.1% | -0.10 | 34% | $61 |
| taker | 2d | regime_trend | oos | 5 | 40.0% | 3.96 | 2.07 | 0.21% | 1.0% | 2.1% | 0.41 | 42% | $67 |
| taker | 2d | regime_trend | full | 26 | 26.9% | 6.69 | 4.68 | 0.96% | 26.7% | 11.9% | 0.51 | 46% | $331 |
| taker | 3d | breakout | train | 21 | 52.4% | 8.33 | 6.81 | 1.45% | 33.1% | 6.4% | 0.84 | 51% | $215 |
| taker | 3d | breakout | val | 5 | 60.0% | 3.62 | 2.85 | 0.48% | 2.4% | 2.7% | 0.62 | 62% | $54 |
| taker | 3d | breakout | oos | 7 | 28.6% | 0.60 | 0.43 | -0.28% | -2.0% | 3.5% | -0.89 | 38% | $76 |
| taker | 3d | breakout | full | 32 | 46.9% | 4.71 | 3.85 | 1.00% | 34.7% | 6.4% | 0.70 | 51% | $375 |
| taker | 3d | ema_trend | train | 29 | 27.6% | 5.84 | 4.41 | 0.88% | 26.7% | 7.3% | 0.75 | 37% | $274 |
| taker | 3d | ema_trend | val | 8 | 25.0% | 4.30 | 2.98 | 0.41% | 3.2% | 2.6% | 0.97 | 52% | $71 |
| taker | 3d | ema_trend | oos | 6 | 50.0% | 1.33 | 0.56 | -0.08% | -0.5% | 2.1% | -0.25 | 30% | $74 |
| taker | 3d | ema_trend | full | 43 | 30.2% | 5.28 | 3.82 | 0.70% | 32.3% | 7.3% | 0.71 | 41% | $465 |
| taker | 3d | regime_trend | train | 17 | 29.4% | 4.49 | 3.35 | 0.33% | 5.6% | 7.6% | 0.32 | 45% | $83 |
| taker | 3d | regime_trend | val | 1 | 100.0% | inf | inf | 0.73% | 0.7% | 1.2% | 0.49 | 39% | $5 |
| taker | 3d | regime_trend | oos | 2 | 50.0% | 2.04 | 1.25 | 0.03% | 0.1% | 0.4% | 0.10 | 7% | $14 |
| taker | 3d | regime_trend | full | 21 | 38.1% | 6.07 | 4.50 | 0.43% | 9.3% | 7.6% | 0.38 | 53% | $111 |

## Robustness (full history, after costs)

| Mode | TF | Family | Neighbour PFs | Neighbour median | Best year | Best-year share | PF w/o best year | Best trade share | Top-3 share | Net w/o top k (k) | Worst trade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| maker | 1d | breakout | [4.88, 1.83, 1.5] | 1.83 | 2017 | 31% | 1.58 | 26% | 69% | $383 (4) | -1.3% |
| maker | 1d | ema_trend | [10.0, 4.26, 1.81] | 4.26 | 2021 | 50% | 2.93 | 49% | 88% | $2,678 (2) | -1.2% |
| maker | 1d | hybrid | [3.35, 3.33, 1.4] | 3.33 | 2021 | 55% | 2.23 | 59% | 117% | $-124 (2) | -1.2% |
| maker | 1d | pullback | [2.8, 2.16, 4.5] | 2.80 | 2024 | 70% | 1.40 | 37% | 87% | $1,364 (2) | -1.3% |
| maker | 1d | regime_trend | [4.15, 6.89, 6.65] | 6.65 | 2021 | 38% | 6.39 | 43% | 85% | $879 (2) | -0.6% |
| maker | 2d | breakout | [3.25, 6.52, 4.43, 6.7] | 5.47 | 2021 | 69% | 2.02 | 69% | 96% | $674 (2) | -1.1% |
| maker | 2d | ema_trend | [3.64, 5.13, 5.88] | 5.13 | 2021 | 55% | 3.35 | 56% | 84% | $920 (3) | -1.1% |
| maker | 2d | hybrid | [1.72, 1.6, 3.5] | 1.72 | 2021 | 102% | 0.99 | 111% | 177% | $-479 (2) | -1.1% |
| maker | 3d | breakout | [7.62, 3.93, 5.24] | 5.24 | 2021 | 66% | 1.84 | 64% | 93% | $712 (2) | -1.1% |
| maker | 3d | ema_trend | [3.83, 3.23, 10.0] | 3.83 | 2021 | 71% | 1.85 | 74% | 105% | $-150 (3) | -1.1% |
| maker | 3d | regime_trend | [6.48, 5.45, 4.75] | 5.45 | 2021 | 53% | 3.22 | 56% | 106% | $88 (2) | -0.6% |
| taker | 1d | breakout | [4.62, 1.88, 1.47] | 1.88 | 2017 | 32% | 1.54 | 29% | 74% | $149 (4) | -1.4% |
| taker | 1d | ema_trend | [10.0, 4.24, 1.59] | 4.24 | 2021 | 50% | 2.70 | 49% | 90% | $2,515 (2) | -1.3% |
| taker | 1d | hybrid | [3.35, 3.32, 1.36] | 3.32 | 2021 | 55% | 2.24 | 59% | 117% | $-131 (2) | -1.2% |
| taker | 1d | pullback | [2.65, 2.18, 4.54] | 2.65 | 2024 | 70% | 1.40 | 37% | 87% | $1,344 (2) | -1.4% |
| taker | 1d | regime_trend | [4.99, 4.02, 3.71] | 4.02 | 2021 | 50% | 2.79 | 50% | 88% | $604 (3) | -0.6% |
| taker | 2d | breakout | [2.99, 6.35, 4.41, 6.19] | 5.30 | 2021 | 70% | 1.97 | 70% | 97% | $608 (2) | -1.2% |
| taker | 2d | ema_trend | [3.29, 4.24, 5.7] | 4.24 | 2021 | 58% | 2.83 | 59% | 88% | $623 (3) | -0.8% |
| taker | 2d | hybrid | [1.65, 1.53, 3.4] | 1.65 | 2021 | 108% | 0.94 | 119% | 188% | $-539 (2) | -1.1% |
| taker | 2d | regime_trend | [10.0, 5.14, 4.94] | 5.14 | 2021 | 42% | 4.20 | 51% | 105% | $319 (2) | -0.8% |
| taker | 3d | breakout | [8.17, 3.87, 5.87] | 5.87 | 2021 | 65% | 2.01 | 62% | 91% | $784 (2) | -1.1% |
| taker | 3d | ema_trend | [4.01, 3.75, 10.0] | 4.01 | 2021 | 62% | 2.26 | 65% | 96% | $141 (3) | -1.1% |
| taker | 3d | regime_trend | [5.81, 5.01, 4.21] | 5.01 | 2021 | 55% | 2.83 | 58% | 110% | $45 (2) | -0.6% |

## $200 simulation (15% risk per trade, cash-capped, no leverage, long only, after costs)

| Mode | TF | Family | Full: end $ | Return | CAGR | Max DD | Trades | Fees $ | Worst month | Best month | OOS: end $ | OOS max DD | B&H full end $ | B&H OOS end $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| maker | 1d | breakout | $1,251.37 | 526% | 20.7% | 51.6% | 62 | $783.08 | -19.4% | 65.8% | $172.29 | 30.3% | $16,833.67 | $192.16 |
| maker | 1d | ema_trend | $5,738.82 | 2769% | 41.2% | 63.1% | 30 | $892.23 | -29.4% | 62.3% | $186.04 | 34.9% | $16,833.67 | $192.16 |
| maker | 1d | hybrid | $1,297.01 | 549% | 21.2% | 64.9% | 30 | $309.83 | -22.2% | 60.0% | $189.28 | 27.9% | $16,833.67 | $192.16 |
| maker | 1d | pullback | $1,235.27 | 518% | 20.6% | 54.3% | 40 | $549.99 | -25.2% | 41.3% | $154.47 | 23.1% | $16,833.67 | $192.16 |
| maker | 1d | regime_trend | $2,488.78 | 1144% | 29.5% | 57.2% | 24 | $206.84 | -33.6% | 62.3% | $262.12 | 12.9% | $16,833.67 | $192.16 |
| maker | 2d | breakout | $2,930.09 | 1365% | 31.8% | 49.9% | 27 | $623.48 | -23.0% | 60.8% | $137.10 | 45.3% | $16,700.35 | $198.88 |
| maker | 2d | ema_trend | $6,296.53 | 3048% | 42.5% | 40.2% | 47 | $1,568.32 | -19.9% | 60.8% | $197.02 | 26.0% | $16,700.35 | $198.88 |
| maker | 2d | hybrid | $302.51 | 51% | 4.3% | 59.8% | 30 | $74.11 | -19.0% | 50.3% | $203.15 | 25.4% | $16,700.35 | $198.88 |
| maker | 3d | breakout | $2,442.13 | 1121% | 29.3% | 46.1% | 32 | $563.70 | -16.2% | 57.5% | $135.03 | 46.1% | $16,393.92 | $198.88 |
| maker | 3d | ema_trend | $1,370.21 | 585% | 21.9% | 42.0% | 42 | $257.80 | -16.9% | 57.5% | $196.70 | 23.1% | $16,393.92 | $198.88 |
| maker | 3d | regime_trend | $591.76 | 196% | 11.8% | 48.4% | 21 | $31.88 | -26.0% | 31.4% | $202.93 | 4.9% | $16,393.92 | $198.88 |
| taker | 1d | breakout | $1,083.69 | 442% | 18.9% | 48.5% | 62 | $1,081.99 | -20.1% | 65.0% | $176.58 | 32.1% | $16,833.67 | $192.16 |
| taker | 1d | ema_trend | $4,298.95 | 2049% | 37.0% | 64.1% | 31 | $1,039.98 | -29.9% | 62.3% | $189.36 | 35.1% | $16,833.67 | $192.16 |
| taker | 1d | hybrid | $1,256.50 | 528% | 20.8% | 65.7% | 30 | $371.44 | -22.5% | 60.8% | $199.27 | 25.2% | $16,833.67 | $192.16 |
| taker | 1d | pullback | $1,175.00 | 487% | 19.9% | 54.7% | 40 | $658.24 | -24.8% | 41.4% | $161.26 | 20.9% | $16,833.67 | $192.16 |
| taker | 1d | regime_trend | $4,889.53 | 2345% | 38.9% | 57.0% | 60 | $2,354.64 | -19.7% | 52.8% | $198.57 | 32.9% | $16,833.67 | $192.16 |
| taker | 2d | breakout | $2,666.26 | 1233% | 30.5% | 50.5% | 27 | $896.85 | -23.1% | 60.8% | $141.61 | 43.3% | $16,700.35 | $198.88 |
| taker | 2d | ema_trend | $4,845.38 | 2323% | 38.8% | 41.3% | 48 | $2,436.63 | -20.6% | 60.8% | $179.72 | 31.1% | $16,700.35 | $198.88 |
| taker | 2d | hybrid | $276.30 | 38% | 3.4% | 61.0% | 30 | $90.08 | -19.3% | 50.5% | $200.84 | 26.0% | $16,700.35 | $198.88 |
| taker | 2d | regime_trend | $1,266.27 | 533% | 20.9% | 56.9% | 26 | $309.63 | -32.8% | 60.8% | $219.92 | 25.2% | $16,700.35 | $198.88 |
| taker | 3d | breakout | $2,715.21 | 1258% | 30.8% | 42.7% | 32 | $912.94 | -16.3% | 57.6% | $147.49 | 40.2% | $16,393.92 | $198.88 |
| taker | 3d | ema_trend | $2,116.02 | 958% | 27.5% | 45.5% | 43 | $697.30 | -16.4% | 57.6% | $188.26 | 25.6% | $16,393.92 | $198.88 |
| taker | 3d | regime_trend | $552.91 | 176% | 11.0% | 49.7% | 21 | $52.44 | -26.0% | 31.4% | $201.57 | 5.5% | $16,393.92 | $198.88 |

## Candidate deep-dives (validation passers / PASS / MARGINAL)

### pullback 1d [taker] `{"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}` -> FAIL

Reasons: OOS expectancy <= 0; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 4 | 75% | 39.84 | $1,042 | 10.4% | 1324.2% |
| 2018 | 1 | 0% | 0.00 | $-93 | -0.8% | -73.4% |
| 2019 | 4 | 50% | 2.91 | $477 | 4.4% | 94.1% |
| 2020 | 6 | 33% | 1.74 | $412 | 9.1% | 304.6% |
| 2021 | 8 | 50% | 1.84 | $447 | -1.5% | 59.4% |
| 2022 | 0 | n/a | n/a | $0 | 0.0% | -64.2% |
| 2023 | 3 | 0% | 0.00 | $-341 | 9.4% | 155.8% |
| 2024 | 6 | 50% | 6.14 | $2,622 | 8.4% | 120.8% |
| 2025 | 7 | 14% | 0.14 | $-862 | -5.9% | -6.3% |
| 2026 | 1 | 100% | inf | $31 | 0.2% | -4.6% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BEAR | 1 | 100% | inf | 7.53% | $1,020 |
| BULL | 33 | 33% | 1.29 | 0.31% | $872 |
| SIDEWAYS | 6 | 67% | 7.51 | 2.67% | $1,841 |
| HIGH_VOL | 16 | 50% | 2.10 | 0.61% | $1,036 |
| LOW_VOL | 15 | 27% | 1.98 | 0.98% | $1,682 |
| MID_VOL | 8 | 38% | 2.28 | 0.93% | $836 |
| UNKNOWN | 1 | 100% | inf | 1.81% | $181 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 1.58, 28 trades, expectancy 0.48%, return 13.1%, max DD 8.9%

- 2017-01-01..2020-01-01 -> 2020-01-01..2020-07-01: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2017-07-02..2020-07-01 -> 2020-07-01..2020-12-30: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2017-12-31..2020-12-30 -> 2020-12-30..2021-06-30: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2018-07-01..2021-06-30 -> 2021-06-30..2021-12-29: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2018-12-30..2021-12-29 -> 2021-12-29..2022-06-29: {"pb_ema": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2019-06-30..2022-06-29 -> 2022-06-29..2022-12-28: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2019-12-29..2022-12-28 -> 2022-12-28..2023-06-28: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2020-06-28..2023-06-28 -> 2023-06-28..2023-12-27: {"pb_ema": 50, "stop_atr": 3.0, "trail_atr": 3.0}
- 2020-12-27..2023-12-27 -> 2023-12-27..2024-06-26: {"pb_ema": 50, "stop_atr": 3.0, "trail_atr": 3.0}
- 2021-06-27..2024-06-26 -> 2024-06-26..2024-12-25: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2021-12-26..2024-12-25 -> 2024-12-25..2025-06-25: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2022-06-26..2025-06-25 -> 2025-06-25..2025-12-24: {"pb_ema": 50, "stop_atr": 2.0, "trail_atr": 3.0}
- 2022-12-25..2025-12-24 -> 2025-12-24..2026-06-24: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2023-06-25..2026-06-24 -> 2026-06-24..2026-09-28: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 5.0}

### regime_trend 1d [taker] `{"sma_n": 100, "stop_atr": 5.0, "vol_pct": 100}` -> FAIL

Reasons: OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 0 | n/a | n/a | $0 | 12.5% | 1324.2% |
| 2018 | 9 | 11% | 4.72 | $714 | -4.8% | -73.4% |
| 2019 | 4 | 25% | 11.56 | $780 | 7.3% | 94.1% |
| 2020 | 7 | 14% | 0.47 | $-72 | 10.3% | 304.6% |
| 2021 | 7 | 43% | 19.78 | $2,593 | 10.6% | 59.4% |
| 2022 | 4 | 0% | 0.00 | $-201 | -1.4% | -64.2% |
| 2023 | 6 | 33% | 1.77 | $145 | 4.7% | 155.8% |
| 2024 | 9 | 11% | 4.29 | $819 | 5.1% | 120.8% |
| 2025 | 11 | 18% | 1.86 | $264 | -1.0% | -6.3% |
| 2026 | 3 | 33% | 2.36 | $138 | 0.9% | -4.6% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BEAR | 18 | 22% | 2.91 | 0.50% | $1,042 |
| BULL | 32 | 9% | 4.36 | 0.79% | $2,929 |
| SIDEWAYS | 9 | 44% | 2.76 | 0.22% | $303 |
| UNKNOWN | 1 | 100% | inf | 9.06% | $906 |
| HIGH_VOL | 8 | 12% | 0.84 | -0.03% | $-25 |
| LOW_VOL | 25 | 20% | 7.67 | 1.51% | $4,463 |
| MID_VOL | 26 | 19% | 0.79 | -0.06% | $-164 |
| UNKNOWN | 1 | 100% | inf | 9.06% | $906 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 3.04, 39 trades, expectancy 0.63%, return 26.0%, max DD 6.6%

- 2017-01-01..2020-01-01 -> 2020-01-01..2020-07-01: {"sma_n": 100, "stop_atr": 3.0, "vol_pct": 80}
- 2017-07-02..2020-07-01 -> 2020-07-01..2020-12-30: {"sma_n": 100, "stop_atr": 3.0, "vol_pct": 80}
- 2017-12-31..2020-12-30 -> 2020-12-30..2021-06-30: {"sma_n": 100, "stop_atr": 3.0, "vol_pct": 50}
- 2018-07-01..2021-06-30 -> 2021-06-30..2021-12-29: {"sma_n": 100, "stop_atr": 3.0, "vol_pct": 50}
- 2018-12-30..2021-12-29 -> 2021-12-29..2022-06-29: {"sma_n": 100, "stop_atr": 5.0, "vol_pct": 50}
- 2019-06-30..2022-06-29 -> 2022-06-29..2022-12-28: {"sma_n": 100, "stop_atr": 3.0, "vol_pct": 80}
- 2019-12-29..2022-12-28 -> 2022-12-28..2023-06-28: {"sma_n": 100, "stop_atr": 3.0, "vol_pct": 50}
- 2020-06-28..2023-06-28 -> 2023-06-28..2023-12-27: {"sma_n": 200, "stop_atr": 3.0, "vol_pct": 50}
- 2020-12-27..2023-12-27 -> 2023-12-27..2024-06-26: {"sma_n": 200, "stop_atr": 3.0, "vol_pct": 80}
- 2021-06-27..2024-06-26 -> 2024-06-26..2024-12-25: {"sma_n": 200, "stop_atr": 5.0, "vol_pct": 80}
- 2021-12-26..2024-12-25 -> 2024-12-25..2025-06-25: {"sma_n": 200, "stop_atr": 5.0, "vol_pct": 80}
- 2022-06-26..2025-06-25 -> 2025-06-25..2025-12-24: {"sma_n": 200, "stop_atr": 5.0, "vol_pct": 80}
- 2022-12-25..2025-12-24 -> 2025-12-24..2026-06-24: {"sma_n": 200, "stop_atr": 5.0, "vol_pct": 80}
- 2023-06-25..2026-06-24 -> 2026-06-24..2026-09-28: {"sma_n": 200, "stop_atr": 5.0, "vol_pct": 50}

### hybrid 1d [taker] `{"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}` -> FAIL

Reasons: < 5 OOS trades; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit; unprofitable without its best few trades

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 3 | 100% | inf | $492 | 4.9% | 1324.2% |
| 2018 | 3 | 0% | 0.00 | $-287 | -2.7% | -73.4% |
| 2019 | 3 | 33% | 3.28 | $486 | 4.8% | 94.1% |
| 2020 | 3 | 33% | 0.00 | $-243 | 10.8% | 304.6% |
| 2021 | 4 | 50% | 10.36 | $2,722 | 10.5% | 59.4% |
| 2022 | 1 | 0% | 0.00 | $-146 | -0.5% | -64.2% |
| 2023 | 3 | 33% | 0.85 | $-25 | 8.1% | 155.8% |
| 2024 | 4 | 25% | 5.66 | $1,772 | 8.0% | 120.8% |
| 2025 | 5 | 40% | 1.46 | $176 | -1.7% | -6.3% |
| 2026 | 1 | 100% | inf | $22 | 0.1% | -4.6% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BULL | 21 | 29% | 2.05 | 0.97% | $1,827 |
| SIDEWAYS | 9 | 67% | 9.61 | 2.78% | $3,143 |
| HIGH_VOL | 11 | 55% | 3.06 | 0.72% | $948 |
| LOW_VOL | 4 | 25% | 6.28 | 3.48% | $1,809 |
| MID_VOL | 14 | 29% | 2.60 | 1.59% | $2,088 |
| UNKNOWN | 1 | 100% | inf | 1.25% | $125 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 1.82, 33 trades, expectancy 0.62%, return 20.9%, max DD 8.9%

- 2017-01-01..2020-01-01 -> 2020-01-01..2020-07-01: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2017-07-02..2020-07-01 -> 2020-07-01..2020-12-30: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2017-12-31..2020-12-30 -> 2020-12-30..2021-06-30: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2018-07-01..2021-06-30 -> 2021-06-30..2021-12-29: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2018-12-30..2021-12-29 -> 2021-12-29..2022-06-29: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2019-06-30..2022-06-29 -> 2022-06-29..2022-12-28: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2019-12-29..2022-12-28 -> 2022-12-28..2023-06-28: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2020-06-28..2023-06-28 -> 2023-06-28..2023-12-27: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2020-12-27..2023-12-27 -> 2023-12-27..2024-06-26: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2021-06-27..2024-06-26 -> 2024-06-26..2024-12-25: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2021-12-26..2024-12-25 -> 2024-12-25..2025-06-25: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2022-06-26..2025-06-25 -> 2025-06-25..2025-12-24: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2022-12-25..2025-12-24 -> 2025-12-24..2026-06-24: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2023-06-25..2026-06-24 -> 2026-06-24..2026-09-28: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}

### breakout 1d [maker] `{"n": 10, "stop_atr": 2.0, "trend_filter": "sma200"}` -> FAIL

Reasons: OOS expectancy <= 0; OOS PF < 1.25; max DD at 15% risk ($200) > 50%

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 5 | 80% | 12.30 | $1,225 | 12.3% | 1324.2% |
| 2018 | 3 | 33% | 0.05 | $-227 | -2.0% | -73.4% |
| 2019 | 5 | 60% | 6.54 | $657 | 6.0% | 94.1% |
| 2020 | 9 | 22% | 2.01 | $716 | 12.0% | 304.6% |
| 2021 | 9 | 44% | 1.93 | $654 | -0.2% | 59.4% |
| 2022 | 0 | n/a | n/a | $0 | 0.0% | -64.2% |
| 2023 | 8 | 62% | 2.96 | $973 | 7.5% | 155.8% |
| 2024 | 10 | 40% | 1.79 | $807 | 5.8% | 120.8% |
| 2025 | 11 | 18% | 0.24 | $-1,017 | -6.9% | -6.3% |
| 2026 | 2 | 50% | 2.33 | $161 | 1.2% | -4.6% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BULL | 51 | 35% | 1.32 | 0.30% | $1,445 |
| SIDEWAYS | 11 | 73% | 10.36 | 1.79% | $2,503 |
| HIGH_VOL | 18 | 50% | 2.57 | 0.83% | $1,787 |
| LOW_VOL | 21 | 33% | 1.70 | 0.68% | $1,523 |
| MID_VOL | 22 | 45% | 1.53 | 0.32% | $746 |
| UNKNOWN | 1 | 0% | 0.00 | -1.08% | $-108 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 1.65, 45 trades, expectancy 0.41%, return 19.0%, max DD 11.5%

- 2017-01-01..2020-01-01 -> 2020-01-01..2020-07-01: {"n": 10, "stop_atr": 3.0, "trend_filter": "sma200"}
- 2017-07-02..2020-07-01 -> 2020-07-01..2020-12-30: {"n": 10, "stop_atr": 3.0, "trend_filter": "sma200"}
- 2017-12-31..2020-12-30 -> 2020-12-30..2021-06-30: {"n": 30, "stop_atr": 2.0, "trend_filter": "none"}
- 2018-07-01..2021-06-30 -> 2021-06-30..2021-12-29: {"n": 10, "stop_atr": 2.0, "trend_filter": "sma200"}
- 2018-12-30..2021-12-29 -> 2021-12-29..2022-06-29: {"n": 10, "stop_atr": 2.0, "trend_filter": "none"}
- 2019-06-30..2022-06-29 -> 2022-06-29..2022-12-28: {"n": 30, "stop_atr": 2.0, "trend_filter": "none"}
- 2019-12-29..2022-12-28 -> 2022-12-28..2023-06-28: {"n": 20, "stop_atr": 2.0, "trend_filter": "sma200"}
- 2020-06-28..2023-06-28 -> 2023-06-28..2023-12-27: {"n": 10, "stop_atr": 2.0, "trend_filter": "sma200"}
- 2020-12-27..2023-12-27 -> 2023-12-27..2024-06-26: {"n": 20, "stop_atr": 2.0, "trend_filter": "sma200"}
- 2021-06-27..2024-06-26 -> 2024-06-26..2024-12-25: {"n": 20, "stop_atr": 2.0, "trend_filter": "sma200"}
- 2021-12-26..2024-12-25 -> 2024-12-25..2025-06-25: {"n": 30, "stop_atr": 3.0, "trend_filter": "sma200"}
- 2022-06-26..2025-06-25 -> 2025-06-25..2025-12-24: {"n": 50, "stop_atr": 3.0, "trend_filter": "none"}
- 2022-12-25..2025-12-24 -> 2025-12-24..2026-06-24: {"n": 50, "stop_atr": 2.0, "trend_filter": "none"}
- 2023-06-25..2026-06-24 -> 2026-06-24..2026-09-28: {"n": 30, "stop_atr": 3.0, "trend_filter": "sma200"}

### pullback 1d [maker] `{"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}` -> FAIL

Reasons: OOS expectancy <= 0; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 4 | 75% | 46.06 | $1,054 | 10.5% | 1324.2% |
| 2018 | 1 | 0% | 0.00 | $-91 | -0.8% | -73.4% |
| 2019 | 4 | 50% | 2.86 | $482 | 4.4% | 94.1% |
| 2020 | 6 | 33% | 1.84 | $449 | 9.5% | 304.6% |
| 2021 | 8 | 50% | 1.93 | $483 | -1.2% | 59.4% |
| 2022 | 0 | n/a | n/a | $0 | 0.0% | -64.2% |
| 2023 | 3 | 0% | 0.00 | $-320 | 9.7% | 155.8% |
| 2024 | 6 | 50% | 6.41 | $2,659 | 8.4% | 120.8% |
| 2025 | 7 | 14% | 0.16 | $-799 | -5.4% | -6.3% |
| 2026 | 1 | 0% | 0.00 | $-119 | -0.9% | -4.6% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BEAR | 1 | 100% | inf | 7.60% | $1,039 |
| BULL | 33 | 30% | 1.28 | 0.31% | $864 |
| SIDEWAYS | 6 | 67% | 7.93 | 2.72% | $1,894 |
| HIGH_VOL | 15 | 47% | 2.14 | 0.66% | $1,054 |
| LOW_VOL | 15 | 27% | 2.12 | 1.05% | $1,834 |
| MID_VOL | 9 | 33% | 1.97 | 0.73% | $726 |
| UNKNOWN | 1 | 100% | inf | 1.83% | $183 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 1.68, 27 trades, expectancy 0.55%, return 14.6%, max DD 8.3%

- 2017-01-01..2020-01-01 -> 2020-01-01..2020-07-01: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2017-07-02..2020-07-01 -> 2020-07-01..2020-12-30: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2017-12-31..2020-12-30 -> 2020-12-30..2021-06-30: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2018-07-01..2021-06-30 -> 2021-06-30..2021-12-29: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2018-12-30..2021-12-29 -> 2021-12-29..2022-06-29: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2019-06-30..2022-06-29 -> 2022-06-29..2022-12-28: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2019-12-29..2022-12-28 -> 2022-12-28..2023-06-28: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2020-06-28..2023-06-28 -> 2023-06-28..2023-12-27: {"pb_ema": 50, "stop_atr": 3.0, "trail_atr": 3.0}
- 2020-12-27..2023-12-27 -> 2023-12-27..2024-06-26: {"pb_ema": 50, "stop_atr": 3.0, "trail_atr": 3.0}
- 2021-06-27..2024-06-26 -> 2024-06-26..2024-12-25: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2021-12-26..2024-12-25 -> 2024-12-25..2025-06-25: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2022-06-26..2025-06-25 -> 2025-06-25..2025-12-24: {"pb_ema": 50, "stop_atr": 2.0, "trail_atr": 3.0}
- 2022-12-25..2025-12-24 -> 2025-12-24..2026-06-24: {"pb_ema": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2023-06-25..2026-06-24 -> 2026-06-24..2026-09-28: {"pb_ema": 50, "stop_atr": 2.0, "trail_atr": 3.0}

### regime_trend 1d [maker] `{"sma_n": 200, "stop_atr": 5.0, "vol_pct": 50}` -> FAIL

Reasons: < 5 OOS trades; < 30 full-history trades; max DD at 15% risk ($200) > 50%

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 0 | n/a | n/a | $0 | 6.9% | 1324.2% |
| 2018 | 2 | 50% | 2.78 | $115 | -5.4% | -73.4% |
| 2019 | 2 | 50% | 13.18 | $392 | 3.9% | 94.1% |
| 2020 | 2 | 0% | 0.00 | $-89 | 8.5% | 304.6% |
| 2021 | 8 | 12% | 8.28 | $1,191 | 1.8% | 59.4% |
| 2022 | 0 | n/a | n/a | $0 | 0.0% | -64.2% |
| 2023 | 2 | 50% | 15.15 | $310 | 6.4% | 155.8% |
| 2024 | 4 | 25% | 7.25 | $763 | 5.3% | 120.8% |
| 2025 | 3 | 67% | 9.23 | $227 | -0.7% | -6.3% |
| 2026 | 1 | 100% | inf | $211 | 1.6% | -4.6% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BULL | 14 | 21% | 3.20 | 0.49% | $793 |
| SIDEWAYS | 10 | 50% | 15.43 | 2.15% | $2,325 |
| HIGH_VOL | 4 | 50% | 2.91 | 0.41% | $176 |
| LOW_VOL | 5 | 60% | 28.11 | 2.24% | $1,332 |
| MID_VOL | 15 | 20% | 5.24 | 1.03% | $1,610 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 2.73, 39 trades, expectancy 0.41%, return 16.7%, max DD 4.9%

- 2017-01-01..2020-01-01 -> 2020-01-01..2020-07-01: {"sma_n": 100, "stop_atr": 5.0, "vol_pct": 80}
- 2017-07-02..2020-07-01 -> 2020-07-01..2020-12-30: {"sma_n": 100, "stop_atr": 5.0, "vol_pct": 80}
- 2017-12-31..2020-12-30 -> 2020-12-30..2021-06-30: {"sma_n": 100, "stop_atr": 3.0, "vol_pct": 50}
- 2018-07-01..2021-06-30 -> 2021-06-30..2021-12-29: {"sma_n": 100, "stop_atr": 3.0, "vol_pct": 50}
- 2018-12-30..2021-12-29 -> 2021-12-29..2022-06-29: {"sma_n": 100, "stop_atr": 5.0, "vol_pct": 50}
- 2019-06-30..2022-06-29 -> 2022-06-29..2022-12-28: {"sma_n": 100, "stop_atr": 5.0, "vol_pct": 80}
- 2019-12-29..2022-12-28 -> 2022-12-28..2023-06-28: {"sma_n": 100, "stop_atr": 5.0, "vol_pct": 50}
- 2020-06-28..2023-06-28 -> 2023-06-28..2023-12-27: {"sma_n": 200, "stop_atr": 5.0, "vol_pct": 50}
- 2020-12-27..2023-12-27 -> 2023-12-27..2024-06-26: {"sma_n": 200, "stop_atr": 5.0, "vol_pct": 80}
- 2021-06-27..2024-06-26 -> 2024-06-26..2024-12-25: {"sma_n": 200, "stop_atr": 5.0, "vol_pct": 80}
- 2021-12-26..2024-12-25 -> 2024-12-25..2025-06-25: {"sma_n": 100, "stop_atr": 3.0, "vol_pct": 100}
- 2022-06-26..2025-06-25 -> 2025-06-25..2025-12-24: {"sma_n": 200, "stop_atr": 5.0, "vol_pct": 80}
- 2022-12-25..2025-12-24 -> 2025-12-24..2026-06-24: {"sma_n": 200, "stop_atr": 5.0, "vol_pct": 80}
- 2023-06-25..2026-06-24 -> 2026-06-24..2026-09-28: {"sma_n": 200, "stop_atr": 5.0, "vol_pct": 50}

### hybrid 1d [maker] `{"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}` -> FAIL

Reasons: < 5 OOS trades; OOS expectancy <= 0; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit; unprofitable without its best few trades

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 3 | 100% | inf | $498 | 5.0% | 1324.2% |
| 2018 | 3 | 0% | 0.00 | $-283 | -2.7% | -73.4% |
| 2019 | 3 | 33% | 3.46 | $514 | 5.0% | 94.1% |
| 2020 | 3 | 33% | 0.01 | $-234 | 11.0% | 304.6% |
| 2021 | 4 | 50% | 10.63 | $2,747 | 10.6% | 59.4% |
| 2022 | 1 | 0% | 0.00 | $-143 | -0.5% | -64.2% |
| 2023 | 3 | 67% | 0.95 | $-8 | 8.3% | 155.8% |
| 2024 | 4 | 25% | 5.93 | $1,808 | 8.1% | 120.8% |
| 2025 | 5 | 40% | 1.55 | $204 | -1.6% | -6.3% |
| 2026 | 1 | 0% | 0.00 | $-86 | -0.6% | -4.6% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BULL | 21 | 29% | 2.01 | 0.96% | $1,800 |
| SIDEWAYS | 9 | 67% | 10.04 | 2.83% | $3,216 |
| HIGH_VOL | 10 | 50% | 3.16 | 0.81% | $975 |
| LOW_VOL | 4 | 25% | 6.68 | 3.54% | $1,849 |
| MID_VOL | 15 | 33% | 2.52 | 1.48% | $2,066 |
| UNKNOWN | 1 | 100% | inf | 1.27% | $127 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 1.84, 33 trades, expectancy 0.64%, return 21.4%, max DD 8.7%

- 2017-01-01..2020-01-01 -> 2020-01-01..2020-07-01: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2017-07-02..2020-07-01 -> 2020-07-01..2020-12-30: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2017-12-31..2020-12-30 -> 2020-12-30..2021-06-30: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2018-07-01..2021-06-30 -> 2021-06-30..2021-12-29: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2018-12-30..2021-12-29 -> 2021-12-29..2022-06-29: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2019-06-30..2022-06-29 -> 2022-06-29..2022-12-28: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2019-12-29..2022-12-28 -> 2022-12-28..2023-06-28: {"n": 20, "stop_atr": 3.0, "trail_atr": 5.0}
- 2020-06-28..2023-06-28 -> 2023-06-28..2023-12-27: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2020-12-27..2023-12-27 -> 2023-12-27..2024-06-26: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2021-06-27..2024-06-26 -> 2024-06-26..2024-12-25: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2021-12-26..2024-12-25 -> 2024-12-25..2025-06-25: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2022-06-26..2025-06-25 -> 2025-06-25..2025-12-24: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2022-12-25..2025-12-24 -> 2025-12-24..2026-06-24: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2023-06-25..2026-06-24 -> 2026-06-24..2026-09-28: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}

### ema_trend 2d [taker] `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` -> FAIL

Reasons: OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 2 | 50% | 1.65 | $14 | 7.6% | 1296.1% |
| 2018 | 1 | 100% | inf | $732 | -0.1% | -72.4% |
| 2019 | 7 | 14% | 6.96 | $677 | 6.3% | 87.3% |
| 2020 | 5 | 20% | 0.61 | $-48 | 11.8% | 304.6% |
| 2021 | 7 | 29% | 15.44 | $3,013 | 12.7% | 64.7% |
| 2022 | 0 | n/a | n/a | $0 | 0.0% | -65.4% |
| 2023 | 6 | 33% | 0.97 | $-6 | 4.2% | 167.5% |
| 2024 | 8 | 50% | 4.94 | $1,154 | 3.7% | 113.4% |
| 2025 | 9 | 22% | 0.35 | $-207 | -1.3% | -7.3% |
| 2026 | 3 | 33% | 0.40 | $-95 | -0.6% | -3.5% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BEAR | 4 | 25% | 2.21 | 0.41% | $243 |
| BULL | 34 | 26% | 5.57 | 1.08% | $4,170 |
| SIDEWAYS | 10 | 50% | 3.66 | 0.76% | $820 |
| HIGH_VOL | 8 | 38% | 11.81 | 1.22% | $1,120 |
| LOW_VOL | 18 | 28% | 6.61 | 1.69% | $3,546 |
| MID_VOL | 21 | 29% | 1.78 | 0.25% | $532 |
| UNKNOWN | 1 | 100% | inf | 0.35% | $35 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 2.67, 38 trades, expectancy 0.67%, return 26.6%, max DD 6.4%

- 2017-01-02..2020-01-02 -> 2020-01-02..2020-07-02: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2017-07-03..2020-07-02 -> 2020-07-02..2020-12-31: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2018-01-01..2020-12-31 -> 2020-12-31..2021-07-01: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2018-07-02..2021-07-01 -> 2021-07-01..2021-12-30: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2018-12-31..2021-12-30 -> 2021-12-30..2022-06-30: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2019-07-01..2022-06-30 -> 2022-06-30..2022-12-29: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2019-12-30..2022-12-29 -> 2022-12-29..2023-06-29: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2020-06-29..2023-06-29 -> 2023-06-29..2023-12-28: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2020-12-28..2023-12-28 -> 2023-12-28..2024-06-27: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2021-06-28..2024-06-27 -> 2024-06-27..2024-12-26: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2021-12-27..2024-12-26 -> 2024-12-26..2025-06-26: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2022-06-27..2025-06-26 -> 2025-06-26..2025-12-25: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2022-12-26..2025-12-25 -> 2025-12-25..2026-06-25: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2023-06-26..2026-06-25 -> 2026-06-25..2026-09-26: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}

### hybrid 2d [taker] `{"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}` -> FAIL

Reasons: < 5 OOS trades; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit; PF without best year <= 1; unprofitable without its best few trades; walk-forward PF 1.32 < 1.5

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 0 | n/a | n/a | $0 | 0.0% | 1296.1% |
| 2018 | 4 | 0% | 0.00 | $-230 | -2.3% | -72.4% |
| 2019 | 3 | 33% | 0.55 | $-59 | -0.6% | 87.3% |
| 2020 | 3 | 67% | 0.90 | $-11 | 9.8% | 304.6% |
| 2021 | 6 | 50% | 6.84 | $1,008 | 0.1% | 64.7% |
| 2022 | 3 | 0% | 0.00 | $-271 | -2.2% | -65.4% |
| 2023 | 1 | 0% | 0.00 | $-31 | 4.8% | 167.5% |
| 2024 | 5 | 40% | 2.75 | $415 | 1.4% | 113.4% |
| 2025 | 5 | 40% | 1.45 | $114 | -1.4% | -7.3% |
| 2026 | 0 | n/a | n/a | $0 | 0.0% | -3.5% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BEAR | 3 | 33% | 0.56 | -0.14% | $-44 |
| BULL | 19 | 32% | 2.04 | 0.53% | $956 |
| SIDEWAYS | 8 | 38% | 1.06 | 0.01% | $23 |
| HIGH_VOL | 12 | 42% | 1.90 | 0.27% | $351 |
| LOW_VOL | 5 | 0% | 0.00 | -0.63% | $-315 |
| MID_VOL | 13 | 38% | 2.24 | 0.74% | $898 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 1.32, 25 trades, expectancy 0.17%, return 4.0%, max DD 5.8%

- 2017-01-02..2020-01-02 -> 2020-01-02..2020-07-02: none eligible
- 2017-07-03..2020-07-02 -> 2020-07-02..2020-12-31: none eligible
- 2018-01-01..2020-12-31 -> 2020-12-31..2021-07-01: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2018-07-02..2021-07-01 -> 2021-07-01..2021-12-30: {"n": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2018-12-31..2021-12-30 -> 2021-12-30..2022-06-30: {"n": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2019-07-01..2022-06-30 -> 2022-06-30..2022-12-29: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2019-12-30..2022-12-29 -> 2022-12-29..2023-06-29: {"n": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2020-06-29..2023-06-29 -> 2023-06-29..2023-12-28: {"n": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2020-12-28..2023-12-28 -> 2023-12-28..2024-06-27: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2021-06-28..2024-06-27 -> 2024-06-27..2024-12-26: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2021-12-27..2024-12-26 -> 2024-12-26..2025-06-26: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2022-06-27..2025-06-26 -> 2025-06-26..2025-12-25: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2022-12-26..2025-12-25 -> 2025-12-25..2026-06-25: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2023-06-26..2026-06-25 -> 2026-06-25..2026-09-26: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}

### ema_trend 2d [maker] `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` -> FAIL

Reasons: OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 2 | 50% | 2.01 | $19 | 7.7% | 1296.1% |
| 2018 | 1 | 100% | inf | $738 | -0.1% | -72.4% |
| 2019 | 7 | 14% | 7.24 | $690 | 6.4% | 87.3% |
| 2020 | 5 | 20% | 0.82 | $-19 | 12.1% | 304.6% |
| 2021 | 7 | 29% | 17.54 | $3,078 | 13.1% | 64.7% |
| 2022 | 0 | n/a | n/a | $0 | 0.0% | -65.4% |
| 2023 | 6 | 33% | 1.34 | $49 | 4.6% | 167.5% |
| 2024 | 8 | 50% | 4.63 | $1,181 | 3.7% | 113.4% |
| 2025 | 8 | 25% | 0.62 | $-84 | -0.5% | -7.3% |
| 2026 | 3 | 33% | 0.51 | $-70 | -0.4% | -3.5% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BEAR | 4 | 25% | 2.62 | 0.47% | $284 |
| BULL | 33 | 27% | 6.53 | 1.16% | $4,411 |
| SIDEWAYS | 10 | 50% | 4.19 | 0.81% | $886 |
| HIGH_VOL | 8 | 38% | 12.15 | 1.25% | $1,150 |
| LOW_VOL | 17 | 29% | 8.88 | 1.88% | $3,789 |
| MID_VOL | 21 | 29% | 1.91 | 0.28% | $605 |
| UNKNOWN | 1 | 100% | inf | 0.37% | $37 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 3.52, 37 trades, expectancy 0.79%, return 31.6%, max DD 5.1%

- 2017-01-02..2020-01-02 -> 2020-01-02..2020-07-02: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2017-07-03..2020-07-02 -> 2020-07-02..2020-12-31: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2018-01-01..2020-12-31 -> 2020-12-31..2021-07-01: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2018-07-02..2021-07-01 -> 2021-07-01..2021-12-30: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2018-12-31..2021-12-30 -> 2021-12-30..2022-06-30: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2019-07-01..2022-06-30 -> 2022-06-30..2022-12-29: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2019-12-30..2022-12-29 -> 2022-12-29..2023-06-29: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2020-06-29..2023-06-29 -> 2023-06-29..2023-12-28: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2020-12-28..2023-12-28 -> 2023-12-28..2024-06-27: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2021-06-28..2024-06-27 -> 2024-06-27..2024-12-26: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2021-12-27..2024-12-26 -> 2024-12-26..2025-06-26: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2022-06-27..2025-06-26 -> 2025-06-26..2025-12-25: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2022-12-26..2025-12-25 -> 2025-12-25..2026-06-25: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2023-06-26..2026-06-25 -> 2026-06-25..2026-09-26: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}

### hybrid 2d [maker] `{"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}` -> FAIL

Reasons: < 5 OOS trades; OOS PF < 1.25; max DD at 15% risk ($200) > 50%; best year > 50% of net profit; PF without best year <= 1; unprofitable without its best few trades; walk-forward PF 1.39 < 1.5

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 0 | n/a | n/a | $0 | 0.0% | 1296.1% |
| 2018 | 4 | 0% | 0.00 | $-225 | -2.2% | -72.4% |
| 2019 | 3 | 33% | 0.57 | $-54 | -0.5% | 87.3% |
| 2020 | 3 | 67% | 0.96 | $-5 | 9.9% | 304.6% |
| 2021 | 6 | 50% | 7.08 | $1,020 | 0.2% | 64.7% |
| 2022 | 3 | 0% | 0.00 | $-266 | -2.2% | -65.4% |
| 2023 | 1 | 0% | 0.00 | $-28 | 4.9% | 167.5% |
| 2024 | 5 | 40% | 2.86 | $430 | 1.5% | 113.4% |
| 2025 | 5 | 40% | 1.54 | $130 | -1.3% | -7.3% |
| 2026 | 0 | n/a | n/a | $0 | 0.0% | -3.5% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BEAR | 3 | 33% | 0.61 | -0.11% | $-38 |
| BULL | 19 | 32% | 2.13 | 0.55% | $1,001 |
| SIDEWAYS | 8 | 38% | 1.10 | 0.03% | $40 |
| HIGH_VOL | 12 | 42% | 1.99 | 0.29% | $376 |
| LOW_VOL | 5 | 0% | 0.00 | -0.60% | $-301 |
| MID_VOL | 13 | 38% | 2.31 | 0.76% | $928 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 1.39, 25 trades, expectancy 0.20%, return 4.7%, max DD 5.5%

- 2017-01-02..2020-01-02 -> 2020-01-02..2020-07-02: none eligible
- 2017-07-03..2020-07-02 -> 2020-07-02..2020-12-31: none eligible
- 2018-01-01..2020-12-31 -> 2020-12-31..2021-07-01: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2018-07-02..2021-07-01 -> 2021-07-01..2021-12-30: {"n": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2018-12-31..2021-12-30 -> 2021-12-30..2022-06-30: {"n": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2019-07-01..2022-06-30 -> 2022-06-30..2022-12-29: {"n": 20, "stop_atr": 2.0, "trail_atr": 5.0}
- 2019-12-30..2022-12-29 -> 2022-12-29..2023-06-29: {"n": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2020-06-29..2023-06-29 -> 2023-06-29..2023-12-28: {"n": 20, "stop_atr": 2.0, "trail_atr": 3.0}
- 2020-12-28..2023-12-28 -> 2023-12-28..2024-06-27: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2021-06-28..2024-06-27 -> 2024-06-27..2024-12-26: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2021-12-27..2024-12-26 -> 2024-12-26..2025-06-26: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2022-06-27..2025-06-26 -> 2025-06-26..2025-12-25: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2022-12-26..2025-12-25 -> 2025-12-25..2026-06-25: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}
- 2023-06-26..2026-06-25 -> 2026-06-25..2026-09-26: {"n": 20, "stop_atr": 3.0, "trail_atr": 3.0}

### ema_trend 3d [taker] `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` -> FAIL

Reasons: OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 2 | 50% | 0.65 | $-19 | 6.3% | 1270.5% |
| 2018 | 3 | 33% | 12.66 | $438 | -2.0% | -72.4% |
| 2019 | 6 | 17% | 5.43 | $417 | 4.0% | 81.5% |
| 2020 | 6 | 17% | 0.32 | $-108 | 9.3% | 364.0% |
| 2021 | 6 | 33% | 12.85 | $1,999 | 7.5% | 43.4% |
| 2022 | 0 | n/a | n/a | $0 | 0.0% | -64.1% |
| 2023 | 5 | 20% | 0.14 | $-228 | 2.0% | 170.7% |
| 2024 | 8 | 25% | 3.19 | $463 | 2.5% | 115.5% |
| 2025 | 6 | 50% | 2.53 | $234 | -0.8% | -9.7% |
| 2026 | 1 | 100% | inf | $29 | 0.2% | -3.5% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BEAR | 3 | 33% | 6.22 | 0.71% | $278 |
| BULL | 32 | 25% | 3.87 | 0.74% | $2,510 |
| SIDEWAYS | 7 | 57% | 4.03 | 0.67% | $492 |
| UNKNOWN | 1 | 0% | 0.00 | -0.54% | $-54 |
| HIGH_VOL | 11 | 36% | 5.53 | 0.57% | $685 |
| LOW_VOL | 15 | 33% | 6.07 | 1.47% | $2,406 |
| MID_VOL | 15 | 20% | 1.33 | 0.12% | $155 |
| UNKNOWN | 2 | 50% | 0.65 | -0.10% | $-19 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 2.29, 32 trades, expectancy 0.37%, return 11.9%, max DD 3.1%

- 2017-01-03..2020-01-03 -> 2020-01-03..2020-07-03: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2017-07-04..2020-07-03 -> 2020-07-03..2021-01-01: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2018-01-02..2021-01-01 -> 2021-01-01..2021-07-02: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2018-07-03..2021-07-02 -> 2021-07-02..2021-12-31: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2019-01-01..2021-12-31 -> 2021-12-31..2022-07-01: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2019-07-02..2022-07-01 -> 2022-07-01..2022-12-30: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2019-12-31..2022-12-30 -> 2022-12-30..2023-06-30: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2020-06-30..2023-06-30 -> 2023-06-30..2023-12-29: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2020-12-29..2023-12-29 -> 2023-12-29..2024-06-28: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2021-06-29..2024-06-28 -> 2024-06-28..2024-12-27: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2021-12-28..2024-12-27 -> 2024-12-27..2025-06-27: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2022-06-28..2025-06-27 -> 2025-06-27..2025-12-26: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2022-12-27..2025-12-26 -> 2025-12-26..2026-06-26: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2023-06-27..2026-06-26 -> 2026-06-26..2026-09-25: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}

### breakout 3d [taker] `{"n": 10, "stop_atr": 3.0, "trend_filter": "none"}` -> FAIL

Reasons: OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 3 | 67% | 1.37 | $39 | 7.2% | 1270.5% |
| 2018 | 3 | 33% | 8.15 | $420 | -2.4% | -72.4% |
| 2019 | 2 | 50% | 13.89 | $483 | 4.6% | 81.5% |
| 2020 | 2 | 100% | inf | $150 | 11.9% | 364.0% |
| 2021 | 3 | 100% | inf | $2,249 | 9.0% | 43.4% |
| 2022 | 3 | 0% | 0.00 | $-230 | -2.1% | -64.1% |
| 2023 | 4 | 25% | 0.96 | $-6 | 4.6% | 170.7% |
| 2024 | 4 | 50% | 3.38 | $418 | 1.2% | 115.5% |
| 2025 | 3 | 67% | 2.22 | $195 | -0.9% | -9.7% |
| 2026 | 5 | 20% | 0.22 | $-245 | -1.8% | -3.5% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BEAR | 11 | 36% | 1.52 | 0.31% | $275 |
| BULL | 12 | 33% | 5.46 | 1.90% | $2,450 |
| SIDEWAYS | 7 | 86% | 21.52 | 0.80% | $745 |
| UNKNOWN | 2 | 50% | 1.03 | 0.02% | $4 |
| HIGH_VOL | 6 | 33% | 2.19 | 0.61% | $335 |
| LOW_VOL | 11 | 55% | 8.28 | 2.58% | $3,194 |
| MID_VOL | 12 | 42% | 0.76 | -0.05% | $-94 |
| UNKNOWN | 3 | 67% | 1.37 | 0.13% | $39 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 2.25, 21 trades, expectancy 0.62%, return 13.1%, max DD 4.6%

- 2017-01-03..2020-01-03 -> 2020-01-03..2020-07-03: {"n": 10, "stop_atr": 3.0, "trend_filter": "none"}
- 2017-07-04..2020-07-03 -> 2020-07-03..2021-01-01: {"n": 10, "stop_atr": 3.0, "trend_filter": "none"}
- 2018-01-02..2021-01-01 -> 2021-01-01..2021-07-02: none eligible
- 2018-07-03..2021-07-02 -> 2021-07-02..2021-12-31: none eligible
- 2019-01-01..2021-12-31 -> 2021-12-31..2022-07-01: {"n": 10, "stop_atr": 2.0, "trend_filter": "sma200"}
- 2019-07-02..2022-07-01 -> 2022-07-01..2022-12-30: none eligible
- 2019-12-31..2022-12-30 -> 2022-12-30..2023-06-30: {"n": 10, "stop_atr": 3.0, "trend_filter": "none"}
- 2020-06-30..2023-06-30 -> 2023-06-30..2023-12-29: {"n": 10, "stop_atr": 2.0, "trend_filter": "none"}
- 2020-12-29..2023-12-29 -> 2023-12-29..2024-06-28: {"n": 10, "stop_atr": 3.0, "trend_filter": "none"}
- 2021-06-29..2024-06-28 -> 2024-06-28..2024-12-27: {"n": 10, "stop_atr": 2.0, "trend_filter": "none"}
- 2021-12-28..2024-12-27 -> 2024-12-27..2025-06-27: {"n": 10, "stop_atr": 2.0, "trend_filter": "none"}
- 2022-06-28..2025-06-27 -> 2025-06-27..2025-12-26: {"n": 10, "stop_atr": 3.0, "trend_filter": "none"}
- 2022-12-27..2025-12-26 -> 2025-12-26..2026-06-26: {"n": 10, "stop_atr": 2.0, "trend_filter": "none"}
- 2023-06-27..2026-06-26 -> 2026-06-26..2026-09-25: {"n": 10, "stop_atr": 2.0, "trend_filter": "sma200"}

### ema_trend 3d [maker] `{"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}` -> FAIL

Reasons: OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit; unprofitable without its best few trades

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 2 | 50% | 0.72 | $-15 | -0.1% | 1270.5% |
| 2018 | 2 | 0% | 0.00 | $-33 | -0.3% | -72.4% |
| 2019 | 6 | 17% | 6.48 | $419 | 4.2% | 81.5% |
| 2020 | 6 | 17% | 0.40 | $-81 | 9.5% | 364.0% |
| 2021 | 6 | 33% | 14.21 | $1,949 | 7.8% | 43.4% |
| 2022 | 0 | n/a | n/a | $0 | 0.0% | -64.1% |
| 2023 | 5 | 20% | 0.18 | $-192 | 2.3% | 170.7% |
| 2024 | 8 | 38% | 2.44 | $394 | 2.0% | 115.5% |
| 2025 | 6 | 50% | 3.17 | $268 | -0.5% | -9.7% |
| 2026 | 1 | 100% | inf | $32 | 0.3% | -3.5% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BEAR | 3 | 33% | 7.59 | 0.76% | $282 |
| BULL | 31 | 26% | 3.40 | 0.63% | $2,008 |
| SIDEWAYS | 7 | 57% | 4.54 | 0.71% | $504 |
| UNKNOWN | 1 | 0% | 0.00 | -0.52% | $-52 |
| HIGH_VOL | 10 | 40% | 2.90 | 0.18% | $239 |
| LOW_VOL | 15 | 33% | 6.99 | 1.52% | $2,403 |
| MID_VOL | 15 | 20% | 1.23 | 0.11% | $114 |
| UNKNOWN | 2 | 50% | 0.72 | -0.07% | $-15 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 2.05, 32 trades, expectancy 0.34%, return 10.9%, max DD 3.9%

- 2017-01-03..2020-01-03 -> 2020-01-03..2020-07-03: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2017-07-04..2020-07-03 -> 2020-07-03..2021-01-01: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2018-01-02..2021-01-01 -> 2021-01-01..2021-07-02: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2018-07-03..2021-07-02 -> 2021-07-02..2021-12-31: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2019-01-01..2021-12-31 -> 2021-12-31..2022-07-01: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2019-07-02..2022-07-01 -> 2022-07-01..2022-12-30: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2019-12-31..2022-12-30 -> 2022-12-30..2023-06-30: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}
- 2020-06-30..2023-06-30 -> 2023-06-30..2023-12-29: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2020-12-29..2023-12-29 -> 2023-12-29..2024-06-28: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2021-06-29..2024-06-28 -> 2024-06-28..2024-12-27: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2021-12-28..2024-12-27 -> 2024-12-27..2025-06-27: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2022-06-28..2025-06-27 -> 2025-06-27..2025-12-26: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2022-12-27..2025-12-26 -> 2025-12-26..2026-06-26: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 3.0}
- 2023-06-27..2026-06-26 -> 2026-06-26..2026-09-25: {"exit_rule": "price", "pair": [20, 50], "stop_atr": 2.0}

### breakout 3d [maker] `{"n": 10, "stop_atr": 3.0, "trend_filter": "none"}` -> FAIL

Reasons: OOS expectancy <= 0; OOS PF < 1.25; best year > 50% of net profit

**By year** (strategy at 1% risk vs BTC):

| Year | Trades | Win% | PF | Net $ | Strategy return | BTC return |
|---|---|---|---|---|---|---|
| 2017 | 3 | 67% | 1.43 | $45 | 7.3% | 1270.5% |
| 2018 | 3 | 33% | 9.04 | $431 | -2.3% | -72.4% |
| 2019 | 2 | 50% | 15.25 | $493 | 4.7% | 81.5% |
| 2020 | 2 | 100% | inf | $158 | 12.0% | 364.0% |
| 2021 | 3 | 100% | inf | $2,278 | 9.1% | 43.4% |
| 2022 | 3 | 0% | 0.00 | $-267 | -2.3% | -64.1% |
| 2023 | 4 | 25% | 1.15 | $18 | 4.8% | 170.7% |
| 2024 | 4 | 50% | 2.61 | $379 | 0.9% | 115.5% |
| 2025 | 3 | 67% | 2.38 | $213 | -0.7% | -9.7% |
| 2026 | 5 | 20% | 0.20 | $-320 | -2.3% | -3.5% |

**By regime** (entry-day regime, lagged daily labels):

| Regime | Trades | Win% | PF | Expectancy | Net $ |
|---|---|---|---|---|---|
| BEAR | 11 | 36% | 1.27 | 0.24% | $175 |
| BULL | 12 | 33% | 5.25 | 1.91% | $2,462 |
| SIDEWAYS | 7 | 86% | 23.92 | 0.85% | $785 |
| UNKNOWN | 2 | 50% | 1.07 | 0.04% | $7 |
| HIGH_VOL | 6 | 33% | 2.39 | 0.65% | $365 |
| LOW_VOL | 11 | 55% | 7.30 | 2.57% | $3,189 |
| MID_VOL | 12 | 42% | 0.66 | -0.09% | $-169 |
| UNKNOWN | 3 | 67% | 1.43 | 0.15% | $45 |

**Walk-forward folds** (params re-selected on each 3-year train window): combined PF 2.27, 21 trades, expectancy 0.63%, return 13.4%, max DD 4.7%

- 2017-01-03..2020-01-03 -> 2020-01-03..2020-07-03: {"n": 10, "stop_atr": 3.0, "trend_filter": "none"}
- 2017-07-04..2020-07-03 -> 2020-07-03..2021-01-01: {"n": 10, "stop_atr": 3.0, "trend_filter": "none"}
- 2018-01-02..2021-01-01 -> 2021-01-01..2021-07-02: none eligible
- 2018-07-03..2021-07-02 -> 2021-07-02..2021-12-31: none eligible
- 2019-01-01..2021-12-31 -> 2021-12-31..2022-07-01: {"n": 10, "stop_atr": 2.0, "trend_filter": "sma200"}
- 2019-07-02..2022-07-01 -> 2022-07-01..2022-12-30: none eligible
- 2019-12-31..2022-12-30 -> 2022-12-30..2023-06-30: {"n": 10, "stop_atr": 3.0, "trend_filter": "none"}
- 2020-06-30..2023-06-30 -> 2023-06-30..2023-12-29: {"n": 10, "stop_atr": 2.0, "trend_filter": "none"}
- 2020-12-29..2023-12-29 -> 2023-12-29..2024-06-28: {"n": 10, "stop_atr": 3.0, "trend_filter": "none"}
- 2021-06-29..2024-06-28 -> 2024-06-28..2024-12-27: {"n": 10, "stop_atr": 2.0, "trend_filter": "none"}
- 2021-12-28..2024-12-27 -> 2024-12-27..2025-06-27: {"n": 10, "stop_atr": 2.0, "trend_filter": "none"}
- 2022-06-28..2025-06-27 -> 2025-06-27..2025-12-26: {"n": 10, "stop_atr": 2.0, "trend_filter": "none"}
- 2022-12-27..2025-12-26 -> 2025-12-26..2026-06-26: {"n": 10, "stop_atr": 2.0, "trend_filter": "none"}
- 2023-06-27..2026-06-26 -> 2026-06-26..2026-09-25: {"n": 10, "stop_atr": 2.0, "trend_filter": "sma200"}
