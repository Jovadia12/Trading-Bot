# Coinbase Advanced: Market Data + Paper Execution

Status (2026-09-24): **paper/research mode only.**
- Live order placement is not implemented, and the design makes it unreachable (§8).
- The strategy layer is empty: Version A and the preregistered RSI(2) pullback are **not** implemented or modified.

---

## 1. Architecture

```
config/          settings.py        PAPER_MODE gate, env/.env loading, redacted Credentials
                 logging_setup.py   secret-redacting log filter
                 env.example        template (no values); copy to .env locally
exchange/        endpoints.py       read-only GET allowlist (enforced) + forbidden list (documented/tested)
                 auth.py            CDP JWT (Ed25519/EdDSA; legacy EC/ES256)
                 transport.py       ReadOnlyTransport: the ONLY REST network path; deny-by-default
                 client.py          ExchangeClient (interface) + CoinbaseAdvancedClient (reads only;
                                    every order/funds method raises)
                 errors.py          LiveOrderExecutionDisabled
market_data/     models.py          ProductSpec, Quote, MarketTrade, Candle, spread_bps()
                 order_book.py      L2 book from snapshots/updates; depth walk (VWAP)
                 websocket_feed.py  public WS feed (heartbeats, level2, market_trades, ticker), gap
                                    detection, reconnect/resubscribe, file replay
                 spread_monitor.py  measured spread + taker cost for $250/$500, percentiles, CSV
execution/       paper_engine.py    PaperExecutionEngine (no exchange dependency, no network)
                 models.py          orders, fills, statuses
                 fees.py            FeeSchedule (account rates or labelled default)
paper_trading/   account.py         $500 cash-only paper account with order holds
                 recorder.py        round-trip trade records (CSV) + order log (JSONL)
                 runner.py          session runner / CLI  (python -m paper_trading)
risk/            limits.py          pre-trade limits (max notional, open orders, long-only, DD halt)
strategy/        base.py            Signal / Strategy interface only; no rules in this phase
backtest/        candle_fill_model.py  plan §5 maker-fill + cost conventions (shared definitions)
tests/           110 tests, incl. no-live-order proofs; fixtures/ has a SYNTHETIC WS replay file
```

The data flow is one way:

**Coinbase WS / REST (reads)** → `market_data` → `PaperExecutionEngine` → `TradeRecorder` → files.

The paper engine never holds a reference to the exchange client. There is no `LiveExecutionEngine`.

---

## 2. Authentication

- **Key type:** Coinbase Developer Platform (CDP) API key. **Ed25519** is recommended; legacy EC P-256 PEM keys also work.
- **JWT format:** mirrors Coinbase's official SDK (`coinbase/coinbase-advanced-py`, `jwt_generator.py`, commit `54fb8ed`, 2026-06-19). That SDK was read directly from GitHub, which was the only reachable Coinbase source.
  - Claims: `sub=<key name>`, `iss="cdp"`, `nbf=now`, `exp=now+120`, `uri="GET api.coinbase.com<path>"`.
  - Headers: `kid=<key name>`, `nonce=<random hex>`.
  - Algorithm: `EdDSA` for Ed25519, `ES256` for EC.
- **Secret formats accepted:** raw base64 (32-byte seed, or the 64-byte seed‖pubkey that the CDP portal downloads), or a PEM block.
- **A fresh 2-minute token is made per REST request.** Tokens and secrets are never logged.
- **WebSocket market-data channels are public**, so **no JWT is sent on the market-data connection**.

### Required environment variables

| Variable | Required | Meaning |
|---|---|---|
| `PAPER_MODE` | **yes**, must be `true` | Hard gate. Anything else, or unset, means the app refuses to start |
| `COINBASE_API_KEY` | optional | CDP key name/ID. Needed only for account reads and your real fee tier |
| `COINBASE_API_SECRET` | optional | Ed25519 private key (base64) or PEM |
| `ALLOW_TRADE_SCOPED_KEY` | optional, default `false` | Only if you knowingly use a Trade-scoped key |

