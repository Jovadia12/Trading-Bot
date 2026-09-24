# Research Audit: BTC Spot RSI(2) Pullback Study and Version A Under Axiom Costs

Audit date: 2026-09-24
Scope: every file in this repository at commit `2784691` (the initial "Add BTC trading research" commit), including all 16 entries in `pullback_study.zip`.
Stance: the existing research is treated as evidence to audit, not as ground truth. Nothing in this audit changes the preregistered rules, re-runs anything against the holdouts, or builds execution code.

---

## 0. Inventory: what was actually provided

| File | What it is | Notes |
|---|---|---|
| `PULLBACK_PREREGISTRATION.md` | Protocol plus an appended "Outcome" section | Byte-identical to `pullback/PREREGISTRATION.md` in the ZIP |
| `candidates_dev_by_cost.csv` | 9 hand-picked long configs x 7 cost scenarios, dev period only | Identical to the ZIP copy |
| `accounts_500usd.csv` | $500 cash-account simulations (dev for pullback; dev/H1/H2 for Version A; buy & hold) | Identical to the ZIP copy |
| `versionA_axiom.csv` | Version A per-trade metrics on dev, H1 and H2 under 4 cost scenarios | Identical to the ZIP copy |
| `dev_landscape.csv` | All 360 single-filter configs (180 long, 180 short) on dev, pre- and post-cost | Identical to the ZIP copy |
| `pullback_study.zip` → `README.md` | Run instructions | |
| ZIP → `build.py` | Resamples 1-minute CSVs to 15m/30m/1h/2h/4h/1D pickles | Reads `/home/claude/data/m1/...`, which isn't included |
| ZIP → `plab.py` | Features, filters, cost model, metrics, $500 account simulator | Imports `simulate, ema, rsi, atr` from `/home/claude/spotlab/lab.py`, which isn't included |
| ZIP → `run_wf.py` | Walk-forward selection (folds 2020–2024) | |
| ZIP → `diag.py` | Rebuilds the trade store and writes `dev_landscape.csv` | |
| ZIP → `report.py` | Candidate tables, accounts, Version A on dev/H1/H2, regimes, shorts | Imports `lab.VERSION_A`, `lab.run_config`, `lab.indicators`, which aren't included |
| ZIP → `results/walkforward_selections.csv` | Walk-forward selections | **Every `selected` cell is empty** |
| ZIP → `results/regimes_dev.csv` | Bull/transition/bear split for 3 base configs (dev) | Only inside the ZIP |
| ZIP → `results/shorts_research.csv` | Short-side base configs (research only, dev) | Only inside the ZIP |

**Missing, but referenced by the provided files:**
1. The raw 1-minute data (Binance BTC/USDT, Bitstamp BTC/USD).
2. `spotlab/lab.py`: the trade simulator (fill logic, stop handling), the indicator code, and the **definition of Version A**.
3. The "report" containing the fee sources ("verified 2026-09-24; see sources in report").
4. The previous study, which defined Version A, first used both holdouts, and produced the "-93% after costs" figure.
5. `results/walkforward_oos.pkl`, `walkforward_oos_metrics.csv` and `store.pkl` (see §10.3 for why the first two could never have been produced).

**Consequence:** none of the numbers can be reproduced from this repository. Everything below audits internal consistency, the code logic that is visible, and the reported outputs.

---

## 1. Research overview

The study asks whether a high-win-rate RSI(2) pullback strategy ("buy short-term oversold dips inside an uptrend") can be made to survive real execution costs on the intended venue. The venue is **Axiom**, a Solana swap terminal where BTC exposure means swapping into cbBTC.

The approach is to trade less often and target larger moves. The study took one base rule and applied one filter at a time (7 filter families, 2 fixed values each), 2 exit variants and 6 timeframes. Selection was by expanding-window walk-forward under the "normal" Axiom cost model. A viability gate had to be passed before any candidate could touch the holdouts.

The study also re-costed the prior baseline strategy, **Version A**, under the Axiom cost model on dev and both holdouts.

