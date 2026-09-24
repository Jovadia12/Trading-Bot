# BTC Spot Execution Venues for a US / New York Customer: Execution Economics

Research date: 2026-09-24
Scope: legitimate BTC spot venues for a US customer resident in New York, and realistic round-trip costs for a $500 account.
Status: research only. No account was opened, no API key was created, and no exchange API was contacted, public or private.
Axiom is out of scope and isn't used as a target venue anywhere in this document.

---

## 0. Read this first: how the facts below were verified

The research ran in a sandboxed cloud container whose network policy **blocked direct access** to every exchange and regulator website tried. The blocked hosts were:
- www.coinbase.com, help.coinbase.com, docs.cdp.coinbase.com, api.exchange.coinbase.com, api.coinbase.com
- www.gemini.com, support.gemini.com, docs.gemini.com, api.gemini.com
- robinhood.com, docs.robinhood.com
- www.bitstamp.net
- www.kraken.com, support.kraken.com, api.kraken.com
- www.dfs.ny.gov
- data.binance.vision

The only research channel available was a web search engine. It returns result titles and URLs plus a machine-generated summary of the indexed page text. Every fact is therefore tagged with its evidence level:

| Tag | Meaning |
|---|---|
| **[OFF-S]** | Official-domain page, seen only through a search-engine summary with the search restricted to that official domain. The URL is official, but I did not read the page myself. |
| **[3P]** | Third-party source only (review sites, news, aggregators). |
| **[CONFLICT]** | Sources disagree. Both values are shown and neither is assumed. |
| **[NOT FOUND]** | Not established in this pass. It is **not** assumed either way. |

**No fact here counts as fully verified (read directly from the official page).** Before any money is committed, every row must be re-checked by logging in to the venue and reading its fee page. Logged-in fee pages also show the account's own tier.

**Spread and slippage: UNAVAILABLE.** No order-book or trade data could be retrieved, because all exchange market-data endpoints were blocked. Per instructions, no spread or slippage number is invented. §4 explains how to obtain them.

---

## 1. Venue status matrix

The columns separate the five questions asked:
- **Exists:** the venue operates.
- **NY:** it serves New York residents.
- **BTC spot:** BTC/USD spot is available.
- **API trading:** orders can be placed programmatically.
- **User eligibility:** whether *this* user qualifies.

| Venue | Exists | Serves NY | BTC/USD spot | Programmatic spot trading | User eligibility |
|---|---|---|---|---|---|
| **Coinbase Advanced** (Coinbase, Inc.) | Yes [OFF-S] | Yes. Coinbase, Inc. is licensed by NYDFS [OFF-S]. Some products (e.g. DEX trading) exclude NY, and the NY asset list is set quarterly [OFF-S]. BTC availability in NY is expected but wasn't explicitly confirmed | BTC-USD [OFF-S] | Yes: Advanced Trade API, REST `POST /api/v3/brokerage/orders` [OFF-S] | **Unknown.** Needs KYC and NY residency verification. The age requirement is [NOT FOUND] in this pass |
| **Gemini ActiveTrader / API** (Gemini Trust Company, LLC) | Yes [OFF-S] | Yes. NY trust company, licensed by NYDFS [OFF-S]. A NY "areas of availability" page exists [OFF-S] | BTCUSD [OFF-S] | Yes: REST + WebSocket order APIs [OFF-S] | **Unknown.** Age requirement [NOT FOUND] |
| **Robinhood Crypto Trading API** (Robinhood Crypto, LLC) | Yes [OFF-S] | Yes. Available in all US states and DC; licensed by NYDFS [OFF-S] | BTC-USD [OFF-S] | Yes. US customers only, with an active Robinhood Crypto account [OFF-S] | **Unknown.** Must be **18+** [OFF-S]. Whether NY accounts get the v2 "fee tier" API is [NOT FOUND] ("eligible jurisdictions") |
| **Bitstamp** (Bitstamp USA, Inc.; "Bitstamp by Robinhood") | Yes [OFF-S] | **Partially.** Bitstamp USA is licensed by NYDFS [OFF-S]. **[CONFLICT]** One FAQ says app Buy/Sell is disabled for NY residents; a blog post says "Quick buy & sell option has landed in New York". NY access to the BTC/USD **order book** was not confirmed | BTC/USD [3P]; pair not confirmed for NY | Yes: API v2 [OFF-S] | **Unknown** |
| **Bullish US** | Yes. It received a NY BitLicense in Sep 2025 [OFF-S news page] | Licensed, but reported to target institutions and "advanced traders" [3P] | Not confirmed | Not confirmed | **Unlikely for a $500 retail account.** Not pursued |
| Kraken | Yes | **No.** Kraken says it does not serve NY [OFF-S support page; 3P] | – | – | **Ineligible (NY)**. Excluded |
| Crypto.com | Yes | **No BitLicense** according to 3P sources | – | – | Excluded pending official confirmation |
| Binance.US | Yes | [NOT FOUND] this pass. Historically excluded NY | – | – | Excluded pending verification |
| PayPal / Venmo / Cash App | Yes | Various | Buy/sell only | No public trading API for this use [NOT FOUND] | Not programmatic; excluded |

