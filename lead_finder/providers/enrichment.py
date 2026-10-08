"""Contact enrichment: Apollo (primary) and Hunter (fallback + verification).

Enrichment only runs for an individual who has already publicly associated
themselves with the wallet. It is never used to unmask an anonymous wallet.
Results whose name does not match the person we asked about are discarded.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import httpx

from .base import NotConfigured, ProviderError, request_json

# Apollo per-lead statuses
APOLLO_SUCCESS, APOLLO_NO_MATCH, APOLLO_ERROR, APOLLO_NOT_CONFIGURED = (
    "Success", "No Match", "Provider Error", "Not Configured")
# Hunter per-lead statuses
HUNTER_FOUND, HUNTER_NOT_FOUND, HUNTER_ERROR, HUNTER_NOT_CONFIGURED = (
    "Found", "Not Found", "Provider Error", "Not Configured")


def fold(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def names_match(expected_first: str, expected_last: str, first: str | None, last: str | None) -> bool:
    return bool(first and last) and fold(expected_first) == fold(first) and fold(expected_last) == fold(last)


@dataclass
class ApolloResult:
    status: str
    message: str | None = None
    title: str | None = None
    company: str | None = None
    company_domain: str | None = None
    company_size: int | None = None
    company_founded_year: int | None = None
    industry: str | None = None
    linkedin: str | None = None
    email: str | None = None
    email_status: str | None = None
    phones: list[str] = field(default_factory=list)
    city: str | None = None
    state: str | None = None
    country: str | None = None
    apollo_id: str | None = None


class ApolloClient:
    name = "Apollo"

    def __init__(self, api_key: str | None, base_url: str, http: httpx.Client):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.http = http

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def match_person(self, first: str, last: str, *, organization: str | None = None,
                     domain: str | None = None, linkedin_url: str | None = None,
                     email: str | None = None) -> ApolloResult:
        if not self.configured:
            return ApolloResult(APOLLO_NOT_CONFIGURED)
        body = {"first_name": first, "last_name": last, "reveal_personal_emails": False}
        for key, val in (("organization_name", organization), ("domain", domain),
                         ("linkedin_url", linkedin_url), ("email", email)):
            if val:
                body[key] = val
        try:
            _, payload = request_json(
                self.http, self.name, "POST", f"{self.base_url}/api/v1/people/match", json=body,
                headers={"x-api-key": self.api_key, "Content-Type": "application/json",
                         "Cache-Control": "no-cache", "Accept": "application/json"})
        except ProviderError as exc:
            return ApolloResult(APOLLO_ERROR, message=f"{exc.status}: {exc.message}")
        person = payload.get("person") if isinstance(payload, dict) else None
        if not isinstance(person, dict):
            return ApolloResult(APOLLO_NO_MATCH)
        if not names_match(first, last, person.get("first_name"), person.get("last_name")):
            return ApolloResult(APOLLO_NO_MATCH, message="Returned person's name did not match")
        org = person.get("organization") if isinstance(person.get("organization"), dict) else {}
        phones = []
        for p in person.get("phone_numbers") or []:
            if isinstance(p, dict):
                num = p.get("sanitized_number") or p.get("raw_number")
                if num:
                    phones.append(str(num))
        email = person.get("email")
        if email and ("email_not_unlocked" in email or "domain.com" in email):
            email = None  # Apollo placeholder for locked emails, not a real address
        return ApolloResult(
            APOLLO_SUCCESS, title=person.get("title"), company=org.get("name"),
            company_domain=org.get("primary_domain"), company_size=org.get("estimated_num_employees"),
            company_founded_year=org.get("founded_year"), industry=org.get("industry"),
            linkedin=person.get("linkedin_url"), email=email, email_status=person.get("email_status"),
            phones=phones, city=person.get("city"), state=person.get("state"),
            country=person.get("country"), apollo_id=person.get("id"))


@dataclass
class HunterResult:
    status: str
    email: str | None = None
    score: int | None = None
    verification: str | None = None
    message: str | None = None


class HunterClient:
    name = "Hunter"
    MIN_SCORE = 70

    def __init__(self, api_key: str | None, base_url: str, http: httpx.Client):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.http = http

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def find_email(self, first: str, last: str, domain: str) -> HunterResult:
        if not self.configured:
            return HunterResult(HUNTER_NOT_CONFIGURED)
        try:
            _, payload = request_json(
                self.http, self.name, "GET", f"{self.base_url}/v2/email-finder",
                params={"domain": domain, "first_name": first, "last_name": last, "api_key": self.api_key})
        except ProviderError as exc:
            if exc.http_status in (404, 451):   # no result / unavailable for legal reasons
                return HunterResult(HUNTER_NOT_FOUND, message=exc.message)
            return HunterResult(HUNTER_ERROR, message=f"{exc.status}: {exc.message}")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not data.get("email"):
            return HunterResult(HUNTER_NOT_FOUND)
        if data.get("first_name") and data.get("last_name") and not names_match(
                first, last, data.get("first_name"), data.get("last_name")):
            return HunterResult(HUNTER_NOT_FOUND, message="Returned person's name did not match")
        score = data.get("score") if isinstance(data.get("score"), int) else None
        if score is not None and score < self.MIN_SCORE:
            return HunterResult(HUNTER_NOT_FOUND, score=score, message=f"Confidence {score} below {self.MIN_SCORE}")
        verification = (data.get("verification") or {}).get("status") if isinstance(data.get("verification"), dict) else None
        return HunterResult(HUNTER_FOUND, email=data["email"], score=score, verification=verification)

    def verify_email(self, email: str) -> str | None:
        """Hunter verifier status: valid | invalid | accept_all | webmail | disposable | unknown."""
        if not self.configured:
            raise NotConfigured(self.name)
        _, payload = request_json(self.http, self.name, "GET", f"{self.base_url}/v2/email-verifier",
                                  params={"email": email, "api_key": self.api_key})
        data = payload.get("data") if isinstance(payload, dict) else None
        return data.get("status") if isinstance(data, dict) else None

    def account(self) -> dict | None:
        if not self.configured:
            raise NotConfigured(self.name)
        _, payload = request_json(self.http, self.name, "GET", f"{self.base_url}/v2/account",
                                  params={"api_key": self.api_key})
        return payload.get("data") if isinstance(payload, dict) else None
