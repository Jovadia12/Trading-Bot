"""Lead pipeline.

DISCOVERED -> QUALIFIED -> IDENTIFIED -> CONTACTABLE (-> SAVED -> CRM, via the API)

Every candidate wallet is persisted with the stage it reached and the reasons
it stopped there; nothing is silently dropped. Provider failures are recorded
as failures and never replaced by guessed data.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from urllib.parse import urlparse

from . import classification as cls
from .attribution import assess
from .chains import (CHAINS, chains_for_family, detect_families, get_chain, is_valid_address,
                     normalize_address)
from .config import Settings
from .providers.base import CONNECTED, NOT_CONFIGURED, NotConfigured, ProviderError
from .providers.enrichment import (APOLLO_ERROR, APOLLO_NOT_CONFIGURED, APOLLO_SUCCESS, HUNTER_ERROR,
                                   HUNTER_FOUND, HUNTER_NOT_CONFIGURED, ApolloClient, HunterClient)
from .providers.ens import EnsProfile, EnsResolver
from .providers.profiles import GithubClient, GithubProfile, WebsiteChecker, github_login_from_record
from .providers.wallet import Activity, Holdings, ProviderLabel, WalletDataProvider
from .scoring import ScoreInput, compute, eligibility
from .security import iso
from .tenancy import FirmRepository

GENERIC_HOSTS = {"github.com", "github.io", "medium.com", "substack.com", "linktr.ee", "twitter.com", "x.com",
                 "linkedin.com", "notion.site", "gmail.com", "mirror.xyz", "warpcast.com", "t.me", "youtube.com",
                 "bio.link", "carrd.co", "gitlab.com", "vercel.app", "netlify.app", "ens.domains", "eth.limo",
                 "eth.link", "instagram.com", "facebook.com", "tiktok.com", "about.me", "wordpress.com"}
_ENS_RE = re.compile(r"^[a-z0-9\-_.]+\.eth$", re.IGNORECASE)
QUALIFY_KEYS = ("chain", "min_value", "max_value", "min_activity", "min_assets")


# ------------------------------------------------------------ provider status
class ProviderStatusStore:
    """Global provider health (config-level; contains no tenant data)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record(self, provider: str, status: str, message: str | None = None) -> None:
        self.conn.execute(
            """INSERT INTO provider_status(provider, status, message, checked_at) VALUES (?,?,?,?)
               ON CONFLICT(provider) DO UPDATE SET status=excluded.status, message=excluded.message,
                                                   checked_at=excluded.checked_at""",
            (provider, status, (message or "")[:300] or None, iso()))

    def chain_success(self, provider: str, chain: str) -> None:
        self.conn.execute(
            """INSERT INTO provider_chain_support(provider, chain, last_success_at) VALUES (?,?,?)
               ON CONFLICT(provider, chain) DO UPDATE SET last_success_at=excluded.last_success_at""",
            (provider, chain, iso()))

    def chain_error(self, provider: str, chain: str, error: str) -> None:
        self.conn.execute(
            """INSERT INTO provider_chain_support(provider, chain, last_error, last_error_at) VALUES (?,?,?,?)
               ON CONFLICT(provider, chain) DO UPDATE SET last_error=excluded.last_error,
                                                         last_error_at=excluded.last_error_at""",
            (provider, chain, error[:200], iso()))

    def all(self) -> dict[str, dict]:
        return {r["provider"]: dict(r) for r in self.conn.execute("SELECT * FROM provider_status")}

    def verified_chains(self, provider: str) -> list[str]:
        rows = self.conn.execute("SELECT chain FROM provider_chain_support WHERE provider=? AND last_success_at "
                                 "IS NOT NULL ORDER BY chain", (provider,)).fetchall()
        return [r["chain"] for r in rows if r["chain"] in CHAINS]


@dataclass
class Providers:
    wallet: WalletDataProvider
    ens: EnsResolver
    github: GithubClient
    website: WebsiteChecker
    apollo: ApolloClient
    hunter: HunterClient

    def all(self) -> list:
        return [self.wallet, self.ens, self.github, self.website, self.apollo, self.hunter]


# -------------------------------------------------------------- query parsing
@dataclass
class ParsedQuery:
    wallets: list[tuple[str, str]] = field(default_factory=list)    # (chain, address)
    ens_names: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)


