# New Strategy Research Plan: BTC Spot Pullback at Low Execution Cost (Preregistration Draft)

Drafted: 2026-09-24. Status: **DRAFT, not yet frozen.** No result of this study has been computed.
Freezing happens when the user approves this file and it is committed with a `FROZEN` tag and date (§12). After that, the rules in §4–§8 can't change for this study.

Companion documents:
- `RESEARCH_AUDIT.md`: authoritative on the limitations of the previous study.
- `VENUE_EXECUTION_RESEARCH.md`: venue and cost evidence.

Hard constraints:
- Research only.
- No live trading, no order placement, no exchange API with trading permissions.
- Axiom isn't a target.
- Version A stays frozen and unmodified.

---

## 1. Question

Can a preregistered, high-win-rate RSI(2) pullback on BTC/USD spot (15m, 30m, 1H, 2H, 4H) show **positive expectancy after fees, spread and slippage**? The test uses substantially lower execution costs than Axiom, at a legitimately accessible US/New York venue, for a $500 cash-only, long-only account. It must hold up under walk-forward validation and later on a genuinely untouched forward period.

**Expected answer, stated before any work:** probably not.
- The prior study's in-sample gross edge is 0.06–0.27% per trade on 15m–4h. That is the only evidence available, and it is likely optimistic.
- The cheapest round trip found at any NY-accessible venue is at least 0.60%. That figure is itself unconfirmed; see VENUE_EXECUTION_RESEARCH.md §5.
- The plan therefore puts a cheap **feasibility gate** (Stage 1) before the full grid, so a foreseeable failure doesn't turn into a fishing expedition.

---

## 2. Data, and the honest answer on an untouched holdout

### 2.1 What the previous study already used

The previous study used (RESEARCH_AUDIT.md §3, §10):
- Binance BTC/USDT 2018-03 → 2026-09-09, as dev, walk-forward and H1.
- Bitstamp BTC/USD 2014–2017 (H2).
- Possibly other periods in a study that wasn't provided.

H1 trades were also simulated for every configuration.

### 2.2 Could a genuinely untouched historical dataset be found?

**No.** Every candidate fails:

| Candidate | Why it's not a clean holdout |
|---|---|
| Coinbase / Gemini / Bitstamp BTC-USD 2018–2026 | Same BTC price path as the Binance data already examined. Cross-venue BTC returns are almost perfectly correlated, so it is the same evidence under a different ticker |
| Bitstamp 2011–2013 | Unknown whether the prior study loaded it (`build.py` read all Bitstamp files). It is also a tiny, illiquid, pre-institutional market (Mt. Gox era), irrelevant to 2026 execution |
| Binance/Coinbase after 2026-09-09 | Only about 2 weeks exist as of drafting |

**Statement:** no genuinely untouched historical BTC dataset is available. **The clean final holdout for this study is forward paper trading** that starts after the rules are frozen (§9). Old periods are never called "holdouts" in this study.

### 2.3 Data for this study

The data for this study is not yet acquired; the container's network policy blocked downloads.

- **Primary series:** Coinbase BTC-USD 1-minute OHLCV. This is the most likely execution venue with official-domain support. Resample to 15m/30m/1H/2H/4H using left-labelled UTC bars, the same convention as before.
- **Data manifest (required before Stage 1):** source URL/endpoint, retrieval date, first and last timestamp, row count, count of missing minutes, SHA-256 of each raw file. Gaps are counted and reported, never silently filled. A bar formed from under 50% of its minutes is flagged.
- **Execution-quality data (§VENUE §4):** public L2 order-book snapshots and trade prints, collected from the start of the forward period. There are no historical spread numbers until they are measured.

### 2.4 Periods

