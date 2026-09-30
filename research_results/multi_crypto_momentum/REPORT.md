# multi_crypto_momentum - backtest

**Data: DAILY SPOT OHLC used as a PROXY for perpetual trading (no funding, no perp basis, no order book).** Source: `crypto_data.zip`. Shorts are simulated on spot prices with 1x cash collateral; perpetual funding, basis, borrow and liquidation mechanics are NOT modelled.

Rules fixed in `strategy/multi_crypto_momentum.py` / `MULTI_CRYPTO_MOMENTUM.md`; parameters not optimised: `{"lookback": 40, "long_threshold": 0.05, "short_threshold": -0.05, "ema_n": 200, "max_per_coin": 0.1, "max_total": 1.0, "fee_rate": 0.0005, "slippage_rate": 0.0002, "min_order_usd": 1.0}`. Start $200.00.

Period 2020-01-01 -> 2026-09-29. OOS (project convention: last 15% of the span, flat start, own $200) from 2025-09-25.

## Data quality

| coin | first | last | rows | missing_days | bad_ohlc_rows | nonpositive_rows |
|---|---|---|---|---|---|---|
| BTC | 2020-01-01 | 2026-09-29 | 2464 | 0 | 0 | 0 |
| ETH | 2020-01-01 | 2026-09-29 | 2464 | 0 | 0 | 0 |
| SOL | 2020-08-11 | 2026-09-29 | 2241 | 0 | 0 | 0 |
| XRP | 2020-01-01 | 2026-09-29 | 2464 | 0 | 0 | 0 |
| BNB | 2020-01-01 | 2026-09-29 | 2464 | 0 | 0 | 0 |
| DOGE | 2020-01-01 | 2026-09-29 | 2464 | 0 | 0 | 0 |
| LINK | 2020-01-01 | 2026-09-29 | 2464 | 0 | 0 | 0 |
| ADA | 2020-01-01 | 2026-09-29 | 2464 | 0 | 0 | 0 |
| AVAX | 2020-09-22 | 2026-09-29 | 2199 | 0 | 0 | 0 |
| DOT | 2020-08-18 | 2026-09-29 | 2234 | 0 | 0 | 0 |

## Headline (full history)

| Metric | Value |
|---|---|
| Total return | 2,529.90% |
| Ending balance from $200 | $5,259.79 |
| Annualized return | 62.39% |
| Max drawdown | 58.18% |
| Sharpe (daily, ann.) | 1.10 |
| Profit factor | 1.58 |
| Win rate | 33.3% |
| Trades | 615 |
| Average trade | $8.23 (11.16% of notional) |
| Fees paid | $175.54 (slippage $70.21) |
| Exposure | avg gross 54.0% of equity; invested on 86.5% of days |
| Longest losing streak | 31 trades |
| Signals rejected | {'BTC regime filter': 1480, 'portfolio exposure cap (100%)': 86, 'insufficient cash': 10} |
| Marks where a 1x short lost more than its collateral | 0 |

## OOS (flat start)

| Metric | Value |
|---|---|
| OOS return | 36.68% ($273.36) |
| OOS PF | 1.92 |
| OOS max drawdown | 17.64% |
| OOS trades | 111 |
| OOS Sharpe | 1.04 |

## Benchmarks

| | Full: end $ | Full return | Full CAGR | Full max DD | Full Sharpe | OOS return | OOS max DD |
|---|---|---|---|---|---|---|---|
| multi_crypto_momentum | $5,259.79 | 2,529.90% | 62.39% | 58.18% | 1.10 | 36.68% | 17.64% |
| BTC buy-and-hold | $2,322.27 | 1,061.14% | 43.85% | 76.63% | 0.91 | -26.27% | 52.97% |
| Equal-weight buy-and-hold (10 coins) | $4,265.40 | 2,032.70% | 57.42% | 84.24% | 0.96 | -47.88% | 69.10% |

Equal-weight buy-and-hold: $20 per coin bought at each coin's first available open (cash until then).

## Results by coin

| | Trades | Win% | PF | Net P&L $ | Avg trade % | Fees $ |
|---|---|---|---|---|---|---|
| DOGE | 73 | 19.2% | 1.72 | 921.57 | 32.90% | 21.00 |
| ADA | 52 | 34.6% | 1.42 | 407.38 | 20.50% | 15.31 |
| BTC | 62 | 38.7% | 1.99 | 468.68 | 8.51% | 17.29 |
| BNB | 72 | 31.9% | 1.43 | 315.93 | 13.01% | 19.06 |
| XRP | 75 | 33.3% | 1.46 | 458.08 | 2.99% | 20.41 |
| ETH | 48 | 47.9% | 2.28 | 560.23 | 11.12% | 13.12 |
| LINK | 69 | 31.9% | 1.20 | 198.02 | 1.44% | 18.45 |
| DOT | 52 | 34.6% | 1.04 | 34.91 | 0.82% | 15.06 |
| AVAX | 57 | 33.3% | 1.64 | 652.30 | 5.96% | 18.23 |
| SOL | 55 | 34.5% | 2.05 | 1,042.68 | 12.61% | 17.60 |

## Long vs short

| | Trades | Win% | PF | Net P&L $ | Avg trade % | Fees $ |
|---|---|---|---|---|---|---|
| long | 303 | 33.7% | 2.59 | 5,618.73 | 23.82% | 80.80 |
| short | 312 | 33.0% | 0.89 | -558.94 | -1.12% | 94.73 |

## Results by year

| Year | Strategy return | BTC B&H return | Trades (by exit) | PF | Net P&L $ |
|---|---|---|---|---|---|
| 2020 | 53.02% | 301.70% | 22 | 1.50 | 10.94 |
| 2021 | 793.89% | 59.79% | 96 | 2.92 | 2,437.24 |
| 2022 | 18.96% | -64.21% | 102 | 1.00 | 4.12 |
| 2023 | -8.22% | 155.61% | 103 | 0.31 | -1,049.78 |
| 2024 | 28.27% | 121.31% | 99 | 1.91 | 1,277.97 |
| 2025 | 15.24% | -6.33% | 100 | 1.38 | 684.31 |
| 2026 | 19.12% | -4.61% | 93 | 2.54 | 1,695.00 |

## Equity curve

![equity curve](equity_curve.svg)

Data: `equity_curve.csv` (strategy equity, gross exposure, open positions, benchmarks); trades: `trades.csv`.
