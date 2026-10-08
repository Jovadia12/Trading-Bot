"""Wallet -> person attribution from self-published public evidence.

Appearing on the same web page as a name is NOT evidence. Accepted evidence:

* ENS primary name: a reverse record that only the wallet's own key can set,
  forward-verified to resolve back to the same address.
* ENS text records (com.github, url, com.linkedin, email, name): set by the
  owner of that ENS name, i.e. the wallet owner publishing their profile.
* Back-link: the linked GitHub profile / personal site itself mentions the
  wallet address or ENS name, which closes the loop in both directions.

Confidence levels
  wallet attribution  High   = ENS primary name + profile/site links back
                      Medium = ENS primary name + owner-set profile records (one-way)
                      Low    = ENS primary name only, or third-party label only
                      None   = no evidence
  identity            High   = real name on a bidirectionally linked profile
                               (or Apollo confirms the owner-linked LinkedIn)
                      Medium = real name from an owner-linked profile (one-way)
                      Low    = only a pseudonym
                      None   = nothing
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .classification import looks_like_person_name
from .providers.ens import EnsProfile
from .providers.profiles import GithubProfile

LEVELS = ["None", "Low", "Medium", "High"]


def downgrade(level: str) -> str:
    return LEVELS[max(0, LEVELS.index(level) - 1)]


@dataclass
class EvidenceItem:
    kind: str          # attribution | identity | contact
    provider: str
    url: str
    detail: str


@dataclass
class Attribution:
    wallet_confidence: str = "None"
    identity_confidence: str = "None"
    wallet_source: str | None = None
    identity_source: str | None = None
    full_name: str | None = None
    name_origin: str | None = None
    github_backlink: bool = False
    website_backlink: bool = False
    evidence: list[EvidenceItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def assess(*, chain: str, address: str, ens: EnsProfile | None, github: GithubProfile | None,
           website_hits: list[str], is_contract: bool | None) -> Attribution:
    a = Attribution()
    if ens is None:
        a.notes.append("No self-published attribution (no verified ENS primary name)")
        return a

    a.evidence.append(EvidenceItem("attribution", "ENS", f"https://app.ens.domains/{ens.name}",
                                   f"Verified primary name {ens.name} (reverse + forward resolution)"))
    owner_records = [k for k in ("com.github", "url", "com.linkedin", "email", "name", "com.twitter")
                     if ens.records.get(k)]
    for key in owner_records:
        a.evidence.append(EvidenceItem("attribution", "ENS", f"https://app.ens.domains/{ens.name}",
                                       f"Owner-set ENS text record '{key}'"))

    needles = {address.lower(), ens.name.lower()}
    if github:
        haystack = f"{github.bio or ''} {github.blog or ''}".lower()
        a.github_backlink = any(n in haystack for n in needles)
        if a.github_backlink:
            a.evidence.append(EvidenceItem("attribution", "GitHub", github.html_url,
                                           "GitHub profile links back to the wallet / ENS name"))
    if website_hits:
        a.website_backlink = True
        a.evidence.append(EvidenceItem("attribution", "Public website", ens.records.get("url", ""),
                                       "Owner's website links back to the wallet / ENS name"))

    if a.github_backlink or a.website_backlink:
        a.wallet_confidence = "High"
        a.wallet_source = "ENS primary name + profile back-link"
    elif owner_records:
        a.wallet_confidence = "Medium"
        a.wallet_source = "ENS primary name + owner-set profile records"
    else:
        a.wallet_confidence = "Low"
        a.wallet_source = "ENS primary name only"

    # ENS reverse records live on Ethereum. The same address on another EVM chain is
    # controlled by the same key only if it is an EOA (no contract code).
    if chain != "ethereum" and is_contract is not False:
        a.wallet_confidence = downgrade(a.wallet_confidence)
        a.notes.append("ENS is on Ethereum; address could not be confirmed as an EOA on this chain")

    # Identity: name only from sources the wallet owner controls.
    gh_name = github.name if github and github.type == "User" else None
    if looks_like_person_name(gh_name):
        a.full_name, a.name_origin = gh_name.strip(), "GitHub profile linked from ENS"
        a.identity_confidence = "High" if a.github_backlink else "Medium"
        a.identity_source = ("GitHub (bidirectional link with ENS)" if a.github_backlink
                             else "GitHub (linked from owner's ENS record)")
        a.evidence.append(EvidenceItem("identity", "GitHub", github.html_url, "Name published on GitHub profile"))
    elif looks_like_person_name(ens.records.get("name")):
        a.full_name, a.name_origin = ens.records["name"].strip(), "ENS 'name' record"
        a.identity_confidence = "High" if a.website_backlink else "Medium"
        a.identity_source = "ENS text record set by wallet owner"
        a.evidence.append(EvidenceItem("identity", "ENS", f"https://app.ens.domains/{ens.name}",
                                       "Name published in owner's ENS record"))
    else:
        a.identity_confidence = "Low"
        a.identity_source = "Pseudonymous ENS name only"
        a.notes.append("Owner has not published a real name")
    return a
