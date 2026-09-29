# Daily / 2d / 3d study: conclusions

The protocol, `DAILY_STRATEGY_PROTOCOL.md`, was committed in `1fdfb42` **before** this run. Full generated results are in `REPORT.md`, `strategy_summary.csv` and `train_grid_results.csv`.

## Verdict

**0 of 30 train-selected candidates passed.** They come from 312 evaluated configurations: 52 parameter sets × {1d, 2d, 3d} × {taker, maker}. Nothing is marginal. Per the protocol:
- **no strategy is implemented;**
- **no paper session is started;**
- Version A is untouched.

## Why everything failed

1. **OOS collapse.** The OOS window runs from 2025-04 to 2026-09, when BTC buy-and-hold returned about −4% with a 53% drawdown.
   - 19 of 23 candidates had OOS PF < 1.25, and 15 had OOS expectancy ≤ 0.
   - Only 2 reached OOS PF ≥ 1.5, and both on 2 and 5 OOS trades. One of those two had also failed validation.
2. **Walk-forward looks good, but it is driven by the same few periods.** 19 of 23 candidates had walk-forward PF ≥ 1.5. However:
   - 18 of 23 made more than 50% of their full-history net profit in **one year**, 2021 for most;
   - the **top 3 trades** accounted for 69–188% of net profit;
   - that is trend-following's usual "few big winners" profile. With 20–60 trades in ~10 years, it can't be told apart from luck.
3. **Drawdown at the operating risk.**
   - At 15% risk per trade, cash-capped (effectively fully invested whenever in a trade), the $200 simulation's max drawdown was **40–66%**. 13 candidates exceeded the 50% limit.
   - At 1% risk, drawdowns were small (≤ 14%), but returns were small too.
4. **Buy-and-hold dominated on return over the full history.**
   - At 15% risk, $200 grew to $276–$6,297 across candidates, against **$16,834** for buy-and-hold (with an 84% drawdown).
   - The filters mainly cut exposure and drawdown. They didn't add return.
   - In the flat OOS window, most candidates still lost money. The best, maker `regime_trend` 1d, ended at $262 against $192 for buy-and-hold, on 2 trades.
5. **Maker vs taker changed little.** Daily holding periods make fees a small part of the problem:
   - PF before costs vs after costs was about 5 → 4 for the trend families;
   - the maker case lifted full-history PF only modestly;
   - it did not rescue OOS.
   - The maker model missed only 0–9% of entries, because a daily bar almost always trades 0.10% below the prior close. That is an OHLC approximation, and real queue-dependent fill rates are unknown.
6. **Small samples.** Pullback and hybrid on 2d/3d bars had too few training trades (< 15) to be selected at all.

## What this does and doesn't show

- It does **not** show that daily trend filters are useless. Their in-sample and walk-forward PFs after costs are high, and they avoided most of the 2018 and 2022 bear markets.
- It does show that, measured as **trade-level alpha with a hard OOS test**, no candidate is robust:
  - the edge is concentrated in a handful of 2017/2021/2024 trend trades;
  - it didn't show up in the most recent 18 months;
  - at 15% risk, drawdowns exceed the pre-set limit.
- None of this is evidence of profitability after costs that would justify paper trading under the protocol.

## Suggested next research direction (would need its own pre-registration)

1. **Reframe the goal as risk-managed exposure, not trade alpha.** Test a low-turnover exposure rule, e.g. "hold BTC only while close > SMA(100/200)", as a portfolio overlay judged against buy-and-hold on risk-adjusted terms: Sharpe, MAR, max drawdown and time underwater. The daily study hints that this is where any value lies. Its trade-level PF test is the wrong yardstick for a strategy that trades only 3–6 times a year.
2. **Pre-register the operating risk level separately.** 15% risk per trade on a 3–5 ATR daily stop is effectively all-in, and gave 40–66% drawdowns. A study of how drawdown scales with 2–10% risk (or fractional exposure) should precede any paper test.
3. **Use the only clean test left.** Every historical window has now been viewed, so more historical searching mostly adds multiple-testing risk. If a rule is pre-registered, the defensible next step is a forward, clock-time paper test with a pre-stated evaluation date. This requires a rule that has passed its own pre-registered criteria first. Nothing from this study qualifies.
4. **Don't return to 5m–6h** at the 0.50%/0.90% Intro tier. Three studies now agree that costs dominate there.
