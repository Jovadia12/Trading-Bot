# BTC Strategy Research Report

Generated 2026-09-29 01:41 UTC in 80s by `python3 -m backtest.research` (pre-registered protocol: STRATEGY_RESEARCH_PROTOCOL.md).

**Costs:** maker 0.50%, taker 0.90%, half-spread 0.005%, slippage 0.020% (+0.050% on stops) -- Coinbase Advanced US entry tier (UNCONFIRMED default). Spread/slippage are ASSUMED until measured.

## Data

- **5m**: 1,023,585 bars 2017-01-01 00:00:00+00:00 -> 2026-09-28 23:55:00+00:00; missing 0.1092% (largest gap 188 bars); bad OHLC 0; zero-volume 0. Splits: {'train': '2017-01-01 00:00..2023-10-27 14:20', 'validation': '2023-10-27 14:20..2025-04-13 07:07', 'oos': '2025-04-13 07:07..2026-09-28 23:55'}
- **15m**: 341,260 bars 2017-01-01 00:00:00+00:00 -> 2026-09-28 23:45:00+00:00; missing 0.0902% (largest gap 62 bars); bad OHLC 0; zero-volume 0. Splits: {'train': '2017-01-01 00:00..2023-10-27 14:13', 'validation': '2023-10-27 14:13..2025-04-13 06:59', 'oos': '2025-04-13 06:59..2026-09-28 23:45'}
- **30m**: 170,653 bars 2017-01-01 00:00:00+00:00 -> 2026-09-28 23:30:00+00:00; missing 0.0767% (largest gap 30 bars); bad OHLC 0; zero-volume 0. Splits: {'train': '2017-01-01 00:00..2023-10-27 14:03', 'validation': '2023-10-27 14:03..2025-04-13 06:46', 'oos': '2025-04-13 06:46..2026-09-28 23:30'}
- **1h**: 85,339 bars 2017-01-01 00:00:00+00:00 -> 2026-09-28 23:00:00+00:00; missing 0.0621% (largest gap 15 bars); bad OHLC 0; zero-volume 0. Splits: {'train': '2017-01-01 00:00..2023-10-27 13:42', 'validation': '2023-10-27 13:42..2025-04-13 06:21', 'oos': '2025-04-13 06:21..2026-09-28 23:00'}

## Final comparison table (selected parameters per family/timeframe; 1% risk, after costs)

| Strategy | TF | Trades | Win% | PF | Gross PF | Expectancy | Net return | Max DD | Sharpe | Fees | Slippage | OOS PF | WF PF | Accepted |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ema_cross {"pair": [50, 150], "stop_atr": 3.0} | 1h | 300 | 18.0% | 0.95 | 1.68 | -0.021% | -38.6% | 84.9% | -0.12 | $42,304 | $1,928 | 0.44 | 0.64 | no: validation gate; OOS PF < 1.5; OOS expectancy <= 0; walk-forward PF < 1.5; walk-forward expectancy <= 0; < 500 trades; max DD > 25% |
| donchian {"n": 100, "stop_atr": 2.5} | 1h | 346 | 21.1% | 0.94 | 1.77 | -0.070% | -46.1% | 85.1% | -0.13 | $56,666 | $2,516 | 0.29 | n/a | no: validation gate; OOS PF < 1.5; OOS expectancy <= 0; walk-forward PF < 1.5; walk-forward expectancy <= 0; < 500 trades; max DD > 25% |
| bb_mr | 5m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| bb_rsi_ema | 5m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| ema_pullback | 5m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| rsi_mr | 5m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| vwap_mr | 5m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| ema_cross | 5m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| donchian | 5m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| squeeze | 5m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| regime_switch | 5m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| hybrid | 5m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| bb_mr | 15m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| bb_rsi_ema | 15m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| ema_pullback | 15m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| rsi_mr | 15m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| vwap_mr | 15m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| ema_cross | 15m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| donchian | 15m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| squeeze | 15m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| regime_switch | 15m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| hybrid | 15m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| bb_mr | 30m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| bb_rsi_ema | 30m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| ema_pullback | 30m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| rsi_mr | 30m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| vwap_mr | 30m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| ema_cross | 30m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| donchian | 30m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| squeeze | 30m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| regime_switch | 30m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| hybrid | 30m | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| bb_mr | 1h | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| bb_rsi_ema | 1h | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| ema_pullback | 1h | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| rsi_mr | 1h | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| vwap_mr | 1h | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| squeeze | 1h | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| regime_switch | 1h | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |
| hybrid | 1h | – | – | – | – | – | – | – | – | – | – | – | – | no: no parameter set profitable after costs on TRAIN (>= 100 trades and PF > 1) |

Walk-forward pool: INFORMATIONAL (no strategy passed validation).

## Verdict

**No strategy met the pre-registered acceptance criteria.** No strategy is recommended; nothing should be paper- or live-traded on the basis of this research.

## Walk-forward folds

**donchian 1h**: combined PF n/a, trades 0, expectancy n/a, max DD n/a

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

**ema_cross 1h**: combined PF 0.64, trades 68, expectancy -0.436%, max DD 35.8%

- train 2017-01-01..2019-01-01 -> test 2019-01-01..2019-07-02: {"pair": [20, 60], "stop_atr": 2.0}
- train 2017-07-02..2019-07-02 -> test 2019-07-02..2019-12-31: {"pair": [20, 60], "stop_atr": 3.0}
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
