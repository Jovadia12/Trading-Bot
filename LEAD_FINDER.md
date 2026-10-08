# Lead Finder

Finds **individual** crypto holders who have **publicly linked a wallet to themselves** and **published a way to contact them**, as prospects for crypto-backed loans. It is built for fewer, better leads:

```
REAL PERSON + REAL WALLET + VERIFIED HOLDINGS/ACTIVITY + SELF-PUBLISHED ATTRIBUTION + PUBLIC CONTACT = CONTACTABLE LEAD
```

Nothing is fabricated. When a provider is missing or fails, the record shows that, e.g. `Holdings unavailable` or `Nansen: Insufficient credits`. No value is guessed.

## Run it

```bash
pip install -r requirements-lead-finder.txt
export NANSEN_API_KEY=... ETH_RPC_URL=... APOLLO_API_KEY=... HUNTER_API_KEY=...   # see lead_finder.env.example
echo 'a-long-password' | python3 -m lead_finder create-user --firm "Acme Lending" --email ops@acme.com --name "Ops"
python3 -m lead_finder serve --port 8060            # http://127.0.0.1:8060
# For local http:// only: LEAD_FINDER_COOKIE_SECURE=false
```

Tests: `python3 -m pytest tests/lead_finder -q`

## Pipeline

| Stage | Meaning |
|---|---|
| **Discovered** | Wallet from Nansen discovery (`tgm/who-bought-sold` on seed tokens), a pasted address, or an ENS name. |
| **Qualified** | Nansen returned valid data showing holdings or activity, and the wallet passed the crypto filters (chain, min/max value, activity, asset count). |
| **Identified** | An individual (not an entity) with a real name and Medium or High identity and wallet attribution. |
| **Contactable** | Meets all 9 requirements below. Shown in **Contactable Crypto Leads**. |
| **Saved → CRM** | A user saved the lead, then optionally moved it to the CRM stage. |

Every other record goes to **Crypto Opportunities** with the reasons it isn't contactable: unattributed wallets, entities, public figures, no contact, failed providers. Nothing is silently dropped.

**Contactable requires all of:**
1. A real individual name.
2. A valid address (EIP-55, base58check, bech32/bech32m, Solana 32-byte).
3. A chain verified by the provider.
4. Holdings or activity evidence.
5. Strong attribution.
6. A public email or phone.
7. Identity confidence of Medium or higher.
8. Not an entity.
9. Not a prominent public figure.

## Wallet → person attribution

The system never treats a name and an address on the same page as evidence. It accepts only evidence the wallet owner published:

- **ENS primary name.** A reverse record can only be set by the address itself. It must forward-resolve back to the same address, or it is ignored.
- **ENS text records** (`com.github`, `url`, `com.linkedin`, `email`, `name`). These are set by the name's owner.
- **Back-link.** The linked GitHub profile, or the owner's website, mentions the wallet or ENS name.

| Wallet attribution | Evidence |
|---|---|
| High | ENS primary name and a profile or site that links back. |
| Medium | ENS primary name and owner-set profile records (one-way). |
| Low | ENS name only. |
| None | No self-published evidence. |

A Medium-attribution wallet is contactable only when the email itself was self-published by the wallet owner, i.e. an ENS `email` record. Contacting that address reaches whoever controls the wallet.

ENS records live on Ethereum. For other EVM chains, attribution is kept only when the address has no contract code on mainnet. Such an address is an EOA, so the same key controls it on every EVM chain. Otherwise attribution drops one level.

There is no ENS-equivalent self-attribution source wired up for Solana, Bitcoin or Tron yet. Those wallets are qualified from Nansen data but stay in Opportunities. The attribution sources sit behind `attribution.assess()`, so a source such as SNS can be added there.

Contact enrichment (Apollo, then Hunter) runs **only for individuals who already identified themselves**. It is never used to unmask an anonymous wallet.

## Scoring (0–100)

| Component | Points |
|---|---|
| Wallet qualification | 25 |
| Attribution | 25 |
| Holdings | 15 |
| Contact availability | 15 |
| Contact verification | 8 |
| Recent activity | 7 |
| Private-person fit | 5 |

Unknown information scores 0, and unknown holdings are never treated as $0. Bands: High 80+, Good 60–79, Moderate 40–59, Low under 40. A $8k wallet with strong attribution and a verified email outranks a $50M anonymous wallet.

## Providers

| Provider | Used for | Per-lead statuses |
|---|---|---|
| **Nansen** (`api.nansen.ai/api/v1`, `apiKey` header) | Discovery, `profiler/address/current-balance`, `profiler/dex-trades`, `profiler/address/labels` | Connected / Insufficient credits / Invalid API key / Rate limited / Access denied / Provider error / Not Configured |
| **ENS** via `ETH_RPC_URL` | Primary name, text records, contract check | (same) |
| **GitHub** public API | Name, company, location, back-link | (same) |
| **Apollo** `people/match` | Title, company, industry, size, email, phone | Success / No Match / Provider Error / Not Configured |
| **Hunter** `email-finder`, `email-verifier` | Fallback email; verification | Found / Not Found / Provider Error / Not Configured |

Nansen sits behind `providers/wallet.py::WalletDataProvider`, so another provider can be dropped in without touching the lead system. Debt tokens (Aave `variableDebt*`, etc.) are subtracted as liabilities, not counted as holdings. Their presence also sets **Funding interest: Observed**. The chain filter lists only chains Nansen has actually returned data for.

## Tenancy and security

- **Tenant scoping.** Every table is scoped by `firm_id`. Child rows reference parents through composite `(firm_id, id)` foreign keys, so the database itself rejects cross-firm references. All access goes through `FirmRepository`, whose `firm_id` comes from the server-side session, never the request. A request containing `firm_id` is rejected with 422.
- **Login is email and password only.** Sessions are opaque, cookies are HttpOnly and SameSite=Strict, and mutations require a custom CSRF header. Wallets are lead data only: there is no wallet login and no wallet column on users.
- **Masking.** Phone numbers are masked in lists and shown in full only in the lead detail view. Audit entries hold ids and actions, never emails or phones.
- **Website fetches.** Only public `https` hosts are fetched, redirects are re-validated, and pages are capped at 512 KB. Known limitation: the DNS check and the fetch resolve separately, so DNS rebinding is not fully prevented.

## Layout

```
lead_finder/
  chains.py          chain registry + address validation
  db.py              schema
  security.py        auth/sessions
  tenancy.py         firm-scoped repository, dedup, saved leads, audit
  pipeline.py        stages, enrichment orchestration, search caching
  attribution.py     evidence → confidence
  classification.py  person/entity, prominence
  scoring.py         score + eligibility
  providers/         nansen, ens, profiles (GitHub/website), enrichment (Apollo/Hunter)
  api.py             FastAPI routes
  static/            UI (DCCN design system)
tests/lead_finder/   unit + end-to-end tests; providers simulated at the HTTP layer
```