def parse_query(query: str, chain_filter: str | None) -> ParsedQuery:
    p = ParsedQuery()
    for raw in re.split(r"[\s,]+", (query or "").strip()):
        if not raw:
            continue
        if raw.lower().startswith("token:"):
            p.tokens.append(raw.split(":", 1)[1])
            continue
        if _ENS_RE.match(raw):
            p.ens_names.append(raw.lower())
            continue
        families = detect_families(raw)
        if raw.startswith("0x") and len(raw) == 42 and not families:
            p.invalid.append(raw)
            continue
        if families:
            fam = families[0]
            chain_info = get_chain(chain_filter)
            if chain_info and chain_info.family == fam:
                p.wallets.append((chain_info.key, raw))
            elif fam == "evm":
                p.wallets.append(("ethereum", raw))
            else:
                p.wallets.append((chains_for_family(fam)[0], raw))
            continue
        p.keywords.append(raw)
    return p


def cache_key(query: str, filters: dict) -> str:
    parsed = parse_query(query, filters.get("chain"))
    basis = {"wallets": sorted(f"{c}:{a.lower()}" for c, a in parsed.wallets),
             "ens": sorted(parsed.ens_names), "tokens": sorted(parsed.tokens),
             "keywords": sorted(k.lower() for k in parsed.keywords),
             "filters": {k: filters.get(k) for k in sorted(filters) if filters.get(k) is not None and filters.get(k) != "" and filters.get(k) is not False}}
    return hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()[:32]


# ------------------------------------------------------------------- run report
class RunReport:
    def __init__(self) -> None:
        self.providers: dict[str, dict] = {}
        self.failures: list[dict] = []

    def ok(self, provider: str) -> None:
        self.providers.setdefault(provider, {"calls": 0, "errors": {}})["calls"] += 1

    def error(self, provider: str, status: str, message: str | None = None) -> None:
        entry = self.providers.setdefault(provider, {"calls": 0, "errors": {}})
        entry["calls"] += 1
        entry["errors"][status] = entry["errors"].get(status, 0) + 1
        entry["last_error"] = f"{status}: {message}" if message else status

    def as_dict(self) -> dict:
        return {"providers": self.providers, "failures": self.failures[:50]}


def _personal_domain(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url if "://" in url else f"https://{url}").hostname or ""
    host = host.lower().removeprefix("www.")
    if not host or "." not in host or any(host == g or host.endswith("." + g) for g in GENERIC_HOSTS):
        return None
    return host


def _email_verification_from_apollo(status: str | None) -> str:
    return {"verified": "Verified", "extrapolated": "Risky", "likely to engage": "Risky"}.get(
        (status or "").lower(), "Unverified")


def _email_verification_from_hunter(status: str | None) -> str | None:
    return {"valid": "Verified", "invalid": "Invalid", "disposable": "Invalid", "accept_all": "Risky",
            "webmail": "Risky", "unknown": "Risky"}.get((status or "").lower())


def _linkedin_key(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url, re.IGNORECASE)
    return m.group(1).lower() if m else url.strip().strip("/").lower()