No help with bypassing age or geographic restrictions is given or implied. A venue that doesn't serve NY is simply excluded.

---

## 2. Per-venue detail

### 2.1 Coinbase Advanced

| Item | Finding | Evidence |
|---|---|---|
| Pair | BTC-USD | [OFF-S] |
| Fee model | Maker-taker. Fees are **not** balance-based: they depend on 30-day USD trading volume, and tiers update hourly | [OFF-S] |
| Fee change | New structure effective **2026-09-16**. Tiers now start at **$10,000** of 30-day volume (previously $25,000), and spot and derivatives volume are combined | [OFF-S] announcement; figures [3P] |
| **US entry tier** | **Maker 0.50%, taker 0.90%** | [3P] (several 2026 summaries of the 2026-09-16 change). The official table wasn't visible in search output |
| Lower tiers | Start at $10k volume; the rate at each tier is [NOT FOUND]. The top (VIP) tier is reported as 0.00% / 0.02% | [3P] |
| Balance qualification | None found; volume only | [OFF-S] |
| Coinbase One | 25% back on Advanced spot fees in USDC, capped at $100/month. Coinbase One's "zero trading fees" do **not** apply to Advanced | [OFF-S] (search summary) |
| Spread | Central limit order book, "no spread fees". **The actual BTC-USD quoted spread is UNAVAILABLE** | [OFF-S]; data blocked |
| API | Advanced Trade API. CDP API keys with View and Trade permissions; the Trade permission "grants permission to execute buy and sell orders" | [OFF-S] |
| Post-only | `limit_limit_gtc` takes `post_only`. **Caveat:** the doc summary says a post-only order that would take is "repriced to the prevailing best bid or offer" rather than rejected. The exact behaviour needs to be confirmed in the live docs | [OFF-S] |
| Minimum order | Product API shows a `quote_min_size` of 0.00000001, but a separate **notional minimum** applies whose value is [NOT FOUND]. `base_min_size` was deprecated in 2022 | [OFF-S] |
| USD deposit / withdrawal | ACH deposit: no Coinbase fee. ACH withdrawal: no Coinbase fee. Fedwire withdrawal: **$25**. **Caveat:** these came from *Coinbase Exchange* help pages, and retail Coinbase/Advanced funding pages weren't confirmed. Wire deposit fee [NOT FOUND] | [OFF-S] |
| BTC withdrawal fee | [NOT FOUND] (a network fee is expected; amount not established) | – |
| BTC deposit fee | [NOT FOUND] | – |
| NY restrictions | DEX trading excluded in NY. NY-supported assets are set quarterly | [OFF-S] |
| Age / eligibility | [NOT FOUND] this pass | – |
| Manual confirmation | Not required. API orders with a Trade-scoped key execute directly | [OFF-S] (inferred from the permission definition) |
| Security | IP allowlist per key, recommended but optional. Keys can be scoped per portfolio | [OFF-S] |

### 2.2 Gemini (ActiveTrader and API)

