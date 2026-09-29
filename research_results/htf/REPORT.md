# BTC Strategy Research Report -- study `htf` (2h, 4h, 6h)

Generated 2026-09-29 03:50 UTC in 17s by `python3 -m backtest.research` (pre-registered protocol: HTF_STRATEGY_PROTOCOL.md).

**Costs:** maker 0.50%, taker 0.90%, half-spread 0.005%, slippage 0.020% (+0.050% on stops) -- user-confirmed Coinbase fee tier (reported 2026-09-29; not fetched via API by this tool) (Intro, 2026-09-29). Spread/slippage are ASSUMED until measured.

## Data

- **2h**: 42,680 bars 2017-01-01 00:00:00+00:00 -> 2026-09-28 22:00:00+00:00; missing 0.0375% (largest gap 7 bars); bad OHLC 0; zero-volume 0. Splits: {'train': '2017-01-01 00:00..2023-10-27 13:00', 'validation': '2023-10-27 13:00..2025-04-13 05:30', 'oos': '2025-04-13 05:30..2026-09-28 22:00'}
- **4h**: 21,343 bars 2017-01-01 00:00:00+00:00 -> 2026-09-28 20:00:00+00:00; missing 0.0234% (largest gap 3 bars); bad OHLC 0; zero-volume 0. Splits: {'train': '2017-01-01 00:00..2023-10-27 11:36', 'validation': '2023-10-27 11:36..2025-04-13 03:48', 'oos': '2025-04-13 03:48..2026-09-28 20:00'}
- **6h**: 14,231 bars 2017-01-01 00:00:00+00:00 -> 2026-09-28 18:00:00+00:00; missing 0.007% (largest gap 1 bars); bad OHLC 0; zero-volume 0. Splits: {'train': '2017-01-01 00:00..2023-10-27 10:12', 'validation': '2023-10-27 10:12..2025-04-13 02:06', 'oos': '2025-04-13 02:06..2026-09-28 18:00'}

## Final comparison table (selected parameters per family/timeframe; 1% risk, after costs)

| Strategy | TF | Trades | Win% | PF | Gross PF | Expectancy | Net return | Max DD | Sharpe | Fees | Slippage | OOS PF | WF PF | Accepted |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| htf_breakout {"ema_slow": 200, "n": 20, "stop_atr": 2.5} | 6h | 160 | 35.6% | 1.37 | 2.57 | 0.330% | 59.5% | 20.3% | 0.56 | $9,792 | $548 | 0.73 | 0.71 | no: validation gate; OOS PF < 1.5; OOS expectancy <= 0; walk-forward PF < 1.5; walk-forward expectancy <= 0 |
| htf_breakout {"ema_slow": 100, "n": 30, "stop_atr": 2.5} | 4h | 222 | 32.9% | 1.26 | 2.50 | 0.291% | 74.1% | 34.9% | 0.56 | $20,034 | $1,120 | 0.47 | n/a | no: parameter neighbourhood median PF < 1.2; validation gate; OOS PF < 1.5; OOS expectancy <= 0; walk-forward PF < 1.5; walk-forward expectancy <= 0; max DD > 25% |
| donchian_ema {"n": 20, "stop_atr": 2.5} | 6h | 114 | 34.2% | 1.58 | 2.83 | 0.526% | 73.6% | 16.7% | 0.67 | $7,654 | $273 | 0.39 | n/a | no: validation gate; OOS PF < 1.5; OOS expectancy <= 0; walk-forward PF < 1.5; walk-forward expectancy <= 0; < 150 trades |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 1.5} | 6h | 172 | 19.8% | 1.15 | 2.45 | 0.310% | 45.5% | 52.3% | 0.34 | $20,338 | $742 | 0.34 | n/a | no: parameter neighbourhood median PF < 1.2; edge depends on a single calendar year; validation gate; OOS PF < 1.5; OOS expectancy <= 0; walk-forward PF < 1.5; walk-forward expectancy <= 0; max DD > 25% |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 2.5} | 4h | 282 | 17.7% | 0.86 | 2.03 | -0.062% | -29.0% | 49.5% | -0.14 | $13,105 | $389 | 0.30 | n/a | no: parameter neighbourhood median PF < 1.2; edge depends on a single calendar year; validation gate; OOS PF < 1.5; OOS expectancy <= 0; walk-forward PF < 1.5; walk-forward expectancy <= 0; max DD > 25% |
| donchian_ema {"n": 30, "stop_atr": 1.5} | 4h | 137 | 29.9% | 1.47 | 3.05 | 1.136% | 279.0% | 38.8% | 0.86 | $43,341 | $1,852 | 0.29 | 0.60 | no: validation gate; OOS PF < 1.5; OOS expectancy <= 0; walk-forward PF < 1.5; walk-forward expectancy <= 0; < 150 trades; max DD > 25% |
| donchian_ema {"n": 30, "stop_atr": 2.5} | 2h | 275 | 25.5% | 0.95 | 1.73 | -0.030% | -23.6% | 69.2% | -0.08 | $34,734 | $1,436 | 0.19 | n/a | no: parameter neighbourhood median PF < 1.2; edge depends on a single calendar year; validation gate; OOS PF < 1.5; OOS expectancy <= 0; walk-forward PF < 1.5; walk-forward expectancy <= 0; max DD > 25% |
| htf_breakout | 2h | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 60 trades and PF > 1) |
| ema_pullback_cont | 2h | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 60 trades and PF > 1) |