**Headline outcome (as reported, and consistent with every file):** under Axiom costs of about 2.2–2.3% per round trip, nothing is viable. No pullback configuration was ever eligible in any walk-forward fold. Version A also loses money after Axiom costs on dev (PF 0.95) and on H1 (PF 0.20), and only breaks even on H2 (PF 1.10).

---

## 2. Data sources (Q1)

| Role | Source | Instrument | Span | Origin |
|---|---|---|---|---|
| Development + walk-forward | Binance | BTC/USDT spot | 2018-03-01 → 2024-12-31 | 1-minute OHLCV resampled (`build.py`) |
| Holdout H1 | Binance | BTC/USDT spot | 2025-01-01 → 2026-09-09 (code end is exclusive at 2026-09-10) | same |
| Holdout H2 | Bitstamp | BTC/USD spot | 2014-01-01 → 2017-12-31 | same |

- Resampling uses left-labelled, left-closed UTC bars, and empty bars are dropped (`dropna`). A daily bar is 00:00–24:00 UTC.
- Duplicate timestamps are dropped when the 1-minute files are merged. No other data cleaning (gap handling, bad-tick filtering) is visible.
- Binance BTC/USDT spot began in Aug 2017. The 2018-03 dev start matches the need for about 200 daily bars before the daily SMA200 (used by filter F1 and by the `valid` mask) exists.
- Venue mismatch: none of this data comes from the intended execution venue (cbBTC pools on Solana via Axiom). The price series is a proxy.

---

## 3. Periods (Q2)

| Period | Dates | Used for |
|---|---|---|
| Dev | 2018-03 → 2024-12 (6.83–6.84 years; both constants appear in the code) | Landscape, candidate tables, $500 accounts, regimes, shorts |
| Walk-forward | Expanding training window starting 2018-03-01; test years 2020, 2021, 2022, 2023, 2024 | Selection plus the viability gate |
| H1 | Binance 2025-01 → 2026-09-09 | Supposed to be evaluated once. **In this study it was used only for Version A** |
| H2 | Bitstamp 2014 → 2017 | Same as H1 |

---

## 4. Exact strategy definitions (Q3, Q4, Q8)

### 4.1 The high-win-rate pullback strategy (base)

Everything is evaluated at bar close on the chosen timeframe (15m, 30m, 1h, 2h, 4h, 1D):

- **Trend condition:** `close > EMA200` **and** `EMA50 > EMA200`
- **Entry signal:** `RSI(2) < 10` at the close, with the trend condition true
- **Entry fill:** next bar's open. This is stated in the prereg; the fill code lives in the missing `lab.simulate`.
- **Protective stop:** 3 x ATR(14) from entry. The code comment says "worst-case fills", which can't be verified.
- **Exits** (whichever comes first, together with the stop):
  - **X1:** `close > SMA5`, or 10 bars elapsed
  - **X2:** `close > SMA20`, or 20 bars elapsed
- One position at a time, long only, spot, no leverage.
- **Validity mask:** EMA200, the ATR% 90th percentile, the daily SMA200 and the 20-bar volume average must all exist.

**Short research mirror (information only):** `close < EMA200`, `EMA50 < EMA200`, `RSI(2) > 90`, exits on `close < SMA5/SMA20`. Shorts are not tradable on a cash-only spot account.

### 4.2 Single filters (one at a time; values fixed in advance)

| ID | Rule (long) | Values |
|---|---|---|
| F1 | Previous *closed* daily close > daily SMA{n} | 100, 200 |
| F2 | ATR%(14) ≥ k x trailing-500-bar median ATR% | 1.0, 1.25 |
| F3 | (SMA20 − close) ≥ k x ATR | 1.5, 2.5 |
| F4 | (SMA20 − close)/close ≥ k x 2.2% | 1, 2 |
| F5 | Volume ≥ k x 20-bar average volume | 1.5, 2.0 |
| F6 | RSI(14) ≥ v | 40, 50 |
| F7 | ATR% ≤ trailing-500-bar {90th, 75th} percentile | 90, 75 |

Base plus 14 filter settings gives 15, times 2 exits gives **30 configs per timeframe**, so **180 long + 180 short = 360** configs. This matches the 360 rows of `dev_landscape.csv`.

