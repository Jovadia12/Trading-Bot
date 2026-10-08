"""Shared provider plumbing: status vocabulary, error mapping, retries."""
from __future__ import annotations

import time
from typing import Any

import httpx

# Provider-level connection status (shown in the Provider Status panel).
CONNECTED = "Connected"
NOT_CONFIGURED = "Not Configured"
INVALID_KEY = "Invalid API key"
INSUFFICIENT_CREDITS = "Insufficient credits"
RATE_LIMITED = "Rate limited"
ACCESS_DENIED = "Access denied"
REQUEST_REJECTED = "Request rejected"
PROVIDER_ERROR = "Provider error"
UNREACHABLE = "Unreachable"
CONFIGURED_UNCHECKED = "Configured (not yet used)"


class ProviderError(Exception):
    """A provider call failed. ``status`` is one of the labels above."""

    def __init__(self, provider: str, status: str, message: str, http_status: int | None = None):
        super().__init__(f"{provider}: {status}: {message}")
        self.provider = provider
        self.status = status
        self.message = message[:300]
        self.http_status = http_status


class NotConfigured(ProviderError):
    def __init__(self, provider: str):
        super().__init__(provider, NOT_CONFIGURED, "No API key / endpoint configured")


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return (resp.text or resp.reason_phrase or "")[:300]
    if isinstance(body, dict):
        for key in ("detail", "message", "error", "errors"):
            if key in body and body[key]:
                val = body[key]
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    val = val[0].get("details") or val[0].get("msg") or val[0]
                return str(val)[:300]
    return str(body)[:300]


def classify_http_error(provider: str, resp: httpx.Response) -> ProviderError:
    code = resp.status_code
    msg = _error_message(resp)
    low = msg.lower()
    if "credit" in low or "quota" in low or "insufficient" in low or code == 402:
        return ProviderError(provider, INSUFFICIENT_CREDITS, msg, code)
    if code == 401:
        return ProviderError(provider, INVALID_KEY, msg, code)
    if code == 403:
        return ProviderError(provider, ACCESS_DENIED, msg, code)
    if code == 429:
        return ProviderError(provider, RATE_LIMITED, msg, code)
    if 400 <= code < 500:
        return ProviderError(provider, REQUEST_REJECTED, msg, code)
    return ProviderError(provider, PROVIDER_ERROR, msg or f"HTTP {code}", code)


def request_json(client: httpx.Client, provider: str, method: str, url: str, *,
                 retries: int = 1, ok_statuses: tuple[int, ...] = (), **kwargs: Any) -> tuple[int, Any]:
    """Perform a request, retrying once on 429/5xx/network errors.

    Returns (status_code, parsed_json). Raises ProviderError on failure.
    ``ok_statuses`` lists non-2xx codes the caller handles itself (e.g. 404).
    """
    attempt = 0
    while True:
        try:
            resp = client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            if attempt < retries:
                attempt += 1
                time.sleep(0.5)
                continue
            raise ProviderError(provider, UNREACHABLE, type(exc).__name__) from exc
        if resp.status_code in ok_statuses:
            try:
                return resp.status_code, resp.json()
            except ValueError:
                return resp.status_code, None
        if resp.is_success:
            try:
                return resp.status_code, resp.json()
            except ValueError as exc:
                raise ProviderError(provider, PROVIDER_ERROR, "Response was not JSON", resp.status_code) from exc
        retryable = resp.status_code == 429 or resp.status_code >= 500
        if retryable and attempt < retries:
            attempt += 1
            wait = resp.headers.get("Retry-After", "1")
            time.sleep(min(float(wait) if wait.replace(".", "", 1).isdigit() else 1.0, 3.0))
            continue
        raise classify_http_error(provider, resp)
