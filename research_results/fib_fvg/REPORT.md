# EMA trend + BOS + Fibonacci + FVG (Unicorn) -- 5m/15m backtest

Generated 2026-10-02 16:48 UTC in 13s by `python3 -m backtest.fib_fvg_study`. Rules: `FIB_FVG_STUDY.md` (objective definitions; the video itself could not be viewed from the research environment, so the rules implement the written specification).

**Coins with 5m data: BTC** of BTC, ETH, SOL, XRP, BNB, DOGE, LINK, ADA, AVAX, DOT. **This is NOT the full 10-coin universe** -- the other coins' 5m data were not available.

Window: 2025-09-29 00:00 -> 2026-09-28 23:55 UTC (365 days). Train (selection only): first 70% to 2026-06-11 12:00; out-of-sample: the last 30%. 32 variants per cost case = 2 versions x 4 stops x 4 exits.

Signals found (whole window incl. warm-up exclusion): {"BTC/standard": 1474, "BTC/unicorn": 75}

Sizing: each entry uses 10% of current equity as notional (1x, cash-capped, shorts as 1x-collateral paper shorts), one position per coin, $200 start.

Data notes: BTC: 149 missing 5m bars (0.14%) filled flat

## Cost cases

- **coinbase_taker**: your Coinbase Intro tier: every leg taker 0.90% + 0.025% spread/slippage (+0.05% on stops)
- **coinbase_maker_like**: entries and fixed take-profits at maker 0.50% assuming the limit fills at the next open (OPTIMISTIC: no missed fills); stops and signal/trailing exits stay taker 0.90% + slippage
- **low_fee_venue_reference**: REFERENCE ONLY, not your account: typical perp-exchange base tier (maker 0.02%, taker 0.05%)
- **zero_cost_diagnostic**: diagnostic only: no fees, no slippage

## Selected candidate per cost case (chosen on TRAIN only, then one OOS look, then full 12 months)

### coinbase_taker: standard, stop atr2.5, exit D: 5R target

| Metric | Train (selection) | Out-of-sample (30%) | Full 12 months |
|---|---|---|---|
| Ending balance (from $200) | $75.39 | $138.56 | $52.77 |
| Total return | -62.31% | -30.72% | -73.62% |
| Trades | 504 | 198 | 698 |
| Win rate | 9.7% | 9.6% | 9.9% |
| Profit factor | 0.06 | 0.05 | 0.06 |
| Average trade (on notional) | -1.935% | -1.851% | -1.906% |
| Average R | -4.91 | -6.21 | -5.27 |
| Max drawdown | -62.34% | -30.72% | -73.62% |
| Sharpe (daily, ann.) | -20.45 | -21.79 | -20.60 |
| Long: trades / win / PF / P&L | 249 / 9.2% / 0.05 / $-62.19 | 104 / 11.5% / 0.07 / $-30.33 | 350 / 10.3% / 0.05 / $-73.07 |
| Short: trades / win / PF / P&L | 255 / 10.2% / 0.07 / $-62.49 | 94 / 7.4% / 0.02 / $-31.11 | 348 / 9.5% / 0.07 / $-74.17 |
| Fees / slippage | $115.99 / $5.92 | $59.91 / $3.03 | $138.26 / $7.04 |
| Biggest winner | BTC short $0.53 (+4.20%) | BTC long $0.49 (+2.59%) | BTC short $0.53 (+4.20%) |
| Biggest loser | BTC short $-0.58 (-4.11%) | BTC short $-0.70 (-3.63%) | BTC short $-0.58 (-4.11%) |

Monthly returns (full 12 months): 2025-09 -0.44%, 2025-10 -13.05%, 2025-11 -7.22%, 2025-12 -11.50%, 2026-01 -8.88%, 2026-02 -11.78%, 2026-03 -11.17%, 2026-04 -14.04%, 2026-05 -11.67%, 2026-06 -6.51%, 2026-07 -10.29%, 2026-08 -9.03%, 2026-09 -10.27%

### coinbase_maker_like: standard, stop atr2.5, exit D: 5R target