## Detailed metrics of every selected configuration (1% risk, after costs)

| Strategy | TF | Split | Trades | Win% | PF before costs | PF after costs | Avg trade | Median trade | Net return | Max DD | Sharpe | Sortino | Avg dur (h) | Exposure | Fees | Slippage | Longest losing streak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| donchian_ema {"n": 30, "stop_atr": 2.5} | 2h | train | 175 | 31.4% | – | 1.28 | 0.466% | -1.159% | 93.5% | 27.5% | 0.63 | 0.55 | 82.4 | 24.1% | $22,995 | $936 | 11.0 |
| donchian_ema {"n": 30, "stop_atr": 2.5} | 2h | val | 53 | 17.0% | – | 0.48 | -0.651% | -1.606% | -30.4% | 31.5% | -1.55 | -1.53 | 64.1 | 26.5% | $3,494 | $151 | 21.0 |
| donchian_ema {"n": 30, "stop_atr": 2.5} | 2h | oos | 47 | 12.8% | 0.81 | 0.19 | -1.161% | -1.649% | -42.5% | 45.4% | -2.99 | -2.42 | 50.3 | 18.5% | $3,811 | $159 | 12.0 |
| donchian_ema {"n": 30, "stop_atr": 2.5} | 2h | full | 275 | 25.5% | 1.73 | 0.95 | -0.030% | -1.361% | -23.6% | 69.2% | -0.08 | -0.07 | 73.4 | 23.6% | $34,734 | $1,436 | 21.0 |
| htf_breakout {"ema_slow": 100, "n": 30, "stop_atr": 2.5} | 4h | train | 149 | 36.9% | – | 1.73 | 0.562% | -0.528% | 115.6% | 16.3% | 1.03 | 1.23 | 122.0 | 30.4% | $11,270 | $626 | 8.0 |
| htf_breakout {"ema_slow": 100, "n": 30, "stop_atr": 2.5} | 4h | val | 38 | 31.6% | – | 0.94 | -0.028% | -0.720% | -1.7% | 11.3% | -0.06 | -0.07 | 117.4 | 34.8% | $1,988 | $110 | 5.0 |
| htf_breakout {"ema_slow": 100, "n": 30, "stop_atr": 2.5} | 4h | oos | 37 | 18.9% | 1.31 | 0.47 | -0.511% | -1.166% | -18.0% | 29.5% | -1.20 | -1.25 | 95.6 | 27.6% | $2,219 | $123 | 22.0 |
| htf_breakout {"ema_slow": 100, "n": 30, "stop_atr": 2.5} | 4h | full | 222 | 32.9% | 2.50 | 1.26 | 0.291% | -0.699% | 74.1% | 34.9% | 0.56 | 0.65 | 119.4 | 31.0% | $20,034 | $1,120 | 22.0 |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 2.5} | 4h | train | 187 | 19.8% | – | 1.02 | 0.093% | -0.473% | 3.0% | 37.4% | 0.13 | 0.07 | 84.8 | 26.5% | $7,654 | $226 | 15.0 |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 2.5} | 4h | val | 55 | 14.5% | – | 0.62 | -0.247% | -0.637% | -13.3% | 20.8% | -0.86 | -0.76 | 70.0 | 30.0% | $2,722 | $83 | 19.0 |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 2.5} | 4h | oos | 41 | 14.6% | 1.47 | 0.30 | -0.639% | -0.924% | -23.3% | 28.9% | -2.05 | -1.76 | 63.3 | 20.3% | $2,819 | $83 | 15.0 |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 2.5} | 4h | full | 282 | 17.7% | 2.03 | 0.86 | -0.062% | -0.550% | -29.0% | 49.5% | -0.14 | -0.08 | 80.0 | 26.4% | $13,105 | $389 | 19.0 |
| donchian_ema {"n": 30, "stop_atr": 1.5} | 4h | train | 86 | 33.7% | – | 2.51 | 1.936% | -1.297% | 346.2% | 19.5% | 1.25 | 1.13 | 165.7 | 23.8% | $17,006 | $695 | 7.0 |
| donchian_ema {"n": 30, "stop_atr": 1.5} | 4h | val | 26 | 26.9% | – | 1.28 | 0.458% | -1.783% | 9.8% | 15.5% | 0.48 | 0.40 | 119.2 | 24.2% | $2,572 | $108 | 6.0 |
| donchian_ema {"n": 30, "stop_atr": 1.5} | 4h | oos | 27 | 22.2% | 1.08 | 0.29 | -1.174% | -1.972% | -27.7% | 34.7% | -1.80 | -1.44 | 74.5 | 15.7% | $2,854 | $129 | 9.0 |
| donchian_ema {"n": 30, "stop_atr": 1.5} | 4h | full | 137 | 29.9% | 3.05 | 1.47 | 1.136% | -1.437% | 279.0% | 38.8% | 0.86 | 0.77 | 143.2 | 23.0% | $43,341 | $1,852 | 9.0 |
| htf_breakout {"ema_slow": 200, "n": 20, "stop_atr": 2.5} | 6h | train | 110 | 38.2% | – | 1.69 | 0.501% | -0.558% | 66.4% | 13.7% | 0.81 | 0.78 | 154.5 | 28.4% | $5,656 | $314 | 9.0 |
| htf_breakout {"ema_slow": 200, "n": 20, "stop_atr": 2.5} | 6h | val | 28 | 28.6% | – | 0.94 | -0.015% | -0.902% | -1.2% | 10.1% | -0.06 | -0.06 | 163.7 | 35.8% | $1,203 | $67 | 4.0 |
| htf_breakout {"ema_slow": 200, "n": 20, "stop_atr": 2.5} | 6h | oos | 23 | 30.4% | 1.96 | 0.73 | -0.192% | -0.859% | -4.8% | 14.2% | -0.37 | -0.40 | 158.1 | 28.4% | $1,294 | $72 | 4.0 |
| htf_breakout {"ema_slow": 200, "n": 20, "stop_atr": 2.5} | 6h | full | 160 | 35.6% | 2.57 | 1.37 | 0.330% | -0.701% | 59.5% | 20.3% | 0.56 | 0.55 | 158.4 | 29.7% | $9,792 | $548 | 9.0 |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 1.5} | 6h | train | 116 | 22.4% | – | 1.59 | 0.766% | -0.657% | 113.5% | 39.4% | 0.81 | 0.74 | 119.1 | 23.1% | $12,815 | $457 | 10.0 |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 1.5} | 6h | val | 36 | 13.9% | – | 0.33 | -0.699% | -1.168% | -23.0% | 26.5% | -1.59 | -1.39 | 81.7 | 23.0% | $2,026 | $79 | 11.0 |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 1.5} | 6h | oos | 20 | 15.0% | 1.69 | 0.34 | -0.734% | -1.204% | -13.9% | 22.5% | -1.13 | -0.79 | 97.2 | 15.2% | $1,814 | $65 | 13.0 |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 1.5} | 6h | full | 172 | 19.8% | 2.45 | 1.15 | 0.310% | -0.804% | 45.5% | 52.3% | 0.34 | 0.31 | 111.3 | 22.4% | $20,338 | $742 | 13.0 |
| donchian_ema {"n": 20, "stop_atr": 2.5} | 6h | train | 74 | 37.8% | – | 2.16 | 0.884% | -0.613% | 85.2% | 11.7% | 0.97 | 0.75 | 194.9 | 24.1% | $4,091 | $152 | 8.0 |
| donchian_ema {"n": 20, "stop_atr": 2.5} | 6h | val | 25 | 28.0% | – | 1.06 | 0.064% | -0.788% | 1.0% | 11.3% | 0.13 | 0.11 | 128.4 | 25.1% | $1,118 | $39 | 9.0 |
| donchian_ema {"n": 20, "stop_atr": 2.5} | 6h | oos | 15 | 26.7% | 1.47 | 0.39 | -0.427% | -0.769% | -6.3% | 9.0% | -0.80 | -0.59 | 170.0 | 19.9% | $817 | $27 | 6.0 |
| donchian_ema {"n": 20, "stop_atr": 2.5} | 6h | full | 114 | 34.2% | 2.83 | 1.58 | 0.526% | -0.716% | 73.6% | 16.7% | 0.67 | 0.52 | 177.1 | 23.6% | $7,654 | $273 | 9.0 |