| Item | Finding | Evidence |
|---|---|---|
| Pair | BTCUSD | [OFF-S] |
| Fee model | Maker-taker. **Tier = the better of** trailing 30-day volume (excluding stablecoin pairs) **or total asset balance in USD**. Tiers are recalculated daily (~02:00 UTC in one source, 00:00 UTC in another) | [OFF-S]; time [CONFLICT] |
| **ActiveTrader base tier** | **Maker 0.60%, taker 1.20%** | [3P] several; gemini.com-restricted search also returned 0.60/1.20 |
| **API fee schedule, lowest tier** | **[CONFLICT]** One search summary says <$10k gives **0.20% / 0.40%**. Another says the $0 tier is **0.40% maker / 0.60% taker** (as worded), with 0.20/0.40 at the $50k tier. A third says the gemini.com-restricted search returned 0.60/1.20 as the lowest tier of the API schedule | [CONFLICT] |
| Which schedule applies to API orders | Gemini publishes a separate "API Fee Schedule" page; support text refers to "ActiveTrader/API trading" tiers. **Which schedule applies to a retail account's API orders is unresolved** | [CONFLICT] |
| Lower tiers | $10k tier reportedly 0.40% / 0.80%; top tier ≈ 0.00% / 0.02–0.025% at $250M+ | [3P] |
| Balance qualification | **Yes.** Asset balance can set the tier. At $500 this almost certainly doesn't reach any threshold (thresholds [NOT FOUND]) | [OFF-S] |
| Partial fills | Taker fee on the immediately filled part, maker fee on the resting remainder | [OFF-S] |
| Spread | **UNAVAILABLE** | data blocked |
| Minimum order | **0.00001 BTC**; increment 1e-8 BTC | [OFF-S] |
| Post-only | "Maker-or-cancel" supported; it cancels rather than rejects if it would take | [OFF-S] |
| USD deposit | ACH and wire deposits: no Gemini fee | [OFF-S] |
| USD withdrawal | ACH: no fee. Wire: **$25** | [OFF-S] |
| BTC withdrawal | **Dynamic fee** covering network cost; amount varies | [OFF-S] |
| BTC deposit | No fee | [OFF-S] |
| Age / eligibility | [NOT FOUND] this pass | – |
| Manual confirmation | Not required for API orders placed with a Trader-role key | [OFF-S] (inferred) |
| Security | Trading-role keys **must be "affirmed"** since 2025-06-30: either IP-allowlisted or explicitly set Unrestricted. Optional **"Requires Heartbeat"**: open orders auto-cancel after 30 s without a request (15 s heartbeat recommended). Master keys don't support cancel-on-disconnect | [OFF-S] |

### 2.3 Robinhood Crypto Trading API

| Item | Finding | Evidence |
|---|---|---|
| Pair | BTC-USD | [OFF-S] |
| API versions | **v1:** orders without fee tiers (commission-free; costs are embedded in the spread through market-maker routing). **v2:** "Place crypto orders with fee tiers" via exchange routing, "for customers in eligible jurisdictions". Only v2 orders count toward tier volume | [OFF-S] |
| **v2 maker status** | **v2 API orders "are charged the taker rate until maker/taker is fully rolled out."** Maker pricing can't currently be counted on via the API | [OFF-S] (search summary of the crypto-api support page) |
| Fee tiers (exchange routing) | Official: "fees range from 0.00%–0.95%", falling with 30-day volume; expanded from 3 to 7 tiers [OFF-S]. Reported table: $0–10k **0.50% maker / 0.95% taker**; $10–50k 0.35/0.75; $50–250k 0.125/0.25; $250–500k 0.075/0.15; $500k–1M 0.06/0.125; $1–5M 0.04/0.10; $5–10M 0.02/0.04; $10–25M 0.01/0.03; $25M+ 0.00/0.03 | Range [OFF-S]; table from a search summary that couldn't be traced to the exact official page |
| Routing | Exchange routing goes to **EDX Markets** and **Bitstamp USA**. Limit orders are generally routed to Bitstamp; a resting limit that later fills earns the maker fee. Market and stop orders always pay taker | [OFF-S] |
| Market-maker routing (v1 / no-fee path) | Robinhood receives payment from market makers. One search summary states **$0.95 per $100 notional as of 2026-06-15**; this couldn't be confirmed and is flagged. Effective cost = spread, **UNAVAILABLE** | [OFF-S] (unconfirmed figure) |
| Balance qualification | None found; volume only | [OFF-S] |
| Post-only | [NOT FOUND] | – |
| Minimum order | [NOT FOUND] | – |
| USD deposit / withdrawal | [NOT FOUND] this pass | – |
| BTC withdrawal / deposit fee | [NOT FOUND] this pass | – |
| Eligibility | 18+, US only, active Robinhood Crypto account needed before creating API keys [OFF-S]. NY eligibility for **v2 fee-tier orders** [NOT FOUND] | [OFF-S] |
| Manual confirmation | API orders execute on signed requests; nothing indicates per-trade confirmation | [OFF-S] (inferred) |
| Security | Ed25519 keypair; the user registers the public key. Requests are signed with `x-api-key`, `x-signature`, `x-timestamp`. Keys issued after 2024-08-13 look like `rh-api-<uuid>`. Rate limits [NOT FOUND] | [OFF-S] |