| Label | Span | Role | Allowed use |
|---|---|---|---|
| **DEV** | Coinbase BTC-USD from first usable date (after a 200-day indicator warm-up) → 2024-12-31 | Walk-forward development | Selection, and everything in §6 |
| **CONTAMINATED-RECENT** | 2025-01-01 → freeze date | Was the prior study's H1 | **Report only**, clearly labelled "previously examined, not a holdout". Never used for selection, filtering or gating |
| **FORWARD (final holdout)** | Freeze date + 1 day → end of paper period (§9) | Clean validation | Evaluated once, under the frozen rules |

---

## 3. Version A (frozen reference)

- Version A isn't modified, re-parameterised or re-selected.
- Its rules exist only in the missing `spotlab/lab.py` (RESEARCH_AUDIT.md §4.6). **If `lab.py` is provided**, Version A is run unchanged over the same periods and the same cost scenarios as the reference row in every table.
- **If it isn't provided**, Version A is represented only by its previously reported numbers, which are labelled as coming from another dataset and cost model and aren't comparable.
- Version A is a *reference*, not a hurdle that can be lowered. Beating Version A is **not** sufficient; the §7 gates are.

---

## 4. Strategy family (frozen, no new parameters)

This study **reuses the prior study's preregistered grid unchanged**, restricted to the requested timeframes. No new rule or parameter value is introduced, so there is nothing new to tune. The only new dimension is *execution mode* (§5), which is fixed in advance.

### 4.1 Base rule (evaluated at bar close)

- **Trend:** `close > EMA200` and `EMA50 > EMA200`
- **Signal:** `RSI(2) < 10`
- **Protective stop:** 3 x ATR(14) below the entry price, checked intrabar, with worst-case fill (gap-through fills at the bar open if it is worse)
- **Exits:**
  - **X1:** `close > SMA5`, or 10 bars
  - **X2:** `close > SMA20`, or 20 bars
- One position at a time. Long only, spot, cash only.

### 4.2 Single filters (one at a time)

Same definitions as `PULLBACK_PREREGISTRATION.md`:
- F1 daily close (previous closed day) > daily SMA{100, 200}
- F2 ATR% ≥ trailing-500-bar median x {1.0, 1.25}
- F3 (SMA20 − close) ≥ {1.5, 2.5} x ATR
- F4 (SMA20 − close)/close ≥ {1, 2} x **the study's primary round-trip cost** (§5.3), not 2.2%. This is the only definitional change, because F4 is defined relative to cost.
- F5 volume ≥ {1.5, 2.0} x 20-bar average (Coinbase volume)
- F6 RSI(14) ≥ {40, 50}
- F7 ATR% ≤ trailing-500-bar {90th, 75th} percentile

That is 15 filter settings x 2 exits = 30 configs per timeframe x 5 timeframes = **150 configurations**. **No pairs, no triples**: Stage 2 pairs are dropped to reduce multiple testing.

Timeframes are exactly **15m, 30m, 1H, 2H, 4H**. 1D is excluded as instructed; it isn't added back later.

---

## 5. Execution model (fixed in advance)

### 5.1 Execution modes

| Mode | Entry | Exit |
|---|---|---|
| **A** (maker/maker) | Post-only limit buy at the signal bar's close | Post-only limit sell at the exit-signal bar's close. If unfilled after 1 bar, taker at the next open. The stop is always a taker order |
| **B (PRIMARY)** (maker/taker) | Post-only limit buy at the signal bar's close | Taker at the next open after the exit signal; stop as a taker |
| **C** (taker/taker) | Taker at the next open | Taker at the next open; stop as a taker |

Mode B is primary because a stop can't safely be a resting maker order, and B isolates the benefit of maker entry. **Selection uses only mode B.** Modes A and C are reported for information and aren't used to choose anything.

### 5.2 Maker fill model (conservative, to be validated in the forward period)

- A post-only buy at limit L fills only if a later bar within **1 bar** trades **strictly below** L (`low < L`). This models queue position: touching L isn't enough.
- If it doesn't fill, the order is cancelled and logged as a **missed trade**. There is no chasing. The missed-trade rate is reported.
- The fill price is L, and the maker fee applies.
- A post-only sell at limit L fills only if a later bar within 1 bar has `high > L`. Otherwise the taker fallback applies.