**Stage 2 (pairs):** per timeframe and exit, combine the two best single filters from different families, ranked on the training window. **It never ran**, because no single filter was ever eligible (§7).

### 4.3 Selection rule (walk-forward)

- Cost scenario: `axiom_normal`, with a $250 notional (50% of a $500 account).
- Eligible in the training window: at least 30 trades **and** net PF > 1.
- Score: t-statistic of net per-trade return. The highest score is selected and then traded in the following calendar year.

### 4.4 Viability gate (for any candidate to reach the holdouts)

Over walk-forward OOS 2020–2024 at primary costs: net expectancy > 0, **and** net win rate ≥ 55%, **and** at least 10 trades per year.

### 4.5 Rule for replacing Version A

A candidate must show positive net expectancy on both holdouts, a higher Sharpe than Version A on both, and a max drawdown no worse than Version A's. No parameter changes are allowed after the holdouts, and cost assumptions may not be lowered.

### 4.6 Version A (Q7)

**The rules of Version A aren't in any provided file.** It is `lab.VERSION_A` in the missing `spotlab/lab.py`, carried over from the previous study. From the outputs it can be described but not defined:

- It is labelled "Version A (4H)", so it runs on 4-hour bars.
- About 20 trades per year on dev (136 trades in 6.84 years), 19.5 per year on H1 and 25 per year on H2.
- Pre-cost: win rate 36–48%, average win about 2–3.3x the average loss, average hold 54–83 hours.

That profile (low win rate, large winners, multi-day holds) looks like **trend-following or breakout**, not mean reversion. It is the incumbent "baseline" that the pullback study was meant to replace.

**Unresolved:** it can't be established from this repository whether Version A was selected on the same 2018–2024 Binance dev data. If it was, its dev numbers are in-sample.

---

## 5. Execution-cost assumptions (Q5)

The cost model is in `plab.py` (`COSTS`, `net()`):

- The platform fee is multiplicative on both sides.
- Pool fee plus slippage adjust the price against you on both sides.
- A fixed network cost (priority fee + Jito tip, SOL valued at $117) is charged twice and divided by notional.

| Scenario | Platform fee/side | Pool fee/side | Slippage/side | Fixed/swap | **Round trip at $250** (computed from the code) |
|---|---|---|---|---|---|
| zero | 0 | 0 | 0 | 0 | 0 |
| axiom_best | 0.85% | 0.02% | 0.02% | 0.0005 SOL ($0.06) | **1.82%** |
| **axiom_normal (PRIMARY)** | 0.95% | 0.05% | 0.05% | 0.002 SOL ($0.23) | **2.27%** (2.46% at $125, 2.18% at $500) |
| axiom_conservative | 1.00% | 0.10% | 0.10% | 0.004 SOL ($0.47) | **2.76%** |
| axiom_harsh | 1.00% | 0.30% | 0.25% | 0.01 SOL ($1.17) | **4.00%** |
| coinbase_taker (comparison) | 0.90% | – | 0.05% | 0 | **1.89%** |
| coinbase_maker_entry (comparison) | 0.50% entry (maker) / 0.90% exit (taker) | – | 0.05% on exit only | 0 | **1.45%** |

Audit notes on costs:
- **The fee levels can't be verified here.** The prereg cites a "report" with sources that isn't included. The Axiom tier fees (0.95% "Wood tier", cashback and referral) and the Coinbase Advanced fees (0.90% taker, 0.50% maker) should be checked against the current official fee pages before anything relies on them.
- Every scenario that could be verified is dominated by the **platform fee**. Slippage and pool assumptions barely matter by comparison. This is why the conclusion is robust: see §9.
- `ROUND_TRIP_NORMAL = 0.022`, used by filter F4, is slightly below the 2.27% the model actually charges at $250. This is minor, but it means F4 is marginally looser than its label.
- The `coinbase_maker_entry` scenario assumes every limit order fills at the next open with no adverse selection or missed fills. That is optimistic.
- A $500 account and $125–$500 positions make the fixed SOL costs material (0.1–0.4% per round trip).

---

## 6. What the Axiom research concluded (Q6)

From the prereg's Outcome section, checked against the CSVs:

| Claim | Checked against files | Verdict |
|---|---|---|
| No config was eligible (≥30 training trades and PF > 1 at primary costs) in any fold | `walkforward_selections.csv`: all 70 rows (2 sides x 5 folds x 7 scopes) have an empty `selected` | **Confirmed** |
| Viability gate FAILED | Follows from the above: there was no OOS series at all | **Confirmed** (vacuously; see §10.3) |
| 2 of 180 long configs had PF > 1 on dev after normal costs, both 1D + RSI14 ≥ 50, 15 trades, 2.2/yr | `dev_landscape.csv`: rows 312 (X1, PF 2.11) and 327 (X2, PF 2.31), 15 trades each; 0 short configs with PF > 1; 0 configs with ≥30 trades and PF > 1 | **Confirmed** |
| Pre-cost win rate is 68–75% on every timeframe | Long base configs: 67.8–75.0% | **Confirmed** |
| Pre-cost edge is +0.05% (15m) to +0.55% (1D) per trade | Base expectancy at zero cost: 0.05–0.06% (15m), 0.52–0.55% (1D) | **Confirmed** |
| "Pre-cost the concept is real on every timeframe" | t-stats at zero cost: 15m 5.27, 30m 3.52, 1h 2.26, **2h 1.76, 4h 1.45, 1D 0.48** | **Overstated.** It is statistically distinguishable from zero only on 15m–1h. On 2h, 4h and 1D a positive pre-cost mean isn't significant |
| Version A isn't viable on Axiom costs (dev PF 0.95, H1 0.20, H2 1.10) | `versionA_axiom.csv`: 0.950 / 0.202 / 1.102 | **Confirmed** |
| Version A remains the baseline | Procedurally true (nothing beat it), but the baseline itself loses money on Axiom | **Accurate, but a misleading word:** there's no viable baseline at these costs |

**Bottom line of the Axiom research:** at about 2.2–2.3% per round trip, neither the pullback family nor Version A has positive expected value net of costs on the evidence available. The pre-cost edge of the pullback idea is 4x (1D) to about 40x (15m) smaller than the round-trip cost.

---

## 7. Validation methodology (and what actually happened)

1. **Dev landscape (`diag.py`):** all 360 configs are evaluated over the full dev period. This is descriptive and **entirely in-sample**.
2. **Walk-forward (`run_wf.py`):** expanding training window from 2018-03 to the end of year Y−1; select by the §4.3 rule; test on year Y; Y = 2020–2024. **Result: zero selections**, so there is no OOS trade series.
   - **Structural point:** with a ≥30-trade eligibility bar and training windows of 22–82 months, the low-frequency 1D configs (about 2–7 trades per year) could hardly ever qualify. The only net-positive config (1D+F6≥50, 2.2 trades per year, 15 trades in total) **could not have been selected in any fold by construction**. That is consistent with the ≥10 trades/yr gate, so it isn't a flaw, but readers should know the walk-forward never really "tested" it.
3. **Viability gate:** never evaluated on data, because nothing was selected.
4. **Holdouts:** per protocol, no pullback config was run on H1 or H2 in any reported output. **Version A was run on H1 and H2** (`report.py` lines 20–33).
5. **Post-hoc candidate tables (`report.py`):** besides the 6 base configs, three configs were **hand-picked after seeing the dev landscape**: 1D+F6≥50 X2, 4H+F4(2x) X2 and 1D+F1(SMA100) X1. They are labelled descriptively and never advanced to the holdouts, so this doesn't violate the protocol. But they are best-of-180 in-sample picks and should be read that way.

---

## 8. Results

### 8.1 Pullback base, long, dev 2018-03..2024 (`candidates_dev_by_cost.csv`, exit X2)