### 2.4 Bitstamp (Bitstamp USA, Inc.)

| Item | Finding | Evidence |
|---|---|---|
| NY status | NYDFS-licensed [OFF-S]. **[CONFLICT]** about NY Buy/Sell. BTC/USD order-book trading for NY is **not confirmed** | [OFF-S] / [CONFLICT] |
| Fees | Official: first **$1,000** of 30-day volume at **0%**. This may be tied to a promotion ("Summer of Discovery"), so it is **not** relied on [OFF-S]. Reported base tier: **0.30% maker / 0.40% taker** below $10k of 30-day volume, falling to 0.00/0.03 above $1B | 0%-on-$1k [OFF-S]; 0.30/0.40 [3P only] |
| Minimum order | 0.0002 BTC for BTC pairs (lowered from 0.001; post date unknown) | [OFF-S] (blog) |
| BTC withdrawal | **0.0005 BTC** (search summary; possibly out of date) | [OFF-S] |
| USD | ACH deposits and withdrawals supported (fees [NOT FOUND]). International wire: 0.1%, min $25 | [OFF-S] |
| API | API v2. Key permissions selectable; key can be locked to an IP | [OFF-S] |
| Post-only | [NOT FOUND] | – |

---

## 3. $500-account round-trip cost scenarios

### 3.1 Tier reality for a $500 account

Fee tiers depend on 30-day volume, and one round trip on $500 is $1,000 of volume. Using the prior study's trade frequencies (in-sample, Binance, so only indicative), the monthly volume at 100% allocation would be:

| Timeframe (prior-study trade rate) | ≈ Round trips/month | ≈ 30-day volume at $500/trade |
|---|---|---|
| 15m (645/yr) | 54 | ≈ $54,000 |
| 30m (317/yr) | 26 | ≈ $26,000 |
| 1h (161/yr) | 13 | ≈ $13,000 |
| 2h (80/yr) | 7 | ≈ $7,000 |
| 4h (40/yr) | 3.3 | ≈ $3,300 |

Higher-frequency strategies could climb out of the entry tier at some venues. For example, Robinhood's reported $50–250k tier is 0.125/0.25. But §5 shows those same strategies have per-trade gross edges far below even those rates. **The scenarios below use each venue's entry tier.** A lower tier may only be used in a study if the fee table is confirmed on the official page, and the tier must be modeled as *earned* from the strategy's own trailing volume, not assumed.

### 3.2 Fee-only round-trip cost (entry tier)

| Venue (entry tier) | Evidence | A: maker + maker | B: maker in + taker out | C: taker + taker | $ fees per $500 round trip (A / B / C) |
|---|---|---|---|---|---|
| Coinbase Advanced (0.50 / 0.90) | [3P] | **1.00%** | **1.40%** | **1.80%** | $5.00 / $7.00 / $9.00 |
| Gemini ActiveTrader (0.60 / 1.20) | [3P] | **1.20%** | **1.80%** | **2.40%** | $6.00 / $9.00 / $12.00 |
| Gemini API schedule (if 0.20 / 0.40 applies) | [CONFLICT] | 0.40% | 0.60% | 0.80% | $2.00 / $3.00 / $4.00 |
| Robinhood v2 exchange routing (0.50 / 0.95) | range [OFF-S], table unconfirmed | 1.00%* | 1.45%* | **1.90%** | $5.00 / $7.25 / $9.50 |
| Bitstamp (0.30 / 0.40) | [3P] | 0.60% | 0.70% | 0.80% | $3.00 / $3.50 / $4.00 |
| Robinhood v1 (no fee; spread-embedded) | [OFF-S] | n/a | n/a | fee 0% + **spread UNAVAILABLE** | UNAVAILABLE |

\* **Via the API, Robinhood v2 orders are currently charged the taker rate** [OFF-S], so A and B aren't achievable programmatically today. Treat API cost as C (1.90%) until maker pricing is live.

