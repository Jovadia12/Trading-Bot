# EMA trend + BOS + Fibonacci + FVG ("Unicorn"): objective rules for the 5m/15m backtest

Written 2026-10-02, **before** the strategy was run on real data. Research only:
- the paper runner, `multi_crypto_momentum` and the running paper session are untouched;
- code: `backtest/fib_fvg.py` (rules and engine), `backtest/fib_fvg_study.py` (runner and report);
- tests: `tests/test_fib_fvg.py`.

**Source.** The video (youtube.com/watch?v=FrXfO4on4uU) could not be opened: the research environment blocks external sites. These rules implement the user's written specification. Every point where that spec is discretionary is converted into a fixed rule below, under **Assumption**.

## Data and timeframes
- **Data:** Coinbase spot `<COIN>-USD` 5m candles (`research_data/coinbase_<coin>usd_5m.csv.gz`).
- **15m bars** are built from complete groups of three 5m bars, UTC-aligned. A 15m bar starting at T is used only from the 5m bar that **opens at T+15m**.
- **Window:** the most recent 365 days common to all available coins, plus 7 days of earlier data for indicator warm-up only.
- **Missing 5m bars** become flat bars (open = high = low = close = previous close, volume 0), and their count is reported.

## Indicators (5m)
- **EMAs:** EMA20, EMA50, EMA200 of the close (standard EMA, `adjust=False`).
- **ATR14:** Wilder's ATR(14).
- **Long trend:** EMA20 > EMA50 > EMA200 **and** close > EMA200. Short trend mirrored. Trend is off for the first 200 bars.

## Structure
- **Swing high (5m)** at bar *i*: high[i] is **strictly** greater than every high in [i−3, i+3].
  - **Assumption:** fractal width k = 3.
  - The swing is **confirmed at the close of bar i+3** and only usable from then on. Swing low mirrored.
- **Bullish break of structure (BOS)** at bar *t*: close[t] > the most recent **confirmed** swing high. Each swing high can trigger only one BOS. Bearish mirrored.
- **Impulse (bullish):**
  - **L** = the lowest low between the broken swing high and the BOS bar (where the breaking leg starts).
  - **H** = the highest high from L up to the latest completed bar.
  - H keeps extending while price makes new highs, and the zone re-anchors from the next bar.
  - **Assumption:** the impulse is defined this way because the spec doesn't say which swing points anchor it.
- **Assumption, minimum impulse:** H − L ≥ **3 × ATR14** at the trigger bar. Micro-swings (often under 0.4% with a zone a few dollars wide) are ignored, as a discretionary trader would.

## Fibonacci and FVG
- **Fib band (bullish):** [H − 0.618·(H−L), H − 0.382·(H−L)]. Bearish: [L + 0.382·(H−L), L + 0.618·(H−L)].
- **FVG** (standard three candles, indexed by the third candle *j* and known at its close):
  - bullish if high[j−2] < low[j], zone [high[j−2], low[j]];
  - bearish if low[j−2] > high[j], zone [high[j], low[j−2]].
- **Which FVG counts:**
  - it must have formed inside the impulse, i.e. its first candle comes after L (bullish) or after H (bearish);
  - it dies once a close goes through it: below its low for a bullish FVG, above its high for a bearish one;
  - **Assumption:** the **most recent** live FVG that overlaps the Fib band is used.
- **Confluence zone Z** = the overlap of that FVG with the Fib band: [max(lows), min(highs)]. It must have positive width.

## Entry (all checked on the completed 5m bar *t*; fill at the open of *t+1*)
1. Trend confirmed at *t*.
2. A BOS created the setup, *t* is after the BOS bar and after the last impulse extension, and the setup is ≤ 288 bars (24 h) old.
   - **Assumption:** setups expire after 24 h.
   - A newer BOS on the same side replaces the setup.
   - A close beyond the impulse origin (below L for longs, above H for shorts) cancels it.