## Robustness checks (full history, after costs)

| Strategy | TF | Neighbour net PFs | Neighbour median PF | Best year | Best-year share of net | PF without best year |
|---|---|---|---|---|---|---|
| donchian_ema {"n": 30, "stop_atr": 2.5} | 2h | [0.83, 0.96] | 0.90 | 2017.0 | n/a | 0.78 |
| htf_breakout {"ema_slow": 100, "n": 30, "stop_atr": 2.5} | 4h | [1.2, 1.32, 1.09] | 1.20 | 2023.0 | 63% | 1.11 |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 2.5} | 4h | [0.67, 0.79, 0.81] | 0.79 | 2019.0 | n/a | 0.75 |
| donchian_ema {"n": 30, "stop_atr": 1.5} | 4h | [1.31, 1.55] | 1.43 | 2023.0 | 54% | 1.24 |
| htf_breakout {"ema_slow": 200, "n": 20, "stop_atr": 2.5} | 6h | [1.21, 1.5, 1.29, 1.28] | 1.29 | 2023.0 | 57% | 1.18 |
| ema_pullback_cont {"ema_fast": 50, "ema_slow": 200, "stop_atr": 1.5} | 6h | [0.97, 1.13, 1.37] | 1.13 | 2019.0 | 136% | 0.94 |
| donchian_ema {"n": 20, "stop_atr": 2.5} | 6h | [1.68, 2.01, 1.55] | 1.68 | 2017.0 | 37% | 1.40 |