Fees are charged on each side's notional, so round-trip fee ≈ entry fee + exit fee. The small exit-price term isn't material at this scale.

### 3.3 Full round trip: fees + spread + slippage

| Component | Maker leg | Taker leg |
|---|---|---|
| Published fee | Table 3.2 | Table 3.2 |
| Spread | Not paid (the order rests at its own price). The real cost is **adverse selection and non-fill risk**: **UNAVAILABLE** | Half the quoted spread per taker leg: **UNAVAILABLE** |
| Slippage beyond top of book ($250–$500 order) | 0 by construction | **UNAVAILABLE** (needs order-book depth data) |
| **Total round trip** | **Fee is a lower bound** | **Fee is a lower bound** |

So every total in this document is **"published fees + an unmeasured, non-negative spread/slippage term"**. No venue's total round-trip cost can be stated as a single number from the evidence gathered.

---

## 4. How to obtain the missing spread and slippage data (not done here)

This needs network access to public market-data endpoints (no API key, no trading permission). In this cloud environment, that means adding the hosts to the environment's allowed network domains.

1. **Quoted spread now:** sample public level-2 order books (e.g. Coinbase `api.exchange.coinbase.com/products/BTC-USD/book?level=2`; Gemini `api.gemini.com/v1/book/btcusd`) every N seconds for ≥ 2 weeks, covering weekends and US/Asia sessions. Record best bid/ask and depth.
2. **Slippage for $250/$500:** from the same snapshots, compute the volume-weighted fill price for a $250 and a $500 marketable order against the book, minus mid. Report the median, 90th and 99th percentiles, and the worst case during volatile hours.
3. **Historical spread:** free historical L2 data generally isn't published by these venues. Options are:
   (a) a paid historical order-book vendor, whose coverage and cost would need verifying;
   (b) spread *estimators* from public trade prints (e.g. the Roll or Abdi–Ranaldo estimators). These are approximations and must be labelled as such.
4. **Maker fill realism:** during forward paper trading, log each hypothetical post-only order against the live book and trades. Record fill or no-fill and the price move after the fill (adverse selection).

Until this is done, every study must run spread/slippage as **explicit scenarios** (e.g. 0 / 0.02% / 0.05% / 0.10% per taker leg). They must be labelled "assumed, not measured", and conclusions must hold across the whole range.

---

## 5. Cost-to-edge analysis

### 5.1 Definition

- **Average absolute expected move** per trade = `win_rate × avg_win + (1 − win_rate) × |avg_loss|`, gross of costs.
- **Cost-to-edge ratio** = round-trip execution cost ÷ average absolute expected move.
- **Edge efficiency** = gross expectancy ÷ average absolute move. A strategy breaks even only when **cost-to-edge ratio < edge efficiency**.

### 5.2 Inputs (illustrative only)

These are the only per-trade statistics available: the prior study's **pre-cost, in-sample, Binance BTC/USDT, 2018-03..2024** base RSI(2) pullback (exit X2) results from `candidates_dev_by_cost.csv`. **RESEARCH_AUDIT.md classifies these as in-sample and unreproducible.** They are used here for a feasibility check only, never for selection. Being in-sample, they are more likely optimistic than pessimistic.

| TF | Trades/yr | Win % | Avg win | Avg loss | **Avg abs move** | **Gross expectancy** | **Edge efficiency** | Avg hold |
|---|---|---|---|---|---|---|---|---|
| 15m | 645 | 73.5 | +0.38% | −0.84% | **0.50%** | +0.060% | 0.12 | 1.6 h |
| 30m | 317 | 73.9 | +0.56% | −1.26% | **0.74%** | +0.084% | 0.11 | 3.0 h |
| 1h | 161 | 72.7 | +0.80% | −1.74% | **1.05%** | +0.104% | 0.10 | 6.1 h |
| 2h | 80 | 72.0 | +1.20% | −2.48% | **1.56%** | +0.166% | 0.11 | 12.1 h |
| 4h | 40 | 71.4 | +1.77% | −3.51% | **2.27%** | +0.265% | 0.12 | 25.5 h |

The pullback's edge efficiency is about **0.10–0.12 on every timeframe**. It keeps only about a tenth of each trade's typical absolute move as net gross edge. That is the structural problem: cost must be below about 10–12% of the average move.

### 5.3 Cost-to-edge ratio at the requested cost levels (breakeven requires ratio < efficiency ≈ 0.10–0.12)

