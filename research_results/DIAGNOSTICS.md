# Descriptive diagnostics: all 268 configurations, full history (NOT used for selection)

Costs as in the research run: maker 0.50%, taker 0.90%; taker round trip incl. spread/slippage ~1.85%. 1% risk per trade, $10,000 start. Full history is in-sample by construction; these figures explain WHY nothing passed and must not be used to pick a strategy.

## Counts

- Configurations with gross (pre-cost) PF > 1: **181 of 268**
- Gross PF >= 1.5: **17** (with >= 500 trades: **4**)
- **Net (after-cost) PF > 1: 0 of 268**

## By timeframe

| TF | Median trades | Median gross PF | Best gross PF (>=100 trades) | Best net PF (>=100 trades) | Median avg gross move / trade |
| --- | --- | --- | --- | --- | --- |
| 5m | 9567 | 1.03 | 2.03 | 0.14 | +0.015% |
| 15m | 3022 | 1.04 | 1.49 | 0.62 | +0.029% |
| 30m | 1465 | 1.07 | 1.51 | 0.87 | +0.076% |
| 1h | 733 | 1.06 | 1.77 | 0.95 | +0.056% |

## Best configuration per family (by net PF, >= 100 trades)

| Family | TF | Params | Trades | Win% (net) | Gross PF | Net PF | Avg gross move/trade | Net return (1% risk) | Max DD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ema_cross | 1h | {"pair": [50, 150], "stop_atr": 3.0} | 300 | 18.0% | 1.68 | 0.95 | +1.67% | -38.6% | 84.9% |
| donchian | 1h | {"n": 100, "stop_atr": 2.5} | 346 | 21.1% | 1.77 | 0.94 | +1.42% | -46.1% | 85.1% |
| ema_pullback | 1h | {"stop_atr": 2.0, "tp_r": 3.0} | 891 | 27.2% | 1.07 | 0.51 | +0.11% | -100.0% | 100.0% |
| hybrid | 1h | {"ema_n": 200, "rsi_max": 40, "trail_atr": 3.0} | 641 | 18.7% | 1.28 | 0.45 | +0.40% | -99.9% | 99.9% |
| regime_switch | 1h | {"adx_level": 20, "stop_atr": 3.0} | 1721 | 17.1% | 1.20 | 0.32 | +0.11% | -100.0% | 100.0% |
| squeeze | 30m | {"pct": 20, "tp_r": 3.0} | 1373 | 27.4% | 1.06 | 0.28 | +0.07% | -100.0% | 100.0% |
| bb_mr | 1h | {"k": 2.5, "stop_atr": 2.0} | 1511 | 17.3% | 0.82 | 0.11 | -0.11% | -100.0% | 100.0% |
| vwap_mr | 1h | {"k": 2.0, "trend": false} | 1132 | 15.1% | 0.84 | 0.09 | -0.07% | -100.0% | 100.0% |
| bb_rsi_ema | 1h | {"ema_n": 200, "k": 1.5, "rsi_max": 40} | 637 | 14.6% | 1.01 | 0.09 | +0.06% | -100.0% | 100.0% |
| rsi_mr | 1h | {"setting": [2, 5]} | 934 | 5.5% | 1.23 | 0.02 | +0.10% | -100.0% | 100.0% |