Setup:
1. Copy `config/env.example` to `.env` in the repo root and fill it in **locally**.
2. `.env`, `.env.*`, `*.key`, `*.pem`, `secrets/` and `credentials/` are git-ignored, and a test checks this.
3. **Create a View-only key.** At startup the app calls `GET /key_permissions`:
   - it **refuses** keys with `can_transfer`;
   - it **refuses** keys with `can_trade` unless `ALLOW_TRADE_SCOPED_KEY=true`;
   - even then, orders stay impossible (§8).
4. Restrict the key to your IP in the CDP portal if possible.

Without credentials, everything runs on public endpoints, and fees use the labelled default (§5).

---

## 3. REST endpoints used (GET only; enforced allowlist in `exchange/endpoints.py`)

| Purpose | Authenticated | Public (no key) |
|---|---|---|
| BTC-USD product spec (increments, min/max size, status) | `/api/v3/brokerage/products/BTC-USD` | `/api/v3/brokerage/market/products/BTC-USD` |
| Order book | `/api/v3/brokerage/product_book?product_id=BTC-USD&limit=N` | `/api/v3/brokerage/market/product_book` |
| Best bid/ask | `/api/v3/brokerage/best_bid_ask?product_ids=BTC-USD` | from the public book (limit=1) |
| Candles (≤ 350 per request; `ONE_MINUTE` … `ONE_DAY`) | `/api/v3/brokerage/products/BTC-USD/candles` | `/api/v3/brokerage/market/products/BTC-USD/candles` |
| Recent trades | `/api/v3/brokerage/products/BTC-USD/ticker` | `/api/v3/brokerage/market/products/BTC-USD/ticker` |
| Accounts / balances | `/api/v3/brokerage/accounts` | – |
| Portfolios | `/api/v3/brokerage/portfolios` | – |
| **Your fee tier** | `/api/v3/brokerage/transaction_summary` (`fee_tier.maker_fee_rate/taker_fee_rate`) | – |
| Key permissions | `/api/v3/brokerage/key_permissions` | – |
| Server time | – | `/api/v3/brokerage/time` |

**The BTC-USD product:** base BTC, quote USD. Minimums and increments are read from the product endpoint at startup (`base_min_size`, `base_increment`, `quote_min_size`, `price_increment`). If the endpoint can't be reached, a clearly labelled FALLBACK spec is used and shown in the run summary.

---

## 4. WebSocket feeds

- **URL:** `wss://advanced-trade-ws.coinbase.com`.
- **Subscribe:** one message per channel: `{"type":"subscribe","product_ids":["BTC-USD"],"channel":"<ch>"}`. It must be sent within 5 s of connecting.
- **Channels:**

| Channel | Use |
|---|---|
| `heartbeats` | Keeps the connection alive on quiet markets |
| `level2` → messages on `l2_data` | `snapshot` then `update` events with `{side: bid/offer, price_level, new_quantity}`. `new_quantity` is the new absolute size, and 0 removes the level |
| `market_trades` | Trade prints; these drive maker fills |
| `ticker` | Best bid/ask + last price |

- **Integrity:**
  - `sequence_num` is checked on every message. On a gap, the book is cleared and the client resubscribes to get a fresh snapshot.
  - 30 s with no messages triggers a reconnect.
  - Connection errors retry with backoff.
  - Messages can be recorded and replayed (`--replay file.jsonl`).

---

## 5. Fee handling

- **Preferred:** your account's actual rates from `/transaction_summary`, loaded at startup when credentials exist.
- **Fallback:** `0.50% maker / 0.90% taker`, labelled **"DEFAULT, UNCONFIRMED"** everywhere it appears. It is the US entry tier according to third-party summaries; see VENUE_EXECUTION_RESEARCH.md.
- **Charging:** fee = rate × fill notional, charged in USD on every paper fill. A BUY reserves `notional × (1 + fee rate)` in USD while the order is open.
- **Tiers:** your tier changes with 30-day volume. The paper engine uses the rate loaded at startup and doesn't simulate tier changes.

## 6. Spread measurement

`SpreadMonitor` samples the live L2 book (≤ 1 per second) and records:
- quoted spread in bps: `(ask − bid) / mid × 10⁴`;
- the cost of an immediate taker **BUY** and **SELL** of **$250** and **$500**, walking the actual book depth, in bps vs mid. That is half-spread plus depth impact.

