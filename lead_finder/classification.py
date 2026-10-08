"""Individual-vs-entity classification and public-prominence assessment.

Keyword screening is one signal among several (provider label categories,
GitHub account type, contract code, personal-name shape). A record is only
"individual" when there is positive evidence of a person and no entity signal;
anything else is "entity" or "uncertain", and neither reaches the main list.
"""
from __future__ import annotations

import re

ENTITY_KEYWORDS = [
    "inc", "llc", "ltd", "limited", "labs", "capital", "fund", "funds", "ventures", "dao", "protocol",
    "foundation", "exchange", "finance", "partners", "holdings", "corp", "corporation", "company",
    "co", "gmbh", "plc", "ag", "sa", "treasury", "multisig", "market maker", "trading firm",
    "bank", "group", "technologies", "network", "association", "institute", "studio", "studios",
    "team", "official", "bot", "vault", "pool", "bridge", "router", "deployer", "hot wallet",
    "cold wallet", "custody", "investments", "asset management", "research", "collective",
]
_ENTITY_RE = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(k) for k in ENTITY_KEYWORDS) + r")(?![a-z0-9])")

ENTITY_LABEL_CATEGORIES = {
    "fund", "funds", "cex", "dex", "defi", "smart contract", "contract", "exchange", "market maker",
    "institution", "institutional", "dao", "bridge", "token", "protocol", "treasury", "company",
    "entity", "nft marketplace", "custodian", "mev", "bot", "deployer", "vc",
}
FAME_KEYWORDS = re.compile(r"(?<![a-z])(celebrity|influencer|kol|politician|public figure|famous|athlete|"
                           r"musician|actor|actress|government|senator|congress|president)(?![a-z])")
_NON_NAMES = {"anonymous", "anon", "crypto", "admin", "support", "unknown", "null", "test", "user"}
_NAME_TOKEN = re.compile(r"^[^\W\d_](?:[^\W\d_]|['\-.])*$", re.UNICODE)

INDIVIDUAL, ENTITY, UNCERTAIN = "individual", "entity", "uncertain"


def entity_keyword_hits(text: str | None) -> list[str]:
    if not text:
        return []
    return sorted({m.group(1) for m in _ENTITY_RE.finditer(text.lower())})


def looks_like_person_name(name: str | None) -> bool:
    if not name:
        return False
    name = name.strip()
    if len(name) > 60 or ".eth" in name.lower() or "@" in name:
        return False
    tokens = name.split()
    if not 2 <= len(tokens) <= 4:
        return False
    if any(not _NAME_TOKEN.match(t) for t in tokens):
        return False
    if any(t.lower().strip(".") in _NON_NAMES for t in tokens):
        return False
    # first and last tokens must be real words, not initials
    if len(tokens[0].strip(".")) < 2 or len(tokens[-1].strip(".")) < 2:
        return False
    return not entity_keyword_hits(name)


def split_name(name: str) -> tuple[str, str]:
    tokens = name.split()
    return tokens[0], tokens[-1]


def classify(*, name: str | None, ens_name: str | None, github_type: str | None,
             labels: list[tuple[str, str | None]], is_contract: bool | None) -> tuple[str, list[str]]:
    """Return (classification, reasons)."""
    entity_reasons: list[str] = []
    if github_type and github_type.lower() == "organization":
        entity_reasons.append("Linked GitHub account is an Organization")
    for field_name, text in (("name", name), ("ENS name", ens_name)):
        hits = entity_keyword_hits(text.replace(".eth", "") if text else text)
        if hits:
            entity_reasons.append(f"Entity keyword in {field_name}: {', '.join(hits)}")
    for label, category in labels:
        if category and category.strip().lower() in ENTITY_LABEL_CATEGORIES:
            entity_reasons.append(f"Provider label category '{category}'")
        hits = entity_keyword_hits(label)
        if hits:
            entity_reasons.append(f"Entity keyword in provider label '{label}'")
    if entity_reasons:
        return ENTITY, entity_reasons
    if is_contract:
        return UNCERTAIN, ["Address is a smart contract (multisig/protocol); owner cannot be confirmed"]
    if looks_like_person_name(name):
        return INDIVIDUAL, ["Personal name published by the wallet owner; no entity signals"]
    if name:
        return UNCERTAIN, ["Published name is not a recognisable personal name"]
    return UNCERTAIN, ["No identity published for this wallet"]


def assess_prominence(*, github_followers: int | None, labels: list[tuple[str, str | None]],
                      bio: str | None) -> tuple[str, list[str]]:
    """High | Medium | Low | Unknown. High-prominence people are kept out of the main list."""
    reasons: list[str] = []
    for label, category in labels:
        if FAME_KEYWORDS.search(f"{label} {category or ''}".lower()):
            reasons.append(f"Provider label suggests public figure: '{label}'")
    if bio and FAME_KEYWORDS.search(bio.lower()):
        reasons.append("Profile bio suggests public figure")
    if reasons:
        return "High", reasons
    if github_followers is None:
        return "Unknown", ["No prominence data"]
    if github_followers >= 10_000:
        return "High", [f"{github_followers:,} GitHub followers"]
    if github_followers >= 2_000:
        return "Medium", [f"{github_followers:,} GitHub followers"]
    return "Low", [f"{github_followers:,} GitHub followers"]