| Metric | Train (selection) | Out-of-sample (30%) | Full 12 months |
|---|---|---|---|
| Ending balance (from $200) | $96.69 | $153.02 | $74.64 |
| Total return | -51.66% | -23.49% | -62.68% |
| Trades | 504 | 198 | 698 |
| Win rate | 14.9% | 16.2% | 15.5% |
| Profit factor | 0.14 | 0.13 | 0.14 |
| Average trade (on notional) | -1.442% | -1.351% | -1.410% |
| Average R | -3.63 | -4.58 | -3.88 |
| Max drawdown | -51.72% | -23.49% | -62.69% |
| Sharpe (daily, ann.) | -17.05 | -18.12 | -17.13 |
| Long: trades / win / PF / P&L | 249 / 14.1% / 0.12 / $-51.53 | 104 / 18.3% / 0.17 / $-22.44 | 350 / 15.7% / 0.13 / $-61.70 |
| Short: trades / win / PF / P&L | 255 / 15.7% / 0.16 / $-51.87 | 94 / 13.8% / 0.08 / $-24.54 | 348 / 15.2% / 0.14 / $-63.66 |
| Fees / slippage | $95.77 / $4.51 | $46.35 / $2.14 | $117.80 / $5.52 |
| Biggest winner | BTC short $0.71 (+5.03%) | BTC long $0.66 (+3.46%) | BTC short $0.71 (+5.03%) |
| Biggest loser | BTC short $-0.53 (-3.69%) | BTC short $-0.63 (-3.20%) | BTC short $-0.53 (-3.69%) |

Monthly returns (full 12 months): 2025-09 -0.36%, 2025-10 -10.00%, 2025-11 -5.03%, 2025-12 -9.13%, 2026-01 -6.28%, 2026-02 -9.16%, 2026-03 -8.33%, 2026-04 -10.98%, 2026-05 -8.89%, 2026-06 -4.21%, 2026-07 -7.69%, 2026-08 -6.60%, 2026-09 -7.75%

### low_fee_venue_reference: standard, stop atr2.5, exit A: 15m opposite EMA/structure

| Metric | Train (selection) | Out-of-sample (30%) | Full 12 months |
|---|---|---|---|
| Ending balance (from $200) | $188.50 | $193.69 | $182.52 |
| Total return | -5.75% | -3.15% | -8.74% |
| Trades | 607 | 268 | 874 |
| Win rate | 20.6% | 19.8% | 20.3% |
| Profit factor | 0.74 | 0.66 | 0.72 |
| Average trade (on notional) | -0.097% | -0.119% | -0.104% |
| Average R | -0.28 | -0.35 | -0.30 |
| Max drawdown | -7.23% | -3.84% | -9.83% |
| Sharpe (daily, ann.) | -2.44 | -3.25 | -2.70 |
| Long: trades / win / PF / P&L | 301 / 21.3% / 0.65 / $-7.63 | 142 / 21.8% / 0.84 / $-1.55 | 442 / 21.3% / 0.70 / $-9.12 |
| Short: trades / win / PF / P&L | 306 / 19.9% / 0.83 / $-3.88 | 126 / 17.5% / 0.47 / $-4.75 | 432 / 19.2% / 0.73 / $-8.36 |
| Fees / slippage | $8.20 / $6.12 | $3.67 / $2.93 | $11.65 / $8.87 |
| Biggest winner | BTC short $1.32 (+7.08%) | BTC long $2.04 (+10.51%) | BTC long $1.92 (+10.51%) |
| Biggest loser | BTC short $-0.34 (-1.71%) | BTC short $-0.37 (-1.86%) | BTC short $-0.35 (-1.86%) |

Monthly returns (full 12 months): 2025-09 -0.00%, 2025-10 -1.44%, 2025-11 -0.90%, 2025-12 -0.79%, 2026-01 -0.73%, 2026-02 +0.22%, 2026-03 -0.96%, 2026-04 -1.37%, 2026-05 -0.88%, 2026-06 -0.11%, 2026-07 -1.45%, 2026-08 -0.17%, 2026-09 -0.53%

## Every variant (full 12 months; train and OOS profit factor shown for context -- NOT for re-selection)