Walk-forward pool: INFORMATIONAL (no strategy passed validation).

## Verdict

**No strategy met the pre-registered acceptance criteria.** No strategy is recommended; nothing should be paper- or live-traded on the basis of this research.

## Walk-forward folds

**donchian_ema 4h**: combined PF 0.60, trades 58, expectancy -0.329%, max DD 22.9%

- train 2017-01-01..2019-01-01 -> test 2019-01-01..2019-07-02: none eligible
- train 2017-07-02..2019-07-02 -> test 2019-07-02..2019-12-31: none eligible
- train 2017-12-31..2019-12-31 -> test 2019-12-31..2020-06-30: none eligible
- train 2018-07-01..2020-06-30 -> test 2020-06-30..2020-12-29: none eligible
- train 2018-12-30..2020-12-29 -> test 2020-12-29..2021-06-29: {"n": 10, "stop_atr": 1.5}
- train 2019-06-30..2021-06-29 -> test 2021-06-29..2021-12-28: {"n": 10, "stop_atr": 1.5}
- train 2019-12-29..2021-12-28 -> test 2021-12-28..2022-06-28: {"n": 15, "stop_atr": 1.5}
- train 2020-06-28..2022-06-28 -> test 2022-06-28..2022-12-27: {"n": 10, "stop_atr": 1.5}
- train 2020-12-27..2022-12-27 -> test 2022-12-27..2023-06-27: none eligible
- train 2021-06-27..2023-06-27 -> test 2023-06-27..2023-12-26: none eligible
- train 2021-12-26..2023-12-26 -> test 2023-12-26..2024-06-25: none eligible
- train 2022-06-26..2024-06-25 -> test 2024-06-25..2024-12-24: none eligible
- train 2022-12-25..2024-12-24 -> test 2024-12-24..2025-06-24: {"n": 10, "stop_atr": 2.5}
- train 2023-06-25..2025-06-24 -> test 2025-06-24..2025-12-23: none eligible
- train 2023-12-24..2025-12-23 -> test 2025-12-23..2026-06-23: none eligible
- train 2024-06-23..2026-06-23 -> test 2026-06-23..2026-09-28: none eligible

