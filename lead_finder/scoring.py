"""0-100 lead score and contactable-lead eligibility.

Weights: wallet qualification 25, attribution 25, holdings 15, contact
availability 15, contact verification 8, recent activity 7, private-person
fit 5. Unknown information earns 0 points; unknown holdings are never treated
as $0 (they simply score nothing for size).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

ATTRIBUTION_POINTS = {"High": 25, "Medium": 15, "Low": 5, "None": 0}
HOLDING_TIERS = [(1_000_000, 15), (250_000, 13), (100_000, 11), (25_000, 8), (5_000, 5), (0.01, 2)]


def score_class(score: int) -> str:
    if score >= 80:
        return "High"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Moderate"
    return "Low"


def days_since(ts: str | None, now: datetime | None = None) -> float | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, ((now or datetime.now(timezone.utc)) - dt).total_seconds() / 86400)


@dataclass
class ScoreInput:
    wallet_verified: bool              # provider returned valid data for this wallet
    asset_count: int | None
    is_contract: bool | None
    attribution: str
    holdings_usd: float | None
    holdings_status: str
    has_email: bool
    has_phone: bool
    email_verification: str | None     # Verified | Risky | Invalid | Unverified | Self-published | None
    last_active_at: str | None
    classification: str
    prominence: str


@dataclass
class Score:
    total: int
    classification: str
    breakdown: dict[str, int] = field(default_factory=dict)


def compute(s: ScoreInput, now: datetime | None = None) -> Score:
    b: dict[str, int] = {}
    qual = 0
    if s.wallet_verified:
        qual += 10
        if s.asset_count:
            qual += 8
        if s.is_contract is False:
            qual += 7
    b["wallet_qualification"] = qual
    b["attribution"] = ATTRIBUTION_POINTS.get(s.attribution, 0)

    hold = 0
    if s.holdings_usd is not None and s.holdings_status != "Holdings unavailable":
        hold = next((pts for floor, pts in HOLDING_TIERS if s.holdings_usd >= floor), 0)
    b["holdings"] = hold

    b["contact_availability"] = min(15, (10 if s.has_email else 0) + (8 if s.has_phone else 0))
    b["contact_verification"] = {"Verified": 8, "Self-published": 4, "Risky": 3}.get(s.email_verification or "", 0) \
        if s.has_email else 0

    age = days_since(s.last_active_at, now)
    b["recent_activity"] = 0 if age is None else 7 if age <= 7 else 5 if age <= 30 else 3 if age <= 90 else 1

    fit = 0
    if s.classification == "individual":
        fit = {"Low": 5, "Unknown": 3, "Medium": 1}.get(s.prominence, 0)
    b["individual_fit"] = fit

    total = max(0, min(100, sum(b.values())))
    return Score(total=total, classification=score_class(total), breakdown=b)


@dataclass
class Eligibility:
    contactable: bool
    reasons: list[str]


def eligibility(*, name: str | None, name_is_person: bool, address_valid: bool, chain_valid: bool,
                has_crypto_evidence: bool, wallet_attribution: str, identity_confidence: str,
                contact_self_published: bool, has_email: bool, has_phone: bool, classification: str,
                prominence: str, status: str, email_invalid: bool = False) -> Eligibility:
    """All nine contactable-lead requirements; every failure is reported, none silently dropped."""
    r: list[str] = []
    if not (name and name_is_person):
        r.append("No real individual name")
    if not address_valid:
        r.append("Invalid wallet address")
    if not chain_valid:
        r.append("Chain not verified by provider")
    if not has_crypto_evidence:
        r.append("No verified holdings or activity")
    strong = wallet_attribution == "High" or (wallet_attribution == "Medium" and contact_self_published)
    if not strong:
        r.append(f"Insufficient wallet attribution ({wallet_attribution})")
    if identity_confidence not in ("High", "Medium"):
        r.append(f"Insufficient identity confidence ({identity_confidence})")
    if not (has_email or has_phone):
        r.append("No publicly associated email or phone")
    if has_email and email_invalid and not has_phone:
        r.append("Email failed verification")
    if classification != "individual":
        r.append("Entity / company" if classification == "entity" else "Identity classification uncertain")
    if prominence == "High":
        r.append("Prominent public figure (excluded)")
    if status in ("suppressed", "do_not_contact", "deleted"):
        r.append(f"Lead status: {status}")
    return Eligibility(contactable=not r, reasons=r)
