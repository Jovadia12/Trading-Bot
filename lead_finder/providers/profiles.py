"""Self-published public profiles linked from a wallet owner's ENS records.

* GitHub: public profile JSON (name, company, location, bio, blog, public email).
* Personal website: fetched only to check whether it links back to the wallet
  or ENS name. Guarded against SSRF (public https hosts only, no redirects to
  private addresses, size-capped).
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from .base import NotConfigured, ProviderError, UNREACHABLE, request_json

_GH_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def github_login_from_record(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().rstrip("/")
    if "github.com/" in v:
        v = v.split("github.com/", 1)[1].split("/")[0]
    v = v.lstrip("@")
    return v if _GH_LOGIN.match(v) else None


@dataclass
class GithubProfile:
    login: str
    type: str                   # "User" | "Organization"
    name: str | None
    company: str | None
    blog: str | None
    location: str | None
    email: str | None
    bio: str | None
    twitter_username: str | None
    followers: int | None
    html_url: str


class GithubClient:
    name = "GitHub"

    def __init__(self, base_url: str, token: str | None, http: httpx.Client):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.http = http

    @property
    def configured(self) -> bool:
        return True  # public endpoint; a token only raises rate limits

    def user(self, login: str) -> GithubProfile | None:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        status, data = request_json(self.http, self.name, "GET", f"{self.base_url}/users/{login}",
                                    headers=headers, ok_statuses=(404,))
        if status == 404 or not isinstance(data, dict):
            return None
        return GithubProfile(
            login=data.get("login") or login, type=data.get("type") or "User",
            name=(data.get("name") or None), company=(data.get("company") or None),
            blog=(data.get("blog") or None), location=(data.get("location") or None),
            email=(data.get("email") or None), bio=(data.get("bio") or None),
            twitter_username=data.get("twitter_username"),
            followers=data.get("followers") if isinstance(data.get("followers"), int) else None,
            html_url=data.get("html_url") or f"https://github.com/{login}",
        )


def _public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            return False
    return bool(infos)


class WebsiteChecker:
    name = "Public website"
    MAX_BYTES = 512 * 1024

    def __init__(self, enabled: bool, http: httpx.Client, resolver=_public_host):
        self.enabled = enabled
        self.http = http
        self._is_public = resolver

    @property
    def configured(self) -> bool:
        return self.enabled

    def page_mentions(self, url: str, needles: list[str]) -> list[str]:
        """Return which needles (case-insensitive) appear on the page."""
        if not self.enabled:
            raise NotConfigured(self.name)
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        for _ in range(4):
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.hostname or not self._is_public(parsed.hostname):
                return []
            try:
                with self.http.stream("GET", url, follow_redirects=False,
                                      headers={"User-Agent": "LeadFinder-attribution-check"}) as resp:
                    if resp.is_redirect and resp.headers.get("location"):
                        url = urljoin(url, resp.headers["location"])
                        continue
                    if not resp.is_success:
                        return []
                    body = b""
                    for chunk in resp.iter_bytes():
                        body += chunk
                        if len(body) >= self.MAX_BYTES:
                            break
            except httpx.HTTPError as exc:
                raise ProviderError(self.name, UNREACHABLE, type(exc).__name__) from exc
            text = body.decode("utf-8", errors="ignore").lower()
            return [n for n in needles if n and n.lower() in text]
        return []