| TF | Trades | /yr | Win % pre-cost | Expectancy pre-cost | t pre-cost | Win % net (normal) | Expectancy net (normal) | PF net |
|---|---|---|---|---|---|---|---|---|
| 15m | 4412 | 645 | 73.5 | +0.06% | 5.27 | 0.5 | −2.22% | 0.002 |
| 30m | 2169 | 317 | 73.9 | +0.08% | 3.52 | 1.2 | −2.19% | 0.006 |
| 1h | 1104 | 161 | 72.7 | +0.10% | 2.26 | 3.4 | −2.17% | 0.013 |
| 2h | 547 | 80 | 72.0 | +0.17% | 1.76 | 9.3 | −2.11% | 0.053 |
| 4h | 273 | 40 | 71.4 | +0.26% | 1.45 | 19.4 | −2.01% | 0.117 |
| 1D | 48 | 7 | 72.9 | +0.52% | 0.48 | 43.8 | −1.76% | 0.480 |

At zero cost, average losses are about 2.2x average wins (e.g. 15m: +0.38% vs −0.84%). The high win rate is the usual mean-reversion trade-off, not an edge in itself.

On 1D, the top 10% of trades account for **214%** of total pre-cost profit, so the result is fragile.

### 8.2 Best in-sample filtered configs (dev, axiom_normal)

| Config | Trades | /yr | Win % net | Exp net | PF net | t net | Gate status |
|---|---|---|---|---|---|---|---|
| 1D + F6 RSI14≥50, X2 | 15 | 2.2 | 46.7 | +0.92% | 2.31 | 1.22 | Fails win-rate (≥55%) and frequency (≥10/yr); not significant |
| 1D + F6 RSI14≥50, X1 | 15 | 2.2 | 46.7 | +0.65% | 2.11 | – | Same entry signals as X2 (different exit), so not an independent result |
| 4H + F4 ≥2x cost, X2 | 36 | 5.3 | 41.7 | −0.95% | 0.58 | −1.16 | Negative |
| 1D + F1 SMA100, X1 | 42 | 6.1 | 40.5 | −0.86% | 0.54 | −1.30 | Negative |

With 180 long configs tested (and X1/X2 pairs that are highly correlated), one or two nominally positive 15-trade results is what chance alone would produce. **This is not evidence of an edge.**

### 8.3 Regimes (dev, `regimes_dev.csv`)

Pre-cost the pullback is positive in bull and transition regimes on 4h and 1h, and slightly positive even in bear on 1h. Net of Axiom costs it is negative in every regime and timeframe. (1D bear and transition have 2 and 4 trades, which is meaningless.)

### 8.4 Shorts (research only, `shorts_research.csv`)

Pre-cost PF is 1.06–1.19 at every timeframe. Net PF is ≤ 0.51 at every timeframe. Shorts aren't tradable on the target account anyway.

### 8.5 Version A (4H) (`versionA_axiom.csv`)

| Period | Status | Trades | Win % pre | PF pre | t pre | PF Axiom normal | PF Coinbase taker | PF Axiom harsh |
|---|---|---|---|---|---|---|---|---|
| Dev 2018-03..2024 | Probably in-sample (unverifiable) | 136 | 47.8 | 2.72 | 3.33 | **0.95** | 1.11 | 0.52 |
| H1 2025..2026-09 | Previously used holdout | 33 | 36.4 | 1.21 | 0.40 | **0.20** | 0.26 | 0.07 |
| H2 2014–2017 | Previously used holdout | 101 | 46.5 | 2.90 | 3.18 | **1.10** | 1.27 | 0.62 |

The pre-cost edge on H1, the most recent and most relevant regime, is statistically nil (t = 0.40), even before costs.

### 8.6 $500 cash-account simulations (`accounts_500usd.csv`, Axiom normal)

| Strategy / period | 25% alloc | 50% | 75% | 100% | Max DD (100%) |
|---|---|---|---|---|---|
| Pullback 15m–2h base, dev | ≈ −92% | ≈ −96% | ≈ −97% | ≈ −98% | ≈ −98% |
| Pullback 4h base, dev | −86% | −96% | −98% | −98% | −98% |
| Pullback 1D base, dev | −23% | −38% | −52% | −64% | −67% |
| 1D+F6≥50 (in-sample pick), dev | +2.8% | +7.1% | +11.4% | +15.9% | −7.9% |
| Version A, dev | −13% | −16% | −24% | −33% | −61% |
| Version A, H1 | −17% | −30% | −41% | −50% | −52% |
| Version A, H2 | −1% | +4% | +5% | +2% | −63% |
| BTC buy & hold: dev / H1 / H2 | +757% / −17% / +1,739% | | | | −77% / −53% / −81% |