| Round-trip cost | 15m | 30m | 1h | 2h | 4h |
|---|---|---|---|---|---|
| 0.25% | 0.49 | 0.34 | 0.24 | 0.16 | **0.11** (≈ breakeven) |
| 0.50% | 0.99 | 0.67 | 0.47 | 0.32 | 0.22 |
| 0.75% | 1.48 | 1.01 | 0.71 | 0.48 | 0.33 |
| 1.00% | 1.98 | 1.35 | 0.95 | 0.64 | 0.44 |
| 1.50% | 2.97 | 2.02 | 1.42 | 0.96 | 0.66 |

Equivalently, cost ÷ gross expectancy is **4.2x, 3.0x, 2.4x, 1.5x and 0.9x** at 0.25% cost, for 15m through 4h. Only 4h is (barely) below 1.

### 5.4 Minimum gross expected move required

| Round-trip cost C | Breakeven gross expectancy per trade | Gross expectancy to survive a +50% cost stress (1.5 C) | **Required avg abs move at pullback-like efficiency 0.11** | Which prior-study TF has that abs move |
|---|---|---|---|---|
| 0.25% | 0.25% | 0.375% | **≈ 2.3%** | 4h (2.27%), marginal |
| 0.50% | 0.50% | 0.75% | **≈ 4.5%** | none of 15m–4h (1D ≈ 5.6%) |
| 0.75% | 0.75% | 1.125% | **≈ 6.8%** | none |
| 1.00% | 1.00% | 1.50% | **≈ 9.1%** | none |
| 1.50% | 1.50% | 2.25% | **≈ 13.6%** | none |

Breakeven gross expectancy ≈ C, and the multiplicative fee effect changes this by less than 0.01 percentage points at these levels.

### 5.5 What this implies

- **The cheapest scenario is A at Bitstamp's reported 0.60%.** Bitstamp's figure is third-party only and its NY order-book access is unconfirmed. Gemini API's possible 0.40% is [CONFLICT].
- **The cheapest venues with official-domain support are Coinbase (1.00% A / 1.80% C) and Robinhood API (1.90%, taker only today).**
- **Even at 0.25% round trip, no timeframe from 15m to 2h breaks even on the prior gross edge, and 4h only just does.** At any cost confirmed in this pass (≥ 0.60% even under the most favourable unconfirmed figure), the 15m–4h RSI(2) pullback is predicted to lose money **before** spread and slippage.
- **Lower fees alone won't rescue the high-win-rate pullback on 15m–4h.** A viable design needs either a much higher edge efficiency, or maker execution that materially improves the *gross* entry. Maker execution might also worsen it through adverse selection. That can only be measured, not assumed; see NEW_STRATEGY_RESEARCH_PLAN.md, Stage 1.

---

## 6. Summary