It writes `spreads.csv` and reports median, p90 and max in `summary.json`. Once enough live sessions exist, these **measured** values replace the "ASSUMED" spread/slippage scenarios in NEW_STRATEGY_RESEARCH_PLAN.md.

---

## 7. Simulated execution methodology (`execution/paper_engine.py`)

| Feature | Model |
|---|---|
| **Clock** | Exchange event timestamps (live or replay), so latency works the same in both |
| **Latency** | Orders become active `latency_ms` after submission (default 250 ms, `--latency-ms`). Taker orders execute against the book **at activation**, so any drift during the latency window shows up as slippage |
| **Taker entry/exit** (MARKET) | Sweep the opposite side of the current L2 book (VWAP), then apply `--extra-slippage-bps` adversely. If depth runs out, the fill is **partial** and the remainder is cancelled (IOC). BUY by USD amount; SELL by BTC amount |
| **Maker entry/exit** (post-only LIMIT) | **Rejected** if it would cross at activation. This is conservative: Coinbase docs mention repricing post-only orders, and that should be verified. Otherwise it **rests**: queue ahead = displayed size at its price. Trades **at** the price use up the queue first, then fill us (partial fills). A trade **through** the price means the level was exhausted, so the remainder fills. Queue ahead shrinks only when the displayed level shrinks. Stricter option: `maker_fill_model="trade_through_only"` |
| **Unfilled makers** | Optional time-to-live leads to **EXPIRED** ("unfilled" or "partially filled at expiry"). Cancel is also supported. Holds are released and the order is logged |
| **Bid/ask spread** | Taker fills happen at book prices, so the spread is paid inside the fill price. Maker fills are at the limit price |
| **Cost attribution per fill** | `shortfall = (fill − mid at submission) × qty × side`. Taker: `spread_cost` = touch − mid at fill (half-spread), and `slippage` = the rest (latency drift + depth + extra bps). Maker: `spread_cost` = shortfall (usually negative, i.e. earned), `slippage` = 0. Adverse selection shows up in P&L |
| **Insufficient balance** | Rejected ("insufficient USD" / "insufficient BTC"). Cash-only, long-only, no margin |
| **Minimum size / increments** | Size is rounded down to `base_increment`; buy prices are rounded down and sell prices up to `price_increment`. Orders below `base_min_size`, above `base_max_size`, or below `quote_min_size` are rejected |
| **Risk limits** | Max $500 notional per order, max 2 open orders, long-only, and new entries halt below −35% from peak equity |

**Trade records** (`trades.csv`, one row per round trip) contain:
- `timestamp` (exit), `entry_time`, `side` (LONG)
- `entry_price`, `exit_price` (fill VWAPs), `quantity`
- `gross_pnl`, `fees`, `spread_cost`, `slippage`, `net_pnl`
- `holding_seconds`, `entry_signal`, `exit_signal`
- `execution_type` (e.g. `MAKER/TAKER`)

`gross_pnl` is computed on fill prices, so spread and slippage are already inside it. They are reported as components and are **not** subtracted twice. `net_pnl = gross_pnl − fees`.

`orders.jsonl` logs every order's final state, including REJECTED, CANCELLED and EXPIRED makers.

**Known modelling limits:**
- Queue position is estimated from the displayed size; the true FIFO position is unknown.
- A maker order may get a fill that a real queue wouldn't give, if hidden or iceberg liquidity sits ahead.
- The fill model uses trade *prices* only. The meaning of the `side` field on Coinbase market trades hasn't been verified.
- Fee rounding follows no documented rule (rates are applied unrounded).

---

## 8. Safety controls

1. **PAPER_MODE gate.**
   - `require_paper_mode()` raises unless `PAPER_MODE` is `true` (case-insensitive, trimmed). It runs in `load_settings()`, `CoinbaseAdvancedClient.__init__`, and `PaperExecutionEngine.__init__`.
   - The CLI exits with code 2 and a message.
   - There is no "live" value and no override.