| Costs | Version | Stop | Exit | Trades | Win% | PF | Avg trade | Avg R | Return | Max DD | Fees | Train PF | OOS PF | OOS return |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| coinbase_maker_like | standard | atr1.5 | A | 985 | 4.2% | 0.05 | -1.464% | -7.54 | -76.39% | -76.43% | $145.66 | 0.05 | 0.04 | -34.71% |
| coinbase_maker_like | standard | atr1.5 | B | 1009 | 4.0% | 0.05 | -1.461% | -7.53 | -77.13% | -77.13% | $147.42 | 0.05 | 0.04 | -34.90% |
| coinbase_maker_like | standard | atr1.5 | R3 | 1234 | 6.4% | 0.02 | -1.357% | -6.83 | -81.29% | -81.29% | $156.26 | 0.03 | 0.01 | -39.61% |
| coinbase_maker_like | standard | atr1.5 | R5 | 1078 | 10.3% | 0.05 | -1.408% | -6.92 | -78.12% | -78.12% | $146.74 | 0.05 | 0.04 | -35.74% |
| coinbase_maker_like | standard | atr2 | A | 919 | 5.8% | 0.06 | -1.452% | -5.66 | -73.70% | -73.74% | $141.68 | 0.06 | 0.04 | -33.55% |
| coinbase_maker_like | standard | atr2 | B | 956 | 4.9% | 0.06 | -1.462% | -5.67 | -75.32% | -75.32% | $143.90 | 0.06 | 0.04 | -34.11% |
| coinbase_maker_like | standard | atr2 | R3 | 1058 | 11.6% | 0.05 | -1.374% | -5.02 | -76.65% | -76.66% | $144.95 | 0.05 | 0.03 | -35.12% |
| coinbase_maker_like | standard | atr2 | R5 | 902 | 13.5% | 0.09 | -1.419% | -5.11 | -72.24% | -72.25% | $134.97 | 0.10 | 0.07 | -31.28% |
| coinbase_maker_like | standard | atr2.5 | A | 874 | 6.4% | 0.07 | -1.434% | -4.50 | -71.49% | -71.53% | $138.97 | 0.08 | 0.06 | -32.22% |
| coinbase_maker_like | standard | atr2.5 | B | 915 | 5.7% | 0.07 | -1.445% | -4.51 | -73.37% | -73.37% | $141.93 | 0.07 | 0.05 | -33.32% |
| coinbase_maker_like | standard | atr2.5 | R3 | 878 | 16.7% | 0.09 | -1.358% | -3.86 | -69.69% | -69.70% | $132.71 | 0.10 | 0.06 | -29.67% |
| coinbase_maker_like | standard | atr2.5 | R5 | 698 | 15.5% | 0.14 | -1.410% | -3.88 | -62.68% | -62.69% | $117.80 | 0.14 | 0.13 | -23.49% |
| coinbase_maker_like | standard | struct | A | 1032 | 4.1% | 0.04 | -1.462% | -10.79 | -77.92% | -77.95% | $148.43 | 0.04 | 0.04 | -36.01% |
| coinbase_maker_like | standard | struct | B | 1058 | 3.7% | 0.04 | -1.464% | -10.81 | -78.79% | -78.79% | $150.12 | 0.04 | 0.03 | -36.67% |
| coinbase_maker_like | standard | struct | R3 | 1247 | 4.8% | 0.02 | -1.363% | -9.72 | -81.74% | -81.75% | $156.54 | 0.02 | 0.00 | -41.56% |
| coinbase_maker_like | standard | struct | R5 | 1112 | 8.3% | 0.04 | -1.408% | -10.18 | -79.13% | -79.13% | $150.04 | 0.05 | 0.02 | -39.07% |
| coinbase_maker_like | unicorn | atr1.5 | A | 72 | 1.4% | 0.00 | -1.503% | -8.53 | -10.26% | -10.26% | $19.10 | 0.00 | 0.00 | -3.17% |
| coinbase_maker_like | unicorn | atr1.5 | B | 73 | 0.0% | 0.00 | -1.533% | -8.82 | -10.59% | -10.60% | $19.33 | 0.00 | 0.00 | -3.28% |
| coinbase_maker_like | unicorn | atr1.5 | R3 | 69 | 4.3% | 0.01 | -1.326% | -7.32 | -8.75% | -8.77% | $17.08 | 0.01 | 0.00 | -2.85% |
| coinbase_maker_like | unicorn | atr1.5 | R5 | 69 | 7.2% | 0.02 | -1.438% | -7.57 | -9.45% | -9.53% | $17.52 | 0.02 | 0.04 | -2.66% |
| coinbase_maker_like | unicorn | atr2 | A | 72 | 2.8% | 0.00 | -1.488% | -6.40 | -10.17% | -10.23% | $19.12 | 0.01 | 0.00 | -3.23% |
| coinbase_maker_like | unicorn | atr2 | B | 73 | 1.4% | 0.00 | -1.531% | -6.64 | -10.58% | -10.58% | $19.33 | 0.00 | 0.00 | -3.36% |
| coinbase_maker_like | unicorn | atr2 | R3 | 69 | 10.1% | 0.02 | -1.407% | -5.71 | -9.26% | -9.37% | $17.26 | 0.03 | 0.01 | -2.86% |
| coinbase_maker_like | unicorn | atr2 | R5 | 68 | 11.8% | 0.05 | -1.483% | -5.96 | -9.60% | -9.80% | $17.40 | 0.05 | 0.06 | -3.00% |
| coinbase_maker_like | unicorn | atr2.5 | A | 72 | 2.8% | 0.00 | -1.488% | -5.10 | -10.17% | -10.24% | $19.10 | 0.01 | 0.00 | -3.11% |
| coinbase_maker_like | unicorn | atr2.5 | B | 73 | 1.4% | 0.00 | -1.505% | -5.20 | -10.41% | -10.42% | $19.34 | 0.00 | 0.00 | -3.23% |
| coinbase_maker_like | unicorn | atr2.5 | R3 | 69 | 13.0% | 0.03 | -1.377% | -4.33 | -9.07% | -9.22% | $17.02 | 0.03 | 0.05 | -2.51% |
| coinbase_maker_like | unicorn | atr2.5 | R5 | 65 | 12.3% | 0.07 | -1.509% | -4.95 | -9.35% | -9.42% | $16.69 | 0.07 | 0.05 | -2.75% |
| coinbase_maker_like | unicorn | struct | A | 74 | 1.4% | 0.00 | -1.529% | -10.29 | -10.70% | -10.70% | $19.58 | 0.00 | 0.00 | -3.15% |
| coinbase_maker_like | unicorn | struct | B | 74 | 0.0% | 0.00 | -1.553% | -10.52 | -10.87% | -10.87% | $19.56 | 0.00 | 0.00 | -3.27% |
| coinbase_maker_like | unicorn | struct | R3 | 74 | 4.1% | 0.01 | -1.388% | -9.48 | -9.77% | -9.81% | $18.31 | 0.01 | 0.01 | -2.87% |
| coinbase_maker_like | unicorn | struct | R5 | 74 | 4.1% | 0.01 | -1.543% | -10.29 | -10.80% | -10.91% | $18.97 | 0.01 | 0.03 | -3.25% |
| coinbase_taker | standard | atr1.5 | A | 985 | 3.6% | 0.03 | -1.889% | -9.75 | -84.48% | -84.48% | $160.55 | 0.03 | 0.02 | -42.34% |
| coinbase_taker | standard | atr1.5 | B | 1009 | 3.2% | 0.03 | -1.886% | -9.74 | -85.12% | -85.12% | $162.06 | 0.03 | 0.02 | -42.58% |
| coinbase_taker | standard | atr1.5 | R3 | 1234 | 0.7% | 0.00 | -1.885% | -9.45 | -90.26% | -90.26% | $172.54 | 0.00 | 0.00 | -50.18% |
| coinbase_taker | standard | atr1.5 | R5 | 1078 | 2.7% | 0.01 | -1.903% | -9.38 | -87.18% | -87.18% | $163.52 | 0.01 | 0.01 | -45.29% |
| coinbase_taker | standard | atr2 | A | 919 | 4.6% | 0.04 | -1.877% | -7.33 | -82.21% | -82.22% | $157.19 | 0.04 | 0.02 | -40.97% |
| coinbase_taker | standard | atr2 | B | 956 | 3.6% | 0.04 | -1.887% | -7.33 | -83.57% | -83.57% | $159.06 | 0.04 | 0.02 | -41.58% |
| coinbase_taker | standard | atr2 | R3 | 1058 | 2.6% | 0.01 | -1.901% | -6.95 | -86.65% | -86.65% | $163.51 | 0.01 | 0.00 | -45.00% |
| coinbase_taker | standard | atr2 | R5 | 902 | 6.2% | 0.03 | -1.912% | -6.91 | -82.21% | -82.21% | $153.60 | 0.04 | 0.02 | -39.78% |
| coinbase_taker | standard | atr2.5 | A | 874 | 5.1% | 0.05 | -1.859% | -5.84 | -80.34% | -80.35% | $154.93 | 0.05 | 0.04 | -39.53% |
| coinbase_taker | standard | atr2.5 | B | 915 | 4.2% | 0.04 | -1.870% | -5.84 | -81.96% | -81.96% | $157.51 | 0.05 | 0.03 | -40.71% |
| coinbase_taker | standard | atr2.5 | R3 | 878 | 5.8% | 0.02 | -1.888% | -5.37 | -80.98% | -80.98% | $153.47 | 0.03 | 0.01 | -38.89% |
| coinbase_taker | standard | atr2.5 | R5 | 698 | 9.9% | 0.06 | -1.906% | -5.27 | -73.62% | -73.62% | $138.26 | 0.06 | 0.05 | -30.72% |
| coinbase_taker | standard | struct | A | 1032 | 3.3% | 0.02 | -1.887% | -13.97 | -85.77% | -85.77% | $162.86 | 0.02 | 0.02 | -43.90% |
| coinbase_taker | standard | struct | B | 1058 | 2.7% | 0.02 | -1.889% | -13.99 | -86.48% | -86.48% | $164.28 | 0.02 | 0.02 | -44.60% |
| coinbase_taker | standard | struct | R3 | 1247 | 0.6% | 0.00 | -1.893% | -13.56 | -90.59% | -90.59% | $172.76 | 0.00 | 0.00 | -52.44% |
| coinbase_taker | standard | struct | R5 | 1112 | 2.6% | 0.01 | -1.903% | -13.80 | -87.97% | -87.97% | $166.57 | 0.01 | 0.00 | -48.89% |
| coinbase_taker | unicorn | atr1.5 | A | 72 | 0.0% | 0.00 | -1.928% | -10.95 | -12.97% | -12.97% | $24.20 | 0.00 | 0.00 | -4.07% |
| coinbase_taker | unicorn | atr1.5 | B | 73 | 0.0% | 0.00 | -1.957% | -11.29 | -13.33% | -13.33% | $24.49 | 0.00 | 0.00 | -4.18% |
| coinbase_taker | unicorn | atr1.5 | R3 | 69 | 0.0% | 0.00 | -1.862% | -10.35 | -12.07% | -12.07% | $23.31 | 0.00 | 0.00 | -3.92% |
| coinbase_taker | unicorn | atr1.5 | R5 | 69 | 0.0% | 0.00 | -1.930% | -10.46 | -12.48% | -12.52% | $23.22 | 0.00 | 0.00 | -3.73% |
| coinbase_taker | unicorn | atr2 | A | 72 | 0.0% | 0.00 | -1.913% | -8.22 | -12.88% | -12.91% | $24.22 | 0.00 | 0.00 | -4.14% |
| coinbase_taker | unicorn | atr2 | B | 73 | 0.0% | 0.00 | -1.956% | -8.49 | -13.32% | -13.32% | $24.49 | 0.00 | 0.00 | -4.26% |
| coinbase_taker | unicorn | atr2 | R3 | 69 | 1.4% | 0.00 | -1.924% | -7.93 | -12.44% | -12.48% | $23.25 | 0.00 | 0.00 | -3.93% |
| coinbase_taker | unicorn | atr2 | R5 | 68 | 5.9% | 0.01 | -1.964% | -8.08 | -12.52% | -12.63% | $22.89 | 0.01 | 0.01 | -3.98% |
| coinbase_taker | unicorn | atr2.5 | A | 72 | 0.0% | 0.00 | -1.913% | -6.56 | -12.88% | -12.91% | $24.20 | 0.00 | 0.00 | -4.02% |
| coinbase_taker | unicorn | atr2.5 | B | 73 | 0.0% | 0.00 | -1.930% | -6.68 | -13.15% | -13.16% | $24.50 | 0.00 | 0.00 | -4.13% |
| coinbase_taker | unicorn | atr2.5 | R3 | 69 | 0.0% | 0.00 | -1.913% | -6.19 | -12.38% | -12.44% | $23.22 | 0.00 | 0.00 | -3.67% |
| coinbase_taker | unicorn | atr2.5 | R5 | 65 | 6.2% | 0.02 | -1.986% | -6.51 | -12.12% | -12.15% | $21.91 | 0.02 | 0.01 | -3.61% |
| coinbase_taker | unicorn | struct | A | 74 | 0.0% | 0.00 | -1.954% | -13.25 | -13.47% | -13.47% | $24.80 | 0.00 | 0.00 | -4.06% |
| coinbase_taker | unicorn | struct | B | 74 | 0.0% | 0.00 | -1.978% | -13.48 | -13.63% | -13.63% | $24.77 | 0.00 | 0.00 | -4.17% |
| coinbase_taker | unicorn | struct | R3 | 74 | 1.4% | 0.00 | -1.916% | -13.19 | -13.23% | -13.24% | $24.82 | 0.00 | 0.00 | -4.02% |
| coinbase_taker | unicorn | struct | R5 | 74 | 1.4% | 0.00 | -2.013% | -13.57 | -13.86% | -13.93% | $24.75 | 0.00 | 0.00 | -4.23% |
| low_fee_venue_reference | standard | atr1.5 | A | 985 | 15.1% | 0.58 | -0.134% | -0.62 | -12.41% | -13.15% | $12.87 | 0.58 | 0.55 | -3.68% |
| low_fee_venue_reference | standard | atr1.5 | B | 1009 | 15.2% | 0.58 | -0.131% | -0.62 | -12.40% | -13.13% | $13.19 | 0.58 | 0.56 | -3.59% |
| low_fee_venue_reference | standard | atr1.5 | R3 | 1234 | 24.4% | 0.63 | -0.117% | -0.62 | -13.49% | -13.68% | $14.43 | 0.66 | 0.53 | -4.78% |
| low_fee_venue_reference | standard | atr1.5 | R5 | 1078 | 16.5% | 0.60 | -0.139% | -0.64 | -13.96% | -14.36% | $12.91 | 0.59 | 0.63 | -3.55% |
| low_fee_venue_reference | standard | atr2 | A | 919 | 18.1% | 0.65 | -0.122% | -0.43 | -10.63% | -11.32% | $12.14 | 0.68 | 0.57 | -3.79% |
| low_fee_venue_reference | standard | atr2 | B | 956 | 17.4% | 0.61 | -0.132% | -0.47 | -11.91% | -12.57% | $12.55 | 0.64 | 0.55 | -3.96% |
| low_fee_venue_reference | standard | atr2 | R3 | 1058 | 24.1% | 0.66 | -0.133% | -0.47 | -13.13% | -13.56% | $12.35 | 0.68 | 0.61 | -4.12% |
| low_fee_venue_reference | standard | atr2 | R5 | 902 | 16.0% | 0.66 | -0.148% | -0.50 | -12.57% | -13.05% | $10.93 | 0.66 | 0.65 | -3.51% |
| low_fee_venue_reference | standard | atr2.5 | A | 874 | 20.3% | 0.72 | -0.104% | -0.30 | -8.74% | -9.83% | $11.65 | 0.74 | 0.66 | -3.15% |
| low_fee_venue_reference | standard | atr2.5 | B | 915 | 19.5% | 0.68 | -0.114% | -0.34 | -9.99% | -10.96% | $12.14 | 0.71 | 0.60 | -3.70% |
| low_fee_venue_reference | standard | atr2.5 | R3 | 878 | 24.8% | 0.74 | -0.120% | -0.34 | -10.03% | -10.34% | $10.37 | 0.74 | 0.73 | -2.79% |
| low_fee_venue_reference | standard | atr2.5 | R5 | 698 | 16.9% | 0.73 | -0.142% | -0.35 | -9.48% | -10.32% | $8.58 | 0.69 | 0.81 | -1.69% |
| low_fee_venue_reference | standard | struct | A | 1032 | 13.7% | 0.54 | -0.132% | -0.83 | -12.80% | -13.64% | $13.42 | 0.53 | 0.57 | -3.44% |
| low_fee_venue_reference | standard | struct | B | 1058 | 13.2% | 0.53 | -0.134% | -0.85 | -13.28% | -14.08% | $13.74 | 0.53 | 0.54 | -3.81% |
| low_fee_venue_reference | standard | struct | R3 | 1247 | 24.9% | 0.56 | -0.125% | -0.85 | -14.41% | -14.55% | $14.50 | 0.60 | 0.45 | -5.31% |
| low_fee_venue_reference | standard | struct | R5 | 1112 | 16.5% | 0.56 | -0.139% | -0.94 | -14.30% | -14.65% | $13.40 | 0.58 | 0.52 | -4.67% |
| low_fee_venue_reference | unicorn | atr1.5 | A | 72 | 13.9% | 0.32 | -0.173% | -0.94 | -1.24% | -1.35% | $1.00 | 0.30 | 0.38 | -0.29% |
| low_fee_venue_reference | unicorn | atr1.5 | B | 73 | 13.7% | 0.26 | -0.203% | -1.11 | -1.47% | -1.58% | $1.01 | 0.27 | 0.24 | -0.41% |
| low_fee_venue_reference | unicorn | atr1.5 | R3 | 69 | 26.1% | 0.67 | -0.093% | -0.58 | -0.64% | -0.74% | $0.85 | 0.74 | 0.49 | -0.28% |
| low_fee_venue_reference | unicorn | atr1.5 | R5 | 69 | 15.9% | 0.49 | -0.167% | -0.71 | -1.15% | -1.32% | $0.89 | 0.37 | 0.84 | -0.09% |
| low_fee_venue_reference | unicorn | atr2 | A | 72 | 18.1% | 0.41 | -0.157% | -0.70 | -1.13% | -1.36% | $1.00 | 0.44 | 0.33 | -0.36% |
| low_fee_venue_reference | unicorn | atr2 | B | 73 | 16.4% | 0.33 | -0.201% | -0.85 | -1.45% | -1.57% | $1.01 | 0.37 | 0.21 | -0.49% |
| low_fee_venue_reference | unicorn | atr2 | R3 | 69 | 21.7% | 0.56 | -0.157% | -0.61 | -1.08% | -1.32% | $0.87 | 0.56 | 0.56 | -0.29% |
| low_fee_venue_reference | unicorn | atr2 | R5 | 68 | 13.2% | 0.49 | -0.202% | -0.72 | -1.37% | -1.69% | $0.89 | 0.48 | 0.52 | -0.36% |
| low_fee_venue_reference | unicorn | atr2.5 | A | 72 | 20.8% | 0.44 | -0.158% | -0.55 | -1.13% | -1.46% | $1.00 | 0.40 | 0.53 | -0.24% |
| low_fee_venue_reference | unicorn | atr2.5 | B | 73 | 21.9% | 0.42 | -0.175% | -0.57 | -1.27% | -1.48% | $1.01 | 0.43 | 0.38 | -0.36% |
| low_fee_venue_reference | unicorn | atr2.5 | R3 | 69 | 26.1% | 0.65 | -0.143% | -0.32 | -0.99% | -1.52% | $0.85 | 0.55 | 0.98 | -0.01% |
| low_fee_venue_reference | unicorn | atr2.5 | R5 | 65 | 13.8% | 0.52 | -0.224% | -0.66 | -1.45% | -1.98% | $0.85 | 0.50 | 0.56 | -0.33% |
| low_fee_venue_reference | unicorn | struct | A | 74 | 13.5% | 0.29 | -0.199% | -1.01 | -1.46% | -1.57% | $1.03 | 0.26 | 0.39 | -0.28% |
| low_fee_venue_reference | unicorn | struct | B | 74 | 12.2% | 0.24 | -0.223% | -1.24 | -1.64% | -1.75% | $1.03 | 0.23 | 0.25 | -0.40% |
| low_fee_venue_reference | unicorn | struct | R3 | 74 | 24.3% | 0.50 | -0.148% | -0.85 | -1.09% | -1.21% | $0.92 | 0.46 | 0.63 | -0.21% |
| low_fee_venue_reference | unicorn | struct | R5 | 74 | 10.8% | 0.28 | -0.253% | -1.29 | -1.85% | -2.05% | $0.98 | 0.25 | 0.35 | -0.45% |
| zero_cost_diagnostic | standard | atr1.5 | A | 985 | 17.7% | 0.99 | -0.002% | 0.08 | -0.19% | -2.39% | $0.00 | 0.98 | 1.03 | +0.15% |
| zero_cost_diagnostic | standard | atr1.5 | B | 1009 | 19.0% | 1.07 | +0.014% | 0.14 | +1.41% | -2.13% | $0.00 | 1.06 | 1.13 | +0.63% |
| zero_cost_diagnostic | standard | atr1.5 | R3 | 1234 | 24.4% | 1.01 | +0.002% | -0.02 | +0.25% | -1.67% | $0.00 | 1.04 | 0.92 | -0.49% |
| zero_cost_diagnostic | standard | atr1.5 | R5 | 1078 | 16.5% | 0.95 | -0.012% | -0.01 | -1.26% | -3.56% | $0.00 | 0.91 | 1.07 | +0.44% |
| zero_cost_diagnostic | standard | atr2 | A | 919 | 20.9% | 1.02 | +0.006% | 0.07 | +0.49% | -2.03% | $0.00 | 1.05 | 0.95 | -0.27% |
| zero_cost_diagnostic | standard | atr2 | B | 956 | 22.0% | 1.06 | +0.013% | 0.09 | +1.19% | -2.24% | $0.00 | 1.07 | 1.01 | +0.07% |
| zero_cost_diagnostic | standard | atr2 | R3 | 1058 | 24.1% | 0.95 | -0.013% | -0.04 | -1.40% | -3.00% | $0.00 | 0.96 | 0.94 | -0.43% |
| zero_cost_diagnostic | standard | atr2 | R5 | 902 | 16.0% | 0.93 | -0.020% | -0.04 | -1.85% | -4.11% | $0.00 | 0.92 | 0.98 | -0.15% |
| zero_cost_diagnostic | standard | atr2.5 | A | 874 | 23.6% | 1.07 | +0.019% | 0.10 | +1.65% | -2.03% | $0.00 | 1.09 | 1.03 | +0.17% |
| zero_cost_diagnostic | standard | atr2.5 | B | 915 | 25.4% | 1.12 | +0.031% | 0.11 | +2.79% | -1.51% | $0.00 | 1.16 | 1.04 | +0.23% |
| zero_cost_diagnostic | standard | atr2.5 | R3 | 878 | 24.8% | 1.00 | -0.001% | -0.01 | -0.12% | -3.32% | $0.00 | 0.98 | 1.03 | +0.25% |
| zero_cost_diagnostic | standard | atr2.5 | R5 | 698 | 16.9% | 0.96 | -0.015% | 0.01 | -1.06% | -3.93% | $0.00 | 0.90 | 1.12 | +0.80% |
| zero_cost_diagnostic | standard | struct | A | 1032 | 16.0% | 1.01 | +0.002% | 0.20 | +0.22% | -2.78% | $0.00 | 0.97 | 1.14 | +0.66% |
| zero_cost_diagnostic | standard | struct | B | 1058 | 16.9% | 1.06 | +0.011% | 0.23 | +1.10% | -2.13% | $0.00 | 1.03 | 1.15 | +0.68% |
| zero_cost_diagnostic | standard | struct | R3 | 1247 | 24.9% | 0.97 | -0.006% | -0.01 | -0.73% | -2.15% | $0.00 | 1.01 | 0.86 | -0.81% |
| zero_cost_diagnostic | standard | struct | R5 | 1112 | 16.5% | 0.94 | -0.011% | -0.01 | -1.22% | -2.60% | $0.00 | 0.95 | 0.95 | -0.29% |
| zero_cost_diagnostic | unicorn | atr1.5 | A | 72 | 23.6% | 0.67 | -0.048% | -0.23 | -0.35% | -0.52% | $0.00 | 0.59 | 0.93 | -0.02% |
| zero_cost_diagnostic | unicorn | atr1.5 | B | 73 | 19.2% | 0.63 | -0.058% | -0.27 | -0.42% | -0.56% | $0.00 | 0.61 | 0.68 | -0.09% |
| zero_cost_diagnostic | unicorn | atr1.5 | R3 | 69 | 26.1% | 1.14 | +0.024% | 0.04 | +0.17% | -0.32% | $0.00 | 1.23 | 0.90 | -0.03% |
| zero_cost_diagnostic | unicorn | atr1.5 | R5 | 69 | 15.9% | 0.81 | -0.039% | -0.04 | -0.27% | -0.51% | $0.00 | 0.60 | 1.51 | +0.16% |
| zero_cost_diagnostic | unicorn | atr2 | A | 72 | 27.8% | 0.78 | -0.037% | -0.18 | -0.27% | -0.56% | $0.00 | 0.80 | 0.72 | -0.09% |
| zero_cost_diagnostic | unicorn | atr2 | B | 73 | 21.9% | 0.69 | -0.056% | -0.22 | -0.41% | -0.54% | $0.00 | 0.75 | 0.53 | -0.17% |
| zero_cost_diagnostic | unicorn | atr2 | R3 | 69 | 21.7% | 0.86 | -0.035% | -0.13 | -0.24% | -0.60% | $0.00 | 0.84 | 0.90 | -0.04% |
| zero_cost_diagnostic | unicorn | atr2 | R5 | 68 | 13.2% | 0.74 | -0.071% | -0.21 | -0.48% | -0.82% | $0.00 | 0.71 | 0.83 | -0.08% |
| zero_cost_diagnostic | unicorn | atr2.5 | A | 72 | 30.6% | 0.78 | -0.042% | -0.15 | -0.30% | -0.69% | $0.00 | 0.69 | 1.06 | +0.02% |
| zero_cost_diagnostic | unicorn | atr2.5 | B | 73 | 27.4% | 0.84 | -0.030% | -0.07 | -0.22% | -0.48% | $0.00 | 0.83 | 0.89 | -0.04% |
| zero_cost_diagnostic | unicorn | atr2.5 | R3 | 69 | 26.1% | 0.91 | -0.026% | 0.04 | -0.18% | -0.75% | $0.00 | 0.75 | 1.47 | +0.22% |
| zero_cost_diagnostic | unicorn | atr2.5 | R5 | 65 | 13.8% | 0.73 | -0.093% | -0.22 | -0.60% | -1.17% | $0.00 | 0.69 | 0.84 | -0.08% |
| zero_cost_diagnostic | unicorn | struct | A | 74 | 21.6% | 0.58 | -0.070% | -0.10 | -0.52% | -0.71% | $0.00 | 0.48 | 0.96 | -0.01% |
| zero_cost_diagnostic | unicorn | struct | B | 74 | 16.2% | 0.53 | -0.078% | -0.23 | -0.58% | -0.74% | $0.00 | 0.48 | 0.72 | -0.08% |
| zero_cost_diagnostic | unicorn | struct | R3 | 74 | 24.3% | 0.85 | -0.029% | -0.03 | -0.21% | -0.43% | $0.00 | 0.75 | 1.15 | +0.05% |
| zero_cost_diagnostic | unicorn | struct | R5 | 74 | 10.8% | 0.46 | -0.119% | -0.35 | -0.88% | -1.11% | $0.00 | 0.41 | 0.62 | -0.15% |