| Question | Answer |
|---|---|
| NY-accessible, API-capable BTC/USD venues (official-domain support) | **Coinbase Advanced, Gemini, Robinhood Crypto API.** Bitstamp is licensed in NY, but NY BTC/USD order-book access is unconfirmed |
| Excluded for NY | Kraken (says it doesn't serve NY); Crypto.com (no BitLicense per 3P); Binance.US (unverified, historically excluded); Bullish US (institution-focused) |
| Lowest entry-tier fees with official-domain support | Coinbase: 0.50% maker / 0.90% taker (3P figures, official announcement of the 2026-09-16 schedule). Robinhood: up to 0.95% (official range), taker-only via API for now |
| Lowest fees found anywhere, unconfirmed | Gemini API schedule 0.20/0.40 [CONFLICT]; Bitstamp 0.30/0.40 [3P] |
| Balance-based tier qualification | **Gemini only** (30-day volume *or* asset balance). Irrelevant at $500 |
| Spread / slippage | **UNAVAILABLE**: all market-data hosts were blocked. No numbers invented |
| Structural finding | The pullback keeps about 11% of its average move as gross edge, so cost must be ≲ 0.25% just to break even on 4h, and less on faster timeframes. No confirmed venue/tier for a $500 account comes close |

---

## 7. Sources consulted (search-surfaced; not directly readable from this environment)

Official domains:
- Coinbase Advanced fees: https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees
- Coinbase blog, fee change: https://www.coinbase.com/blog/were-lowering-fees-for-many-active-traders-on-coinbase-advanced
- Coinbase Create Order API: https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/create-order
- Coinbase List Products: https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/products/list-products
- Coinbase Advanced Trade API permissions: https://docs.cdp.coinbase.com/advanced-trade/docs/rest-api-scopes.html
- Coinbase API security best practices: https://docs.cdp.coinbase.com/get-started/authentication/security-best-practices
- Coinbase ACH deposits: https://help.coinbase.com/en/exchange/funding/depositing-with-ach
- Coinbase ACH withdrawals: https://help.coinbase.com/en/exchange/funding/withdrawing-with-ach
- Coinbase Fedwire withdrawals: https://help.coinbase.com/en/exchange/funding/withdrawing-with-fedwire
- Coinbase One: https://www.coinbase.com/one
- Coinbase US user agreement: https://www.coinbase.com/legal/user_agreement/united_states
- Coinbase DEX trading: https://www.coinbase.com/blog/coinbase-unlocks-millions-of-assets-with-dex-trading
- Gemini ActiveTrader fee schedule: https://www.gemini.com/fees/activetrader-fee-schedule
- Gemini API fee schedule: https://www.gemini.com/fees/api-fee-schedule
- Gemini trading fees FAQ: https://support.gemini.com/hc/en-us/articles/115004709906-What-are-your-trading-fees
- Gemini transfer fees: https://support.gemini.com/hc/en-us/articles/115004710166-What-are-the-transfer-fees
- Gemini trading minimums: https://support.gemini.com/hc/en-us/articles/4401824250267-Are-there-trading-minimums-
- Gemini Trusted IPs: https://support.gemini.com/hc/en-us/articles/37826759865115-How-to-secure-your-API-Keys-with-Trusted-IPs
- Gemini roles: https://developer.gemini.com/roles
- Gemini orders API: https://docs.gemini.com/rest/orders
- Gemini New York availability: https://www.gemini.com/areas-of-availability/new-york-us
- Robinhood crypto fee tiers: https://robinhood.com/us/en/support/articles/crypto-fee-tiers/
- Robinhood Crypto Trading API: https://robinhood.com/us/en/support/articles/crypto-api/
- Robinhood crypto order routing: https://robinhood.com/us/en/support/articles/crypto-order-routing/
- Robinhood crypto trading API docs: https://docs.robinhood.com/crypto/trading/
- Robinhood Crypto fee schedule (PDF): https://cdn.robinhood.com/assets/robinhood/legal/rhc-fee-schedule.pdf
- Robinhood Crypto is coming to New York: https://robinhood.com/us/en/newsroom/robinhood-crypto-is-coming-to-new-york/
- Bitstamp fee schedule: https://www.bitstamp.net/fee-schedule/
- Bitstamp USA Inc.: https://www.bitstamp.net/legal/usa-inc/
- Bitstamp quick buy & sell in New York: https://blog.bitstamp.net/post/quick-buy-and-sell-new-york/
- Bitstamp crypto withdrawal cost: https://www.bitstamp.net/faq/how-much-does-a-cryptocurrency-withdrawal-cost/
- Bitstamp minimum order size: https://blog.bitstamp.net/post/weve-lowered-minimum-order-size-all-pairs/
- Bitstamp API: https://www.bitstamp.net/api/
- Kraken licensing: https://support.kraken.com/articles/where-is-kraken-licensed-or-regulated
- Bullish BitLicense: https://www.bullish.com/us/news-insights/bullish-secures-new-york-bitlicense-from-the-nydfs-paving-way-for-u-s-launch
- NYDFS virtual currency businesses: https://www.dfs.ny.gov/virtual_currency_businesses

Third-party sources used only where tagged [3P]:
- https://www.datawallet.com/crypto/coinbase-fees
- https://tokenecho.io/guides/coinbase-advanced-trade-fees/
- https://coinbureau.com/review/gemini
- https://cryptoslate.com/crypto-exchanges/gemini-exchange-review/
- https://www.bitdegree.org/crypto/tutorials/gemini-fees
- https://cryptoslate.com/crypto-exchanges/bitstamp-exchange-review/
- https://legalclarity.org/is-kraken-available-in-new-york-why-its-blocked/
- https://koinly.io/blog/best-crypto-exchanges-new-york/
- https://www.coindesk.com/policy/2025/09/17/crypto-platform-bullish-wins-new-york-bitlicense-clearing-path-for-u-s-expansion