**donchian_ema 6h**: combined PF n/a, trades 0, expectancy n/a, max DD n/a

- train 2017-01-01..2019-01-01 -> test 2019-01-01..2019-07-02: none eligible
- train 2017-07-02..2019-07-02 -> test 2019-07-02..2019-12-31: none eligible
- train 2017-12-31..2019-12-31 -> test 2019-12-31..2020-06-30: none eligible
- train 2018-07-01..2020-06-30 -> test 2020-06-30..2020-12-29: none eligible
- train 2018-12-30..2020-12-29 -> test 2020-12-29..2021-06-29: none eligible
- train 2019-06-30..2021-06-29 -> test 2021-06-29..2021-12-28: none eligible
- train 2019-12-29..2021-12-28 -> test 2021-12-28..2022-06-28: none eligible
- train 2020-06-28..2022-06-28 -> test 2022-06-28..2022-12-27: none eligible
- train 2020-12-27..2022-12-27 -> test 2022-12-27..2023-06-27: none eligible
- train 2021-06-27..2023-06-27 -> test 2023-06-27..2023-12-26: none eligible
- train 2021-12-26..2023-12-26 -> test 2023-12-26..2024-06-25: none eligible
- train 2022-06-26..2024-06-25 -> test 2024-06-25..2024-12-24: none eligible
- train 2022-12-25..2024-12-24 -> test 2024-12-24..2025-06-24: none eligible
- train 2023-06-25..2025-06-24 -> test 2025-06-24..2025-12-23: none eligible
- train 2023-12-24..2025-12-23 -> test 2025-12-23..2026-06-23: none eligible
- train 2024-06-23..2026-06-23 -> test 2026-06-23..2026-09-28: none eligible

**htf_breakout 6h**: combined PF 0.71, trades 19, expectancy -0.271%, max DD 15.2%

- train 2017-01-01..2019-01-01 -> test 2019-01-01..2019-07-02: none eligible
- train 2017-07-02..2019-07-02 -> test 2019-07-02..2019-12-31: none eligible
- train 2017-12-31..2019-12-31 -> test 2019-12-31..2020-06-30: none eligible
- train 2018-07-01..2020-06-30 -> test 2020-06-30..2020-12-29: none eligible
- train 2018-12-30..2020-12-29 -> test 2020-12-29..2021-06-29: {"ema_slow": 100, "n": 10, "stop_atr": 1.5}
- train 2019-06-30..2021-06-29 -> test 2021-06-29..2021-12-28: none eligible
- train 2019-12-29..2021-12-28 -> test 2021-12-28..2022-06-28: {"ema_slow": 100, "n": 10, "stop_atr": 1.5}
- train 2020-06-28..2022-06-28 -> test 2022-06-28..2022-12-27: none eligible
- train 2020-12-27..2022-12-27 -> test 2022-12-27..2023-06-27: none eligible
- train 2021-06-27..2023-06-27 -> test 2023-06-27..2023-12-26: none eligible
- train 2021-12-26..2023-12-26 -> test 2023-12-26..2024-06-25: none eligible
- train 2022-06-26..2024-06-25 -> test 2024-06-25..2024-12-24: none eligible
- train 2022-12-25..2024-12-24 -> test 2024-12-24..2025-06-24: none eligible
- train 2023-06-25..2025-06-24 -> test 2025-06-24..2025-12-23: none eligible
- train 2023-12-24..2025-12-23 -> test 2025-12-23..2026-06-23: none eligible
- train 2024-06-23..2026-06-23 -> test 2026-06-23..2026-09-28: none eligible
