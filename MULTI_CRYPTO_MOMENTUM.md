# `multi_crypto_momentum`: rules, implementation and how to run it

Written 2026-09-30 and committed **before** any backtest result exists. The rules are the user's specification, implemented exactly. The parameters are fixed and will **not** be optimised after seeing results. This is a separate strategy:
- the paper strategy **Version A** and all earlier studies are untouched;
- **PAPER ONLY**: no code path in this project can place a live order.

## Rules (exact)

| | |
|---|---|
| **Universe** | BTC, ETH, SOL, XRP, BNB, DOGE, LINK, ADA, AVAX, DOT |
| **Timeframe** | daily (UTC candles) |
| **Long signal** | 40-day return > +5% **and** close > EMA200 |
| **Short signal** | 40-day return < −5% **and** close < EMA200 |
| **BTC regime filter** (alts only; BTC itself is not filtered) | alt longs only if BTC close > BTC EMA200; alt shorts only if BTC close < BTC EMA200 |
| **Exit long** | 40-day return crosses below 0% **or** close crosses below EMA200 |
| **Exit short** | 40-day return crosses above 0% **or** close crosses above EMA200 |
| **Timing** | signal on a **completed** daily candle; fill at the **next available** candle's open |
| **Allocation** | max **10%** of current equity per coin; max **100%** gross exposure; unused capital stays in cash; 1x; no leverage, no borrowing, no liquidation modelling |
| **Costs** | **0.05% fee per side + 0.02% slippage per side**. Configurable: `--fee`, `--slippage` |

## Definitions and interpretation choices

These are fixed here because the specification leaves them open.

- **40-day return:** `close[t] / close[t−40] − 1`, counted in daily candles of that coin.
- **EMA200:** the standard EMA (span 200, `adjust=False`), treated as **invalid until 200 candles exist**. No signals or exits are generated before then.
- **Strict inequalities:**
  - long needs `ret > 0.05`; short needs `ret < −0.05`;
  - exits use `ret < 0` / `ret > 0` and `close < EMA` / `close > EMA`.
- **"Crosses" = level test while holding.** An exit is the level condition evaluated at each completed close while a position is open. Entries require the opposite side (e.g. a long needs ret > +5% and close > EMA), so the first close meeting the exit condition *is* the crossing.
- **BTC regime at an alt's date d** uses BTC's latest completed candle ≤ d. It's forward-filled, never back-filled. Alts are blocked until BTC's EMA200 is valid.
- **Entries are state-based.** Every day a flat coin whose signal holds is an entry candidate, so a signal rejected for capacity is retried the next day if it still holds.
- **Reversal:** if a held position's exit and an opposite-side signal occur on the same close, the exit fills first at the next open, then the new side is entered at the same open, subject to the caps.
- **Order of execution at each open:**
  1. **exits** first;
  2. **entries** sorted by **|40-day return| descending**, ties broken by universe order (BTC, ETH, SOL, XRP, BNB, DOGE, LINK, ADA, AVAX, DOT).
- **Entry size:** each entry gets `min(10% × equity, 100% × equity − current gross exposure, cash / (1 + fee))`.
  - Equity and exposure are marked at the latest prices.
  - If that is below $1, the signal is **rejected** with the binding reason: exposure cap or cash.
  - If it's positive but below 10%, the entry gets the remaining capacity and is flagged `capped`.
- **Caps apply at entry.** Positions are **not rebalanced** afterwards, so a winning position can drift above 10%.
- **Short accounting:** shorts are paper shorts on spot prices with **1x cash collateral**.
  - Opening locks the notional, plus the fee, from cash.
  - The position's value is `collateral + qty × (entry − price)`.
  - A short whose loss exceeds its collateral is counted and reported (`short_collateral_breach_marks`), not liquidated.
- **Slippage** is adverse on every fill: buys fill at `ref × (1 + s)`, sells at `ref × (1 − s)`. Fees are charged on notional.

## Backtest (`backtest/mcm_backtest.py`)

```bash
PAPER_MODE=true python3 -m backtest.mcm_backtest --data research_data/crypto_data.zip
```