# ------------------------------------------------------------------ pipeline
class LeadPipeline:
    def __init__(self, repo: FirmRepository, providers: Providers, status: ProviderStatusStore, settings: Settings):
        self.repo = repo
        self.p = providers
        self.status = status
        self.settings = settings
        self.report = RunReport()

    # -- provider call wrapper: records status, never invents a fallback value
    def _call(self, provider_name: str, fn, *args, chain: str | None = None, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except NotConfigured:
            self.report.error(provider_name, NOT_CONFIGURED)
            self.status.record(provider_name, NOT_CONFIGURED)
            return None, NOT_CONFIGURED
        except ProviderError as exc:
            self.report.error(provider_name, exc.status, exc.message)
            self.status.record(provider_name, exc.status, exc.message)
            if chain:
                self.status.chain_error(provider_name, chain, f"{exc.status}: {exc.message}")
            return None, exc.status
        self.report.ok(provider_name)
        self.status.record(provider_name, CONNECTED)
        return result, CONNECTED

    # ------------------------------------------------------------- search
    def run_search(self, query: str, filters: dict) -> dict:
        key = cache_key(query, filters)
        search_id = self.repo.create_search(query, filters, key)
        parsed = parse_query(query, filters.get("chain"))
        counts = {"discovered": 0, "qualified": 0, "identified": 0, "contactable": 0,
                  "unattributed": 0, "failed": 0, "reused": 0}

        # 1) Re-surface untouched leads from earlier runs of this search first.
        reused = self.repo.reusable_leads(key)
        for lead_id in reused:
            self.repo.add_search_result(search_id, lead_id, "cached")
        counts["reused"] = len(reused)

        # 2) Fresh candidates.
        candidates = self._candidates(parsed, filters)
        seen_lead_ids = set(reused)
        for chain, address, source, label in candidates:
            outcome = self.process_wallet(chain, address, source, label, filters)
            if outcome is None:
                counts["failed"] += 1
                continue
            lead_id, stage, attribution_conf, failed = outcome
            counts["discovered"] += 1
            if failed:
                counts["failed"] += 1
            if stage in ("qualified", "identified", "contactable"):
                counts["qualified"] += 1
                if attribution_conf in ("None", "Low"):
                    counts["unattributed"] += 1
            if stage in ("identified", "contactable"):
                counts["identified"] += 1
            if stage == "contactable":
                counts["contactable"] += 1
            if lead_id not in seen_lead_ids:
                self.repo.add_search_result(search_id, lead_id, "fresh")
                seen_lead_ids.add(lead_id)

        for raw in parsed.invalid:
            self.report.failures.append({"input": raw[:80], "reason": "Invalid wallet address checksum"})
        status = "completed"
        if not candidates and not reused:
            status = "no_results"
        self.repo.finish_search(search_id, counts, self.report.as_dict(), status)
        return {"search_id": search_id, "counts": counts, "status": status, "report": self.report.as_dict()}

    def _candidates(self, parsed: ParsedQuery, filters: dict) -> list[tuple[str, str, str, str | None]]:
        limit = max(1, min(int(filters.get("max_candidates") or self.settings.max_candidates), 200))
        out: list[tuple[str, str, str, str | None]] = []
        seen: set[tuple[str, str]] = set()

        def add(chain: str, address: str, source: str, label: str | None = None) -> None:
            if not get_chain(chain):
                self.report.failures.append({"input": address[:80], "reason": f"Unsupported chain {chain}"})
                return
            k = (chain, normalize_address(chain, address) if is_valid_address(chain, address) else address)
            if k not in seen and len(out) < limit:
                seen.add(k)
                out.append((chain, address, source, label))

        for chain, address in parsed.wallets:
            add(chain, address, "Direct wallet lookup")
        for name in parsed.ens_names:
            resolved, _ = self._call(self.p.ens.name, self.p.ens.resolve_name, name)
            if resolved:
                add("ethereum", resolved, f"ENS name lookup ({name})")
            else:
                self.report.failures.append({"input": name, "reason": "ENS name did not resolve"})

        explicit = bool(parsed.wallets or parsed.ens_names)
        if explicit:
            return out
        chain_filter = filters.get("chain")
        if parsed.tokens:
            seeds = {(chain_filter or "ethereum"): parsed.tokens}
        else:
            seeds = {c: t for c, t in self.settings.seed_tokens.items() if not chain_filter or c == chain_filter}
        if not seeds:
            self.report.failures.append({"input": chain_filter or "", "reason": "No discovery seed configured for chain"})
        per_seed = max(1, limit // max(1, sum(len(t) for t in seeds.values())))
        for chain, tokens in seeds.items():
            for token in tokens:
                found, _ = self._call(self.p.wallet.name, self.p.wallet.discover, chain, token, 30, per_seed,
                                      chain=chain)
                if found:
                    self.status.chain_success(self.p.wallet.name, chain)
                for w in found or []:
                    add(w.chain, w.address, w.source, w.provider_label)
        return out

    # ------------------------------------------------------- single wallet
    def process_wallet(self, chain: str, address: str, source: str, provider_label: str | None,
                       filters: dict) -> tuple[int, str, str, bool] | None:
        chain_info = get_chain(chain)
        if chain_info is None:
            return None
        valid = is_valid_address(chain, address)
        if not valid:
            self.report.failures.append({"input": address[:80], "reason": f"Invalid {chain_info.name} address"})
            return None
        norm = normalize_address(chain, address)
        existing = self.repo.find_lead_by_wallet(chain, norm)
        prior_status = existing["status"] if existing else "new"
        reasons: list[str] = []
        provider_failed = False

        # ---- wallet data (Nansen)
        wallet_name = self.p.wallet.name
        holdings: Holdings | None
        holdings, h_status = self._call(wallet_name, self.p.wallet.holdings, chain, norm, chain=chain)
        if holdings is None:
            provider_failed = True
            reasons.append(f"Wallet data unavailable ({wallet_name}: {h_status})")
        else:
            self.status.chain_success(wallet_name, chain)
        activity: Activity | None = None
        labels: list[ProviderLabel] = []
        if holdings is not None:
            activity, _ = self._call(wallet_name, self.p.wallet.activity, chain, norm,
                                     self.settings.activity_window_days, chain=chain)
            labels, _ = self._call(wallet_name, self.p.wallet.labels, chain, norm, chain=chain)
            labels = labels or []
        if provider_label and not any(l.label == provider_label for l in labels):
            labels.append(ProviderLabel(label=provider_label, category=None))
        label_pairs = [(l.label, l.category) for l in labels]

        # ---- attribution evidence (self-published only)
        ens: EnsProfile | None = None
        is_contract: bool | None = None
        github: GithubProfile | None = None
        website_hits: list[str] = []
        if chain_info.family == "evm":
            is_contract, _ = self._call(self.p.ens.name, self.p.ens.is_contract, norm)
            ens, _ = self._call(self.p.ens.name, self.p.ens.reverse_lookup, norm)
        if ens:
            login = github_login_from_record(ens.records.get("com.github"))
            if login:
                github, _ = self._call(self.p.github.name, self.p.github.user, login)
            needles = [norm, ens.name]
            for site in [ens.records.get("url"), github.blog if github else None]:
                if site and not website_hits:
                    hits, _ = self._call(self.p.website.name, self.p.website.page_mentions, site, needles)
                    website_hits = hits or []
        attribution = assess(chain=chain, address=norm, ens=ens, github=github,
                             website_hits=website_hits, is_contract=is_contract)

        classification, class_reasons = cls.classify(
            name=attribution.full_name, ens_name=ens.name if ens else None,
            github_type=github.type if github else None, labels=label_pairs, is_contract=is_contract)
        prominence, prom_reasons = cls.assess_prominence(
            github_followers=github.followers if github else None, labels=label_pairs,
            bio=github.bio if github else (ens.records.get("description") if ens else None))

        # ---- qualification
        value = holdings.estimated_value_usd if holdings else None
        trades = activity.trade_count if activity else None
        has_crypto_evidence = bool(holdings and ((value or 0) > 0 or holdings.asset_count > 0)) or bool(trades)
        qualified = holdings is not None and has_crypto_evidence
        if holdings is not None and not has_crypto_evidence:
            reasons.append("No holdings or recent activity reported by provider")
        if qualified:
            q_fail = self._qualification_failures(chain, value, holdings, trades, filters)
            if q_fail:
                qualified = False
                reasons.extend(q_fail)

        identified = (qualified and classification == cls.INDIVIDUAL
                      and attribution.identity_confidence in ("High", "Medium")
                      and attribution.wallet_confidence in ("High", "Medium"))

        # ---- enrichment (only for already self-identified individuals)
        contacts: list[dict] = []
        ident_extra: dict = {}
        apollo_status = hunter_status = None
        identity_conf = attribution.identity_confidence
        enrichment_ran = False
        if identified and prominence != "High" and prior_status not in ("suppressed", "do_not_contact", "deleted"):
            enrichment_ran = True
            contacts, ident_extra, apollo_status, hunter_status, identity_conf = self._enrich(
                attribution, ens, github, identity_conf)

        usable = [c for c in contacts if c["kind"] == "email" and c["verification"] != "Invalid"]
        order = {"Verified": 0, "Self-published": 1, "Risky": 2, "Unverified": 3}
        usable.sort(key=lambda c: (order.get(c["verification"], 9), not c["self_published"]))
        best_email = usable[0] if usable else None
        phones = [c for c in contacts if c["kind"] == "phone"]
        best_phone = phones[0] if phones else None
        email_invalid = any(c["kind"] == "email" and c["verification"] == "Invalid" for c in contacts) and not best_email
        contact_self_published = bool(best_email and best_email["self_published"])
        linkedin = ident_extra.get("linkedin") or (ens.records.get("com.linkedin") if ens else None)

        elig = eligibility(
            name=attribution.full_name, name_is_person=cls.looks_like_person_name(attribution.full_name),
            address_valid=valid, chain_valid=holdings is not None, has_crypto_evidence=has_crypto_evidence,
            wallet_attribution=attribution.wallet_confidence, identity_confidence=identity_conf,
            contact_self_published=contact_self_published, has_email=best_email is not None,
            has_phone=best_phone is not None, classification=classification, prominence=prominence,
            status=prior_status, email_invalid=email_invalid)

        if elig.contactable and qualified:
            stage, category = "contactable", "contactable"
        else:
            stage = "identified" if identified else "qualified" if qualified else "discovered"
            category = "opportunity"
            reasons = reasons + [r for r in elig.reasons if r not in reasons]

        score = compute(ScoreInput(
            wallet_verified=holdings is not None, asset_count=holdings.asset_count if holdings else None,
            is_contract=is_contract, attribution=attribution.wallet_confidence, holdings_usd=value,
            holdings_status=holdings.holdings_status if holdings else "Holdings unavailable",
            has_email=best_email is not None, has_phone=best_phone is not None,
            email_verification=best_email["verification"] if best_email else None,
            last_active_at=activity.last_active_at if activity else None,
            classification=classification, prominence=prominence))

        funding = "Unknown"
        if holdings is not None:
            funding = (f"Observed: active DeFi debt ({', '.join(holdings.debt_positions[:3])})"
                       if holdings.debt_positions else "None observed")

        # ---- persist (one transaction per wallet)
        with self.repo.tx():
            wallet_id, _ = self.repo.upsert_wallet({
                "chain": chain, "address": norm, "display_address": address.strip(),
                "estimated_portfolio_value": value,
                "holdings_status": holdings.holdings_status if holdings else "Holdings unavailable",
                "native_balance": holdings.native_balance if holdings else None,
                "native_symbol": chain_info.native_symbol,
                "asset_count": holdings.asset_count if holdings else None,
                "token_holdings_json": json.dumps([t.__dict__ for t in holdings.tokens[:50]]) if holdings else None,
                "recent_activity_count": trades, "last_active_at": activity.last_active_at if activity else None,
                "activity_json": json.dumps({"window_days": activity.window_days, "truncated": activity.truncated,
                                             "recent": activity.recent, "source": activity.source}) if activity else None,
                "debt_positions_json": json.dumps(holdings.debt_positions) if holdings else None,
                "provider_labels_json": json.dumps([{"label": l, "category": c} for l, c in label_pairs]),
                "is_contract": None if is_contract is None else int(is_contract),
                "source": source, "provider_status": h_status,
            })
            identity_id = None
            if ens is not None:
                identity_id = self.repo.upsert_identity({
                    "full_name": attribution.full_name, "company": ident_extra.get("company") or (
                        github.company.lstrip("@").strip() if github and github.company else None),
                    "title": ident_extra.get("title"), "linkedin": linkedin,
                    "city": ident_extra.get("city"), "state": ident_extra.get("state"),
                    "country": ident_extra.get("country"), "zip": None,
                    "location_text": (github.location if github else None) or ens.records.get("location"),
                    "industry": ident_extra.get("industry"), "company_size": ident_extra.get("company_size"),
                    "company_founded_year": ident_extra.get("company_founded_year"),
                    "company_domain": ident_extra.get("company_domain"), "ens_name": ens.name,
                    "github_login": github.login if github else None, "website": ens.records.get("url"),
                    "classification": classification, "classification_reasons_json": json.dumps(class_reasons),
                    "identity_confidence": identity_conf, "identity_source": attribution.identity_source,
                    "public_prominence": prominence, "prominence_reasons_json": json.dumps(prom_reasons),
                }, [c["value"] for c in contacts if c["kind"] == "email"])
                for c in contacts:
                    self.repo.upsert_contact(identity_id, c["kind"], c["value"], c["source"],
                                             c["self_published"], c["verification"])
            lead_fields = {
                "identity_id": identity_id, "name": attribution.full_name,
                "title": ident_extra.get("title"),
                "company": ident_extra.get("company") or (github.company.lstrip("@").strip()
                                                          if github and github.company else None),
                "email": best_email["value"].lower() if best_email else None,
                "phone": best_phone["value"] if best_phone else None, "linkedin": linkedin,
                "wallet_address": address.strip(), "chain": chain, "estimated_holdings_usd": value,
                "holdings_status": holdings.holdings_status if holdings else "Holdings unavailable",
                "recent_activity": trades, "last_active_at": activity.last_active_at if activity else None,
                "asset_count": holdings.asset_count if holdings else None,
                "identity_confidence": identity_conf,
                "wallet_attribution_confidence": attribution.wallet_confidence,
                "identity_source": attribution.identity_source, "wallet_source": attribution.wallet_source,
                "contact_source": ", ".join(sorted({c["source"] for c in [best_email, best_phone] if c})) or None,
                "email_verification_status": best_email["verification"] if best_email else None,
                "public_prominence": prominence, "classification": classification, "funding_interest": funding,
                "apollo_status": apollo_status, "hunter_status": hunter_status, "stage": stage,
                "category": category, "opportunity_reasons_json": json.dumps(reasons if category != "contactable" else []),
                "lead_score": score.total, "score_class": score.classification,
            }
            lead_id, created = self.repo.upsert_lead(wallet_id, lead_fields)
            sources = [("wallet", wallet_name, "", source)]
            if holdings is not None:
                sources.append(("wallet", wallet_name, "", "profiler/address/current-balance"))
            if activity is not None:
                sources.append(("wallet", wallet_name, "", activity.source))
            sources += [(e.kind, e.provider, e.url, e.detail) for e in attribution.evidence]
            sources += [("classification", "Lead Finder", "", r) for r in class_reasons]
            sources += [("contact", c["source"], "", f"{c['kind']} ({c['verification']})") for c in contacts]
            self.repo.add_sources(lead_id, sources)
            self.repo.record_score(lead_id, score.total, score.classification, score.breakdown)
            self.repo.audit("lead_discovered" if created else "lead_updated", lead_id,
                            f"stage={stage} chain={chain}")
            if enrichment_ran:
                self.repo.audit("lead_enriched", lead_id, f"apollo={apollo_status} hunter={hunter_status}")
        return lead_id, stage, attribution.wallet_confidence, provider_failed

    def _qualification_failures(self, chain: str, value: float | None, holdings: Holdings,
                                trades: int | None, f: dict) -> list[str]:
        out = []
        if f.get("chain") and f["chain"] != chain:
            out.append(f"Chain {chain} outside filter")
        if f.get("min_value") is not None:
            if value is None:
                out.append("Holdings unavailable; cannot confirm minimum portfolio value")
            elif value < float(f["min_value"]):
                out.append(f"Portfolio below minimum (${value:,.0f} < ${float(f['min_value']):,.0f})")
        if f.get("max_value") is not None and value is not None and value > float(f["max_value"]):
            out.append(f"Portfolio above maximum (${value:,.0f})")
        if f.get("max_value") is not None and value is None:
            out.append("Holdings unavailable; cannot confirm maximum portfolio value")
        if f.get("min_activity") is not None:
            if trades is None:
                out.append("Activity unavailable; cannot confirm minimum activity")
            elif trades < int(f["min_activity"]):
                out.append(f"Recent activity below minimum ({trades} trades)")
        if f.get("min_assets") is not None and holdings.asset_count < int(f["min_assets"]):
            out.append(f"Asset count below minimum ({holdings.asset_count})")
        return out

    def _enrich(self, attribution, ens: EnsProfile | None, github: GithubProfile | None, identity_conf: str):
        contacts: list[dict] = []
        extra: dict = {}
        first, last = cls.split_name(attribution.full_name)

        def add(kind, value, source, self_published, verification):
            value = value.strip()
            key = value.lower() if kind == "email" else re.sub(r"\D", "", value)
            for c in contacts:
                ck = c["value"].lower() if c["kind"] == "email" else re.sub(r"\D", "", c["value"])
                if c["kind"] == kind and ck == key:
                    return
            contacts.append({"kind": kind, "value": value, "source": source,
                             "self_published": self_published, "verification": verification})

        if ens and ens.records.get("email") and "@" in ens.records["email"]:
            add("email", ens.records["email"], "ENS record (wallet owner)", True, "Self-published")
        if github and github.email:
            add("email", github.email, "GitHub public profile", attribution.github_backlink, "Unverified")

        # Apollo (primary enrichment)
        linkedin_record = ens.records.get("com.linkedin") if ens else None
        if linkedin_record and "linkedin.com" not in linkedin_record:
            linkedin_record = f"https://www.linkedin.com/in/{linkedin_record.strip('/@')}"
        org = github.company.lstrip("@").strip() if github and github.company else None
        personal_domain = _personal_domain(ens.records.get("url") if ens else None) or _personal_domain(
            github.blog if github else None)
        apollo_res = None
        if not self.p.apollo.configured:
            apollo_status = APOLLO_NOT_CONFIGURED
            self.status.record(self.p.apollo.name, NOT_CONFIGURED)
        else:
            apollo_res = self.p.apollo.match_person(first, last, organization=org, linkedin_url=linkedin_record,
                                                    email=contacts[0]["value"] if contacts else None)
            apollo_status = apollo_res.status
            if apollo_res.status == APOLLO_ERROR:
                self.report.error(self.p.apollo.name, "Provider error", apollo_res.message)
                self.status.record(self.p.apollo.name, "Provider error", apollo_res.message)
            else:
                self.report.ok(self.p.apollo.name)
                self.status.record(self.p.apollo.name, CONNECTED)
        if apollo_res and apollo_res.status == APOLLO_SUCCESS:
            extra = {k: getattr(apollo_res, k) for k in ("title", "company", "company_domain", "company_size",
                                                         "company_founded_year", "industry", "linkedin", "city",
                                                         "state", "country")}
            if apollo_res.email:
                add("email", apollo_res.email, "Apollo", False, _email_verification_from_apollo(apollo_res.email_status))
            for phone in apollo_res.phones:
                add("phone", phone, "Apollo", False, "Unverified")
            if linkedin_record and _linkedin_key(apollo_res.linkedin) == _linkedin_key(linkedin_record):
                identity_conf = "High"  # Apollo confirms the LinkedIn profile the wallet owner published

        # Hunter fallback when Apollo is unavailable or returned no email
        hunter_status = None
        has_apollo_email = any(c["source"] == "Apollo" and c["kind"] == "email" for c in contacts)
        if not has_apollo_email:
            domain = extra.get("company_domain") or personal_domain
            if not self.p.hunter.configured:
                hunter_status = HUNTER_NOT_CONFIGURED
                self.status.record(self.p.hunter.name, NOT_CONFIGURED)
            elif not domain:
                hunter_status = "Not Found"
                self.report.failures.append({"input": "enrichment", "reason": "Hunter skipped: no company or personal domain"})
            else:
                h_res = self.p.hunter.find_email(first, last, domain)
                hunter_status = h_res.status
                if h_res.status == HUNTER_ERROR:
                    self.report.error(self.p.hunter.name, "Provider error", h_res.message)
                    self.status.record(self.p.hunter.name, "Provider error", h_res.message)
                else:
                    self.report.ok(self.p.hunter.name)
                    self.status.record(self.p.hunter.name, CONNECTED)
                if h_res and h_res.status == HUNTER_FOUND and h_res.email:
                    add("email", h_res.email, "Hunter", False,
                        _email_verification_from_hunter(h_res.verification) or "Unverified")

        # Verification of the emails we intend to use
        if self.p.hunter.configured:
            for c in contacts:
                if c["kind"] == "email" and c["verification"] in ("Unverified", "Self-published", "Risky"):
                    result, _ = self._call(self.p.hunter.name, self.p.hunter.verify_email, c["value"])
                    mapped = _email_verification_from_hunter(result)
                    if mapped and not (mapped == "Risky" and c["verification"] == "Self-published"):
                        c["verification"] = mapped
        return contacts, extra, apollo_status, hunter_status, identity_conf