### 5.3 Cost scenarios (total per round trip, before the maker/taker split)

- **Fees:** each venue's *confirmed* entry-tier maker and taker fees. Confirming them means reading the logged-in official fee page; that is Stage 0. Unconfirmed figures from VENUE_EXECUTION_RESEARCH.md can't be used as the primary cost.
- **Primary venue and cost:** set in Stage 0, **before** Stage 1 runs, and recorded in §12. It is the confirmed-fee venue the user would actually use. It is not the cheapest-looking venue, and it isn't changed after results.
- **Spread and slippage per taker leg, until measured:** scenarios of **0.00%, 0.02%, 0.05% and 0.10%**. All are labelled **ASSUMED, not measured**. Conclusions must hold at **0.05%**, which is the primary assumption, and the result at 0.10% is reported.
- **Cost-sensitivity grid, for reporting and never for selection:** total round trip of **0.25%, 0.50%, 0.75%, 1.00% and 1.50%**.
- **Stress:** the primary cost x **1.5** (anti-overfitting rule 6).
- **Volume tier:** the entry tier is used. A lower tier may be applied to a trade only if the strategy's own trailing 30-day volume on a $500 account earned it *and* that tier's fee is confirmed.

---

## 6. Validation procedure

### Stage 0: prerequisites (no strategy results computed)

1. Confirm fees from logged-in official pages, and record the primary venue and cost in §12.
2. Acquire the data and write the manifest (§2.3).
3. Re-implement the simulator in this repository with unit tests. Required tests:
   - no look-ahead (signals use closed bars only);
   - entry at the next open or maker-fill rule;
   - stop ordering within a bar;
   - boundary handling: training windows are filtered by **exit** time so no training trade ends in the test year, fixing RESEARCH_AUDIT.md §11.1;
   - empty-selection handling, fixing the prior `pd.concat` crash.
4. If `lab.py` is supplied, reproduce Version A's previously reported zero-cost dev numbers as a simulator cross-check. Any mismatch is reported, not tuned away.

### Stage 1: feasibility gate (cheap; runs before the full grid)

- On DEV, measure the **gross** (zero-fee, zero-spread) per-trade expectancy of the **unfiltered base rule, X2**, for each timeframe under **mode B's maker-fill model**.
- **Kill criterion:** if no timeframe has a gross expectancy of at least **1.5 x the primary round-trip cost** (the fees for mode B plus 0.05% assumed spread/slippage on the taker leg), **stop the study.** Record "infeasible at available costs". Stage 2 does not run.
- Rationale: a filter can raise per-trade expectancy only by removing trades. Given edge efficiency ≈ 0.11 (VENUE §5), a base gross edge far below cost can't plausibly be rescued without fishing.

### Stage 2: walk-forward selection (only if Stage 1 passes)

- **Folds:** expanding training window from the DEV start, test years **2019, 2020, 2021, 2022, 2023, 2024**, each test year strictly after its training window. The first fold's training window is at least 2 years.
- **Eligibility in training:** at least 30 trades, **net PF > 1 under primary cost and mode B**, and net expectancy > 0 under the **1.5x stress** cost.
- **Score:** t-statistic of net per-trade return under primary cost. Highest score wins. **Win rate is never a selection criterion** (rule 8).
- **Selection space:** all 150 configurations. The selected config is traded in the test year; results are concatenated into a single OOS series.
- **Multiple-testing control:** also report White's Reality Check (or Hansen's SPA) p-value for the best config in each training window against the zero-edge null, using a stationary bootstrap. It is reported, not used as a gate.

### Stage 3: viability gates on the concatenated walk-forward OOS series (2019–2024)

All of these must pass:

| # | Gate | Anti-overfitting rule |
|---|---|---|
| G1 | Net expectancy after fees + primary spread/slippage > 0 | 9 |
| G2 | **Lower bound of the one-sided 90% bootstrap CI** of net expectancy > 0 (stationary bootstrap on trades, 10,000 resamples) | 10 |
| G3 | Net expectancy > 0 at **1.5x** primary cost **and** at the 0.10% spread/slippage assumption | 6 |
| G4 | Top 5% of trades contribute **< 50%** of total net profit, **and** net profit stays positive after removing the 2 largest winners | 7 |
| G5 | At least 10 trades per year on average, at least 60 OOS trades in total, and at least 3 of 6 test years net-positive | robustness |
| G6 | Net expectancy > 0 in at least 2 of 3 regimes that each have ≥ 15 trades (§8) | robustness |
| G7 | Max drawdown of the $500 account (50% allocation) no worse than −35% | risk |

A win-rate threshold is **not** a gate; win rate is reported only.

If no config passes, the study ends with "no viable candidate". **No parameter, filter, cost or gate is then changed to find one** (rule 5).

### Stage 4: freeze

- The single strategy that passed (the most recent fold's selection, re-selected once on all of DEV under the same rule) is written into `FROZEN_STRATEGY.md` with its exact rules, venue, costs and execution mode.
- Committed with a timestamp. **Nothing changes after this** (rules 1 and 4).

### Stage 5: reports on CONTAMINATED-RECENT (2025-01 → freeze)

- Run once on the frozen strategy, with the heading **"Previously examined data. Not a holdout. Not a gate."**
- It can't rescue or reject the strategy on its own.
- If it is strongly negative (net expectancy CI entirely < 0), that is recorded as a warning that forward trading will face.

---

## 7. Metrics reported for every evaluated series

Every series here means: the Stage 1 base, each walk-forward fold, the concatenated OOS, CONTAMINATED-RECENT and FORWARD. Version A is reported alongside when available.

| Metric | Definition / note |
|---|---|
| Trade count, trades/year | |
| Win rate | Net and gross, with a Wilson 95% CI |
| Average winner, average loser | Net and gross, % per trade |
| Win/loss ratio | Average win ÷ absolute average loss |
| Expectancy before costs | Mean gross % per trade, bootstrap 95% CI |
| Expectancy after costs | Mean net % per trade (fees + spread + slippage), bootstrap 95% CI |
| Profit factor | Net; bootstrap 95% CI |
| Maximum drawdown | $500 account, daily mark-to-market, at 25/50/75/100% allocation, $10 min order, never above cash (as before) |
| Sharpe | Daily returns x √365, with bootstrap 95% CI. Days in cash count as 0 |
| Maximum losing streak | Consecutive net losers |
| Average holding period | Hours |
| Total fees | $ on the $500 account, and % of starting equity |
| Estimated slippage | $ and bps, **labelled ASSUMED until measured** |
| Profit concentration | Share of net profit from the top 1%, 5% and 10% of trades; net result excluding the top 2 trades |
| Regime performance | Bull / bear / transition (§8): count, win rate, net expectancy with CI |
| Cost-to-edge ratio | Round-trip cost ÷ average absolute gross move; also the edge efficiency (gross expectancy ÷ absolute move) |
| Maker metrics (modes A/B) | Missed-entry rate. Average gross return of filled vs missed signals, which measures adverse selection |
| Buy & hold | Same period, same account, for context |

---

## 8. Regime definition (fixed)

Using daily closes, lagged one full day so that it is known before the bar:

| Regime | Condition |
|---|---|
| BULL | close > SMA200 and SMA200 is higher than 20 days earlier |
| BEAR | close < SMA200 and SMA200 is lower than 20 days earlier |
| TRANSITION | Otherwise |

This matches the prior study's `report.py`, so results stay comparable.

---

## 9. Forward paper-trading protocol (the only clean holdout)

- **Start:** the day after the freeze commit. **No live orders.** The "paper" signals are computed from public market data, and hypothetical fills are logged. Fills must be judged against the **live order book and trade prints** (§VENUE §4), not just candles. That also produces the first *measured* spread, slippage and maker-fill statistics.
- **Minimum length:** the later of **12 months** or **100 closed trades**. For 4H, about 40 trades a year means about 2.5 years; that is accepted rather than shortened.
- **Decision rule (fixed now):** the strategy is considered validated only if forward net expectancy, using **measured** costs, is > 0 **and** the one-sided 90% bootstrap lower bound is > 0 **and** gates G3 and G4 hold on forward data.
- **No interim tuning.** Interim reports are allowed only with no changes. A pre-committed stop applies: if the forward drawdown of the $500 paper account passes −35%, paper trading stops and the result is recorded as failed.
- Anything built later for live execution is **out of scope** of this plan and needs a separate instruction.

---

## 10. Uncertainty reporting

- Bootstrap CIs use a stationary (block) bootstrap on trade sequences, 10,000 resamples, with a fixed seed recorded in §12.
- Every headline number has a CI or an explicit "n too small (< 30)".
- Multiple testing: report the number of configurations tried (150 x modes x costs) next to any best-of result, plus the Reality Check/SPA p-value.
- Anything based on assumed spread/slippage carries the label **ASSUMED**.

---

## 11. Anti-overfitting rules: where each is enforced

| # | Rule | Enforced by |
|---|---|---|
| 1 | Freeze rules before final holdout | Stage 4 freeze commit before FORWARD |
| 2 | Walk-forward validation | Stage 2 |
| 3 | Preserve an untouched final holdout | FORWARD period (§2.2 explains why no historical one exists) |
| 4 | Never optimize on the final holdout | FORWARD is evaluated once; no parameters exist after the freeze |
| 5 | No changing parameters until profitable | Grid reused from the prior prereg; no reruns after failure (Stage 3) |
| 6 | Reject if the edge vanishes with modestly worse costs | Stage 1 (1.5x), training eligibility (1.5x), G3 |
| 7 | Reject dependence on 1–2 huge trades | G4 |
| 8 | Don't select on win rate | Score is the t-stat; win rate isn't a gate |
| 9 | Positive expectancy after fees and slippage | G1, G2 |
| 10 | Report uncertainty and CIs | §10 |

---

## 12. Freeze record (to be completed before Stage 1; blank means not frozen)

| Field | Value |
|---|---|
| Primary venue (fees confirmed from the official logged-in page) | _pending Stage 0_ |
| Confirmed maker / taker entry-tier fee, and confirmation date | _pending_ |
| Primary round-trip cost for mode B (fee + 0.05% ASSUMED taker spread/slippage) | _pending_ |
| Data manifest file + SHA-256 | _pending_ |
| Bootstrap seed | _pending_ |
| Plan approved by user / date | _pending_ |
| Plan commit hash at freeze | _pending_ |

---

## 13. What was **not** done while drafting this plan

- No backtest was run and no strategy result was computed. The container can't reach any market-data host, and the plan must be approved before Stage 1.
- The only numbers referenced are the **previous study's in-sample gross statistics**. They were used in VENUE_EXECUTION_RESEARCH.md §5 for a feasibility estimate, which predicts that Stage 1 will likely fail at confirmed costs. Using previously seen data to decide *whether* to run a study is acknowledged as a mild form of data snooping. It pushes toward running less, not toward selecting a config.
- Version A wasn't run or modified.
- No exchange account, API key, order or live-trading component was created.

---

## 14. Prerequisites the user must supply or approve before any work starts

1. **Approve or amend this plan.** Amendments are made before freezing only.
2. **Network access:** allow the public market-data hosts listed in VENUE_EXECUTION_RESEARCH.md §0 in this environment's network settings (read-only public data; no keys).
3. **Fee confirmation:** screenshots or copied text of the logged-in fee page for the intended venue.
4. **Optional:** `spotlab/lab.py`, so that Version A can be run as a live reference.