## Comparison over the same 12 months

| Strategy | Ending balance | Return | Max DD | Sharpe | Trades | PF | Win% |
|---|---|---|---|---|---|---|---|
| fib_fvg selected [coinbase_taker] standard / atr2.5 / R5 | $52.77 | -73.62% | -73.62% | -20.60 | 698 | 0.06 | 9.9% |
| fib_fvg selected [coinbase_maker_like] standard / atr2.5 / R5 | $74.64 | -62.68% | -62.69% | -17.13 | 698 | 0.14 | 15.5% |
| fib_fvg selected [low_fee_venue_reference] standard / atr2.5 / A | $182.52 | -8.74% | -9.83% | -2.70 | 874 | 0.72 | 20.3% |
| multi_crypto_momentum (its spec: 0.05% fee + 0.02% slippage) | $269.58 | +34.79% | -17.47% | 1.01 | 111 | 1.87 | 46.8% |
| multi_crypto_momentum at Coinbase taker 0.90% + 0.02% slippage | $226.81 | +13.40% | -20.44% | 0.53 | 110 | 1.28 | 40.9% |
| BTC buy-and-hold (0.90% taker in/out) | $146.17 | -26.91% | -52.97% | -0.49 | 1 | n/a | n/a |

multi_crypto_momentum uses the 10-coin DAILY Binance-format data (crypto_data.zip) over the same dates; the fib_fvg rows use only the coins listed above.