Account-simulation caveats:
- On the losing high-frequency configs, the account runs out of money and most later signals are skipped under the $10 minimum order (e.g. 4,118 of 4,412 15m trades skipped at 25%). The −92% to −98% figures are therefore *floored* by ruin; the true per-trade loss is larger.
- Sharpe ratios near −5 reflect long flat periods after ruin.
- Over dev, Version A paid $1,549 in fees on a $500 account at 100% allocation.

---

## 9. In-sample vs out-of-sample classification (Q9)

| Result | Classification |
|---|---|
| `dev_landscape.csv` (all 360 configs) | **In-sample** (descriptive) |
| `candidates_dev_by_cost.csv` base configs | **In-sample** (not selected, so little selection bias, but not validated) |
| `candidates_dev_by_cost.csv` 1D+F6, 4H+F4, 1D+F1 | **In-sample and selected post hoc**: the most optimistic kind of number |
| `accounts_500usd.csv` pullback rows | **In-sample** |
| `regimes_dev.csv`, `shorts_research.csv` | **In-sample** |
| Walk-forward OOS 2020–2024 | **Does not exist**: nothing was selected |
| Version A, dev | **Probably in-sample.** Version A came from the prior study, which used the same dev split ("same as previous study"); unverifiable without that study |
| Version A, H1 and H2 | **Nominally out-of-sample, but not first-look.** Both holdouts were already used in the previous study, and this study looked at them again under a new cost model |
| Previous study's base 15m result on H1/H2 (pre-cost PF 1.15/1.33; −93% after costs) | Reported in the prereg; **no artifact provided** |

---

## 10. Was any final holdout actually untouched? (Q10)

**No.**

1. **The prereg itself says** both H1 and H2 were used in the previous study, where the base 15m RSI(2)<10 strategy was evaluated on them. Version A was presumably evaluated or validated there too.
2. **This study re-evaluated Version A on H1 and H2** (`report.py`, `versionA_axiom.csv`, `accounts_500usd.csv`). Repricing costs doesn't change the trades, but it is still another look at the same holdout data.
3. **The pullback filter variants** were never *reported* on H1 or H2, so "filter variants have never touched them" holds for the outputs. However, `run_wf.py` and `diag.py` simulate trades on the **entire** Binance series, H1 included, and only window them to dev afterwards. H1 trades for all 360 configs existed in memory and in `store.pkl`. Nothing indicates they were inspected, but the separation is procedural, not physical, and it can't be verified.
4. The prereg's own conclusion is correct and important: **no untouched historical BTC data remains.** The only genuinely clean evidence from here on is forward (paper) data.

Additional point on preregistration integrity:
- The header says "Written 2026-09-24T02:47:43Z, before any result of this study was computed", but the file also contains the Outcome (02:50:27Z). There's no version history, so the "before" claim rests on the file's own timestamp.
- ZIP metadata shows `build.py` at 02:47:43 and `plab.py` at 02:48:45, i.e. edited *after* the stated preregistration time. `dev_landscape.csv` is at 02:49:33 and the prereg at 02:50:27. The whole study was coded, run and written up in about 3 minutes.
- None of this proves a violation. It means **the preregistration isn't independently verifiable**. The researcher also already knew from the prior study that the base strategy lost 93% after costs, so the negative result was largely foreseeable.

---

## 11. Methodological problems, leakage, survivorship bias, inconsistencies (Q11)

### 11.1 Look-ahead and data leakage: checked items

| Item | Finding |
|---|---|
| Daily trend filter (F1) on intraday bars | **Correct.** A daily candle becomes available at its close (`index + 1 day`) and is joined backward on the intraday bar's *close* time. No look-ahead |
| Rolling features (EMA, SMA, RSI, ATR, 500-bar quantiles, volume average) | Causal (trailing windows including the current closed bar). Signals act at the next open, so no look-ahead |
| Entry at next open, stop and exit fills | Stated, but implemented in the **missing** `lab.simulate`. **Can't be verified** |
| Walk-forward train/test boundary | Training trades are filtered by *entry* time, so a trade entered just before the boundary can exit up to 10–20 bars into the test year. That is minor label leakage. It is irrelevant here because nothing was selected, but it should be fixed (filter on exit time) in future work |
| Full-series simulation including H1 | See §10.3: H1 trades were computed, though not reported |