- **Data:** `crypto_data.zip` (daily **spot** OHLC for the 10 coins).
  - The loader accepts either one CSV per coin, with the coin taken from the file name (`BTC.csv`, `BTC-USD.csv`, `btcusdt_1d.csv`, …), or CSVs with a symbol column.
  - Timestamps may be dates, ISO strings, or epoch seconds/milliseconds.
  - It **refuses** duplicate coins, non-daily rows, or missing BTC, rather than guessing. Missing coins are excluded and reported, never substituted.
- **Label:** every output says **"DAILY SPOT OHLC used as a PROXY for perpetual trading (no funding, no perp basis, no order book)"**. Perpetual funding payments are **not** modelled.
- **Full history:** from $200; open positions are closed at the final close so trade statistics are complete.
- **OOS (project convention):** the last 15% of the chronological span, as a separate run with a flat start and its own $200. Only signals from closes inside OOS are acted on. Indicators are computed on the full history (they only use the past).
- **Reported:**
  - total return, ending balance, annualised return, max drawdown, Sharpe (daily), profit factor, win rate, trades, average trade, fees, exposure, longest losing streak;
  - results by coin, by year, and long vs short;
  - OOS return, PF and max drawdown;
  - the equity curve (CSV + SVG);
  - benchmarks: **BTC buy-and-hold**, and **equal-weight buy-and-hold** ($20 per coin, bought at each coin's first available open; cash until then).

## Paper session (`paper_trading/mcm_runner.py`)

```bash
PAPER_MODE=true python3 -m paper_trading.mcm_runner --duration 604800   # ~7 days, $200, 10%/100% caps
```

- **Market data:** Coinbase Advanced **public, read-only REST** (daily candles), through the project's allowlisted transport.
  - GET only; order paths are refused before any network I/O.
  - **No credentials are used.**
- **Products:** each coin is looked up as the Coinbase **spot** product `<COIN>-USD`, labelled as a **price proxy for perpetual trading**.
  - The existing read-only infrastructure has no perpetual-futures product endpoints allowlisted, and no perp product IDs have been verified for this account.
  - A coin whose product is missing, offline or trading-disabled is **disabled and reported; nothing is substituted**.
  - If Coinbase can't be reached at all, symbols are reported as "could not be checked", not as unlisted.
  - If BTC is unavailable, every alt is disabled, because the regime filter can't be evaluated.
- **Same engine as the backtest** (`strategy/multi_crypto_momentum.py`):
  - at each 00:00 UTC boundary, once the new daily candles exist (it waits up to 30 minutes for every coin), the **just-completed** candle is evaluated;
  - paper fills happen at the **new candle's open**;
  - **no trade is taken at startup**, because the current candle opened before the session began. Signals present at startup are listed as "not traded".
- **Startup report prints:**
  - strategy, universe, allocation, fees, starting balance, available/unavailable symbols;
  - `PAPER MODE: ENABLED`, `order_endpoint_called: NO`, `paper orders: 0 | live orders: 0`, `starting equity: $200.00`.
- **Final report** (on duration end or Ctrl+C):
  - starting/ending equity, P&L, return, max drawdown;
  - trades by coin, winning/losing trades, fees, current positions;
  - signals generated and rejected, with reasons;
  - market-data messages, connection errors;
  - the order-endpoint confirmation.
- **Records** go to `paper_trading/records/mcm_<UTC timestamp>/` (git-ignored):
  - `state.json`, rewritten every poll;
  - `final_report.json`.
- A restart begins a fresh session.

## Caveats that apply to any result

1. **Fees.** 0.05% per side resembles perpetual-futures taker fees. Your Coinbase **spot** Intro tier is **0.50% maker / 0.90% taker**. At those fees results would differ materially; re-run with `--fee 0.009` to see the effect.
2. **No real spot shorts.** Shorts can't be executed on a Coinbase spot account. In the backtest and paper session they are simulated on spot prices.
3. **Proxy data.** Spot data is used as a proxy for perps: funding, basis and perp-specific liquidity are absent.
4. **Scale of the paper test.** A 7-day paper session covers about **7 daily decisions**. It is an integration test, not evidence of profitability.