3. Retracement into the band: price touches Z, which lies inside the 38.2–61.8% band.
4. FVG overlap: Z exists.
5. **Reaction** (**Assumption**, the spec's "price reacts"):
   - long: low[t] ≤ Z_high **and** close[t] > open[t] **and** close[t] > midpoint(Z);
   - short mirrored: high[t] ≥ Z_low **and** close[t] < open[t] **and** close[t] < midpoint(Z).
6. **Unicorn version** only: EMA200[t] lies within [Z_low − 0.25·ATR14, Z_high + 0.25·ATR14].
   - **Assumption:** the "small tolerance" is 0.25 × ATR14.
7. One trade per setup and **one position per coin**. Signals arriving while a position is open are ignored.

## Stops
- **Structural:**
  - long: min(FVG low, signal-bar low) − 0.1·ATR14;
  - short: max(FVG high, signal-bar high) + 0.1·ATR14;
  - **Assumption:** the buffer is 0.1 × ATR. The far side of the FVG is used rather than the impulse origin, which would be a 100% retracement.
- **ATR variants:** the entry price ∓ k × ATR14 at the signal bar, for k = 1.5, 2 and 2.5.
- **1R** = |entry − initial stop|. A trade whose stop is on the wrong side of the entry price is skipped.

## Exits (managed on 15m; fills on 5m)
- **A:**
  - exit at the next 5m open after a 15m bar **completed after entry** shows the opposite condition;
  - for a long that means 15m EMA20 < EMA50, **or** a 15m close below the last confirmed 15m swing low (k = 3); shorts mirrored;
  - the initial stop stays active.
- **B:**
  - trailing structural stop at the latest confirmed 15m swing low − 0.1·ATR14(15m) for longs (mirrored for shorts);
  - it only uses 15m swings confirmed after entry and only ever tightens;
  - it is checked intrabar on 5m.
- **C / D:** fixed take-profit at 3R / 5R, plus the initial stop.
- **All exits:**
  - stops are stop-market orders: a 5m bar opening beyond the stop fills at the open;
  - if the stop and the target fall in the same 5m bar, **the stop is assumed first**;
  - a target fills only if price trades **through** it;
  - trades still open at a window boundary are closed at that bar's open.

## Execution, sizing, costs
- **Sizing:**
  - completed candles only; entry at the next 5m open;
  - **10% of current equity** per entry (so 10 coins × 10% ≤ 100%), 1x, cash-capped, no leverage or borrowing;
  - shorts are paper shorts on spot prices with 1x cash collateral;
  - **Assumption:** the spec gives no sizing, so the existing 10%-per-coin convention is used.
- **Cost cases:**
  - **coinbase_taker:** 0.90% per side (your Coinbase Intro tier) + 0.005% half-spread + 0.02% slippage, + 0.05% extra on stops.
  - **coinbase_maker_like:**
    - entries and fixed targets at 0.50% maker, assuming the limit fills at the next open (**optimistic: no missed fills**);
    - stops and signal/trailing exits stay taker 0.90% + slippage.
  - **low_fee_venue_reference:** 0.02% maker / 0.05% taker. A typical perp-exchange base tier, **for reference only, not your account**.
  - **zero_cost_diagnostic:** shows the edge before costs. Never used for selection.

## Validation (no optimisation on the evaluation data)
1. **Grid:** 2 versions × 4 stops × 4 exits = **32 fixed variants**. No parameter inside a variant is tuned.
2. **Train:** the first 70% of the 12 months.
3. **Selection, per real cost case:** the variant with the highest **train** profit factor among those with ≥ 20 train trades; ties go to the higher train average trade.
4. **Out-of-sample:** the last 30%, evaluated **once** for the selected variant.
5. **Full 12 months:** the same selected variant, reported separately.
6. **Also reported:**
   - all 32 variants, for transparency only, not for re-selection;
   - `multi_crypto_momentum` (daily data, same dates);
   - BTC buy-and-hold.