### 11.2 Survivorship and selection bias

- **Asset-level survivorship:** the study covers only BTC, the best-surviving crypto asset, chosen with hindsight. That is acceptable for a BTC-only mandate, but results don't generalise to "crypto".
- **Venue survivorship and proxy risk:** Binance BTC/USDT is a proxy for cbBTC on Solana. USDT-quoted prices embed USDT/USD basis and depeg risk. H2 (Bitstamp BTC/USD, 2014–2017) is a different venue, quote currency and liquidity regime, and volume-based filters (F5) aren't comparable across venues.
- **Multiple testing:** 360 single configs, plus in-sample hand-picked candidates. No correction (Bonferroni, White's Reality Check, deflated Sharpe) was applied. It only matters for the lone positive result, which should be treated as noise.
- **Version A's origin is unknown.** Its selection process, and how many alternatives were tried before it, can't be audited. Its dev PF 2.72 pre-cost should be assumed optimistically biased.

### 11.3 Reproducibility and pipeline defects

1. **The critical dependencies are missing:** `lab.py` (simulator, indicators, Version A), the 1-minute data and the cost-source report. Nothing is reproducible from this repository.
2. **`run_wf.py` would crash.** With zero selections, `oos` is empty and `pd.concat(oos)` on line 98 raises `ValueError: No objects to concatenate`. That is why `walkforward_oos.pkl` and `walkforward_oos_metrics.csv` don't exist, and why `store.pkl` wasn't written by `run_wf.py`. `diag.py` works around this by re-executing only the first half of `run_wf.py`. The README pipeline (`build && run_wf && diag && report`) as written would stop at `run_wf.py`.
3. `report.py` uses `lab.load`, `lab.indicators` and `lab.run_config` for Version A (the spotlab pipeline), but `plab.load` for closes. That means two data-loading paths whose consistency can't be checked.

### 11.4 Inconsistencies between the prereg and the code

| Prereg says | Code does | Severity |
|---|---|---|
| Pairs use "the two single filters with the best DEV walk-forward result" | Pairs are built in-fold from the training-window ranking, requiring different families | Low. The code is the better practice, and it never ran |
| F4 threshold = "normal round-trip cost (2.2%)" | Actual modeled normal round trip at $250 = 2.27% | Low |
| Dev = 2018-03..2024 | Year constants 6.83 (`diag.py`) and 6.84 (`report.py`) | Cosmetic |
| "Pre-cost the concept is real on every timeframe" | t < 2 on 2h, 4h and 1D (§6) | Moderate: an overstatement in the write-up |
| "Version A remains the baseline" | Version A is itself net-negative on Axiom costs | Moderate: wording can mislead a reader into thinking there is a working baseline |
| Fee values "verified … see sources in report" | Report not provided | Moderate: this is the single most important input, and it is unverifiable here |

### 11.5 Other modeling limitations

- **Worst-case intrabar fills** ("validated simulator") are claimed but not shown. If stops and targets are both hit within one bar, the ordering assumption matters on 1D and 4H.
- **Gap and outage handling:** `dropna` after resampling removes empty bars (exchange outages). Indicators then silently "skip" time.
- **Metrics:** the per-trade t-stat assumes independent trades. On 15m with overlapping regimes that assumption is optimistic, but it only strengthens the negative conclusion.
- **Sharpe** from daily equity with √365 is appropriate for 24/7 crypto, but it is dominated by flat days for low-frequency strategies.

---

## 12. What evidence is actually strong

1. **Under ~1.8–4.0% round-trip costs, the RSI(2) pullback family is not viable on BTC.** Pre-cost expectancy is +0.05% to +0.55% per trade against 1.8%+ costs, a 4x to 40x shortfall. This holds on every timeframe, filter, exit, regime and cost scenario, including "axiom_best" and both Coinbase variants. No plausible simulator bug (fill ordering, off-by-one bar) moves a strategy by 2% per trade, so this conclusion survives the missing code.
2. **The walk-forward result (zero eligible configs) is consistent with that.** It isn't a subtle statistical call; the configs aren't close to eligibility.
3. **Version A doesn't survive Axiom costs.** It fails even on its likely in-sample dev period (PF 0.95), and fails badly on H1 (PF 0.20).
4. **Pre-cost, the short-horizon pullback has a small, statistically detectable positive drift on 15m–1h** (t = 2.3–5.3, more than 1,000 trades). This is a well-known phenomenon and not an artifact of selection, because these are unfiltered base configs. It is economically irrelevant at retail fee levels.
5. **Execution cost, specifically the ~0.9–1.0% per-side platform fee, is the dominant variable in this whole research line.** Changing it matters more than any strategy parameter.

## 13. What evidence is weak

1. **The only net-positive config (1D + RSI14≥50):** 15 trades, t = 1.22, one of 180, chosen in-sample, and it fails the preregistered win-rate and frequency gates. Treat it as noise.
2. **Any claim that Version A has a genuine edge.** Its strong dev numbers are probably in-sample. Its strong H2 numbers come from a reused holdout on a different venue and era. On the most recent data (H1) its pre-cost PF is 1.21 with t = 0.40, which is indistinguishable from zero.
3. **Pre-cost edge on 2h, 4h and 1D pullbacks:** not statistically significant.
4. **The exact fee levels** (Axiom tiers, cashback and referral; Coinbase maker and taker): sources not provided.
5. **The Coinbase maker-entry scenario:** assumes perfect limit fills.
6. **Holdout-based claims of any kind:** both holdouts are contaminated by prior use.
7. **Anything that depends on `lab.py`** (fill logic, stops, Version A's definition), because it can't be audited.

---

## 14. Known limitations (summary)

- Not reproducible from the repository: data, simulator and Version A definition are missing.
- No untouched historical holdout exists. H1 and H2 have both been used, and H1 trades for all configs were computed.
- Proxy data (Binance BTC/USDT, Bitstamp BTC/USD) instead of the execution venue (cbBTC on Solana).
- Fee inputs unverified in this repository.
- Walk-forward produced no OOS series, so there is no true OOS performance number for any pullback config.
- There is no multiple-testing correction; it only matters for the one positive in-sample result.
- Small-account effects ($10 minimum, fixed SOL costs) are modeled only approximately.
- The preregistration can't be independently time-verified.

---

## 15. Recommended next research step

**Recommendation: reproduce and verify before any new strategy work, then treat costs as a design constraint rather than an afterthought.**

1. **Restore reproducibility (first, and necessary):** add to this repository
   - `spotlab/lab.py` (the simulator, indicators and `VERSION_A`)
   - a data manifest for the 1-minute files (source, date range, row counts, checksums). The data can be pulled by script rather than committed.
   - the fee-source report
   - the previous study's artifacts

   Then fix the `run_wf.py` empty-`concat` crash, and re-run `diag.py` to confirm that `dev_landscape.csv` reproduces exactly. Until this is done, even the negative results are only "reported", not "audited".
2. **Re-verify execution costs from official sources** for the intended venue(s): the Axiom fee tier actually available to this account, Coinbase Advanced's current tier, and cbBTC pool depth at $125–$500 order sizes. Record the date and the URLs.
3. **Then, in a new, separately preregistered study (dev data only):** require any candidate to show a pre-cost per-trade expectancy of several times the verified round-trip cost *before* costs are even modeled. At about 2.3% round trip on Axiom, that effectively rules out anything trading more than a few times per year. If the user wants a lower-cost venue considered, that is a legitimate new study question. It must be preregistered as such, with costs taken from verified fee schedules and never tuned to make results work.
4. **Accept that the clean test is forward-only.** The prereg itself notes there is no untouched historical data. Any future candidate that passes dev walk-forward should go to a *frozen-spec forward paper-trading* period with a pre-committed minimum sample size before any capital decision. Based on this audit, **no current strategy (pullback or Version A) merits forward paper trading on Axiom costs.**

No parameters were tuned, no holdout was re-run, and no execution or live-trading code was created as part of this audit.