2. **No order code exists.**
   - `ExchangeClient.place_order / create_order / market_order / limit_order / preview_order / edit_order / cancel_order(s) / close_position / move_portfolio_funds / withdraw / deposit / convert` all raise **`LIVE ORDER EXECUTION DISABLED: research/paper mode only.`**
   - Any *unknown* client attribute that looks like trading or funding (`*order*`, `*withdraw*`, `*transfer*`, `*send*`, `*buy*`, `*sell*`, `*fund*`) raises the same error.
3. **Transport allowlist (deny by default).**
   - `ReadOnlyTransport` is the only REST network path. It permits **GET** only, to the paths in §3, and checks this **before** building auth headers or opening a connection.
   - `post/put/delete/patch` methods raise.
   - All order, convert, portfolio-mutation and payment paths are refused, including read-only order history, which isn't needed.
4. **Separation.** The paper engine and recorder don't import the exchange layer, `requests`, `websockets`, `socket` or `urllib`. A test checks this against the source's import tree.
5. **Key-permission check.** Keys with Transfer permission are refused, and Trade permission is refused by default.
6. **Secrets.**
   - Values come only from environment variables or a git-ignored `.env`.
   - `Credentials.__repr__` is redacted.
   - The log filter redacts the key, the secret, any JWT, `Bearer` tokens and PEM blocks.
   - The `.env` loader returns variable names only.
7. **No official SDK dependency.** `coinbase-advanced-py` includes order functions, so it's used only as a reference for auth and message formats, not installed as a dependency.

---

## 9. How to start paper trading

```bash
pip install -r requirements.txt
cp config/env.example .env        # optional: add a VIEW-ONLY CDP key locally; keep PAPER_MODE=true
PAPER_MODE=true python -m paper_trading --duration 300                   # market data + spread measurement
PAPER_MODE=true python -m paper_trading --duration 300 --demo-roundtrip  # + scripted execution smoke test
PAPER_MODE=true python -m paper_trading --replay tests/fixtures/ws_btcusd_synthetic.jsonl --demo-roundtrip
```

Outputs go to `paper_trading/records/<run-id>/` (git-ignored): `summary.json`, `spreads.csv`, `trades.csv` and `orders.jsonl`.

`--demo-roundtrip` runs a scripted **execution-path smoke test**, not a strategy:
1. Post-only buy at the best bid with a 20 s time-to-live.
2. If it isn't filled, a taker buy.
3. After a 5 s hold, a taker sell.

No strategy is attached until one is frozen under NEW_STRATEGY_RESEARCH_PLAN.md.

**Network note:** this cloud environment's policy currently blocks `api.coinbase.com` and `advanced-trade-ws.coinbase.com` (HTTP 403 from the egress proxy). To run live here, add both hosts to the environment's allowed network domains, or run locally.

---

## 10. How to verify that NO live orders can be placed

```bash
python -m pytest -q                               # 110 tests
python -m pytest -q tests/test_no_live_orders.py tests/test_paper_mode.py
grep -rn "brokerage/orders\|/orders\"" --include=*.py . | grep -v tests/   # only exchange/endpoints.py (the blocklist)
```

What the tests prove:
- Every forbidden method and path (order create/preview/edit/cancel/close, convert, portfolio create/move/edit/delete, legacy send/withdraw/deposit, order history) raises before any network access. A recording session shows **zero** calls.
- Every disabled client method, and any trading-like attribute name, raises the exact message.
- Client read methods issue only allowlisted GETs, and none contain `/orders`.
- No non-test code calls an HTTP write method, or mentions the orders endpoint outside the blocklist.
- No `LiveExecution*` class exists.
- A **full paper session** (replay + scripted round trip) runs with `socket.connect` and `requests.Session.request` sabotaged, so the paper path makes no network calls at all.
- PAPER_MODE: unset, `false`, `1`, `yes` or `live` all refuse, for the settings, the client, the engine and the CLI.
- With fake credentials set, no stdout, stderr, log or record file contains the key or the secret.
- `.env`, `.env.*`, `secrets/`, `credentials/`, `*.key`, `*.pem` and `paper_trading/records/` are git-ignored.
