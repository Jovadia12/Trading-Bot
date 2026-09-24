# High-win-rate pullback study: pre-registered protocol
Written 2026-09-24T02:47:43Z, before any result of this study was computed.

## Goal
Keep the RSI(2) pullback concept (buy short-term oversold dips inside an uptrend) but trade less often,
capture larger moves, and survive REAL execution costs. Live target: BTC spot (cbBTC on Axiom or BTC on a
spot exchange), long-only, cash-only, no leverage/margin/borrowing. Shorts are researched for information only.

## Execution venue and costs (verified 2026-09-24; see sources in report)
Axiom = Solana swap terminal; BTC exposure = cbBTC swaps routed through Solana pools. Flat fee per swap (buy AND sell),
no maker discount. Fixed network cost = priority fee + Jito tip, valued at SOL = $117.
| Scenario | Platform fee/side | Pool fee | Slippage | Fixed/swap |
| Best realistic | 0.85% (Wood tier 0.95% net with 10% referral discount) | 0.02% | 0.02% | 0.0005 SOL ($0.06) |
| Normal (PRIMARY) | 0.95% (Wood tier, net of 0.05% SOL cashback) | 0.05% | 0.05% | 0.002 SOL ($0.23) |
| Conservative | 1.00% (cashback not counted) | 0.10% | 0.10% | 0.004 SOL ($0.47) |
| Harsh | 1.00% | 0.30% | 0.25% | 0.01 SOL ($1.17) |
Comparison only: Coinbase Advanced US entry tier (0.90% taker; 0.50% maker) + 0.05% slippage. Zero-cost also reported.
Fixed costs scale with position size; selection uses a $250 position (50% of $500).

## Data / splits (same as previous study)
Development: Binance BTC/USDT 2018-03..2024 (1-minute -> resampled, with volume). Walk-forward: expanding train,
test years 2020..2024. Holdouts, evaluated once: H1 Binance 2025-01..2026-09-09; H2 Bitstamp 2014-2017.
DISCLOSURE: both holdouts were used in the previous study, where the BASE 15m RSI(2)<10 strategy was evaluated
on them (pre-cost PF 1.15 / 1.33; after costs -93%). Filter variants have never touched them. There is no
newer historical data; genuinely untouched evidence can only come from forward paper trading.

## Timeframes: 15m, 30m, 1H, 2H (requested) + 4H, 1D (higher timeframes, pre-registered extension).

## Strategy grid (fixed in advance)
Base (per timeframe): uptrend = close > EMA200 and EMA50 > EMA200; entry when RSI(2) < 10 at close; enter next open;
protective stop 3 ATR(14); one position at a time.
Exit variants (2): X1 close > SMA5 or 10 bars (original); X2 close > SMA20 or 20 bars (bigger target).
Single-filter variants, ONE filter at a time, 2 fixed values each (14 variants + unfiltered base):
- F1 higher-timeframe trend: prior daily close > daily SMA{100, 200}
- F2 volatility floor: ATR%(14) >= trailing-500-bar median x {1.0, 1.25}
- F3 distance from MA: (SMA20 - close) >= {1.5, 2.5} x ATR
- F4 minimum expected move vs fees: (SMA20 - close)/close >= {1, 2} x normal round-trip cost (2.2%)
- F5 volume confirmation: volume >= {1.5, 2.0} x 20-bar average
- F6 RSI regime: RSI(14) >= {40, 50}
- F7 volatility ceiling (avoid crash regimes): ATR% <= trailing-500-bar {90th, 75th} percentile
= 15 filter settings x 2 exits = 30 configs per timeframe per side, 180 per side.
Stage 2 (pairs): for each timeframe, the two single filters with the best DEV walk-forward result may be combined
(one pair per timeframe per exit). No triples.

## Selection (walk-forward, PRIMARY costs, long side)
Eligible in training window: >= 30 trades and PF > 1. Score = t-stat of net % return per trade. Highest score wins.
## Viability gate for the high-win-rate concept (walk-forward OOS 2020-2024, primary costs)
net expectancy > 0 AND net win rate >= 55% AND >= 10 trades/year. Only candidates passing go to holdouts.
## Replacing Version A (same costs, $500 account, same allocation)
Requires: positive net expectancy on BOTH holdouts, higher Sharpe than Version A on both, and a max drawdown no worse.
Otherwise Version A remains the baseline. No parameter changes after holdouts. No cost assumptions lowered.
## $500 account; 25/50/75/100% of available cash per signal; $10 minimum order; positions never exceed cash.

## Outcome (recorded 2026-09-24T02:50:27Z); nothing changed after results
- Walk-forward: NO configuration (180 single-filter long configs + in-fold pairs, 6 timeframes) was ever eligible
  (>=30 training trades with PF > 1 after primary Axiom costs) in any fold. Viability gate: FAILED.
- Dev 2018-03..2024: 2 of 180 long configs had PF > 1 after Axiom normal costs; both 1D + RSI14>=50 (15 trades, 2.2/yr).
  With 180 configs tested, 1-2 positive results are expected by chance; it also fails the >=10 trades/yr requirement.
- Pre-cost the concept is real on every timeframe (68-75% win rate) but its edge is +0.05% (15m) to +0.55% (1D) per trade
  versus ~2.2-2.5% round-trip cost on Axiom.
- Per protocol, no pullback candidate proceeds to the holdouts. Version A remains the baseline, but Version A is also not
  viable on Axiom costs (dev PF 0.95, H1 PF 0.20, H2 PF 1.10).
