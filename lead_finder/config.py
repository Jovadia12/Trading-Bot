"""Runtime configuration, read from environment variables only.

Provider keys are optional: a provider without a key reports "Not Configured"
and is skipped. Nothing is substituted for a missing provider.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

# Default discovery seeds: liquid wrapped-native tokens, whose active traders are
# real wallets with on-chain activity. Override with LEAD_FINDER_SEED_TOKENS.
DEFAULT_SEED_TOKENS: dict[str, list[str]] = {
    "ethereum": ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"],   # WETH
    "base": ["0x4200000000000000000000000000000000000006"],       # WETH
    "arbitrum": ["0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"],   # WETH
    "polygon": ["0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619"],    # WETH
    "solana": ["So11111111111111111111111111111111111111112"],    # wSOL
}


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


@dataclass
class Settings:
    db_path: str = "lead_finder.db"
    nansen_api_key: str | None = None
    nansen_base_url: str = "https://api.nansen.ai"
    apollo_api_key: str | None = None
    apollo_base_url: str = "https://api.apollo.io"
    hunter_api_key: str | None = None
    hunter_base_url: str = "https://api.hunter.io"
    eth_rpc_url: str | None = None
    github_token: str | None = None
    github_base_url: str = "https://api.github.com"
    fetch_websites: bool = True
    seed_tokens: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_SEED_TOKENS))
    max_candidates: int = 25
    activity_window_days: int = 90
    session_ttl_hours: int = 12
    cookie_secure: bool = True
    http_timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls()
        s.db_path = _env("LEAD_FINDER_DB") or s.db_path
        s.nansen_api_key = _env("NANSEN_API_KEY")
        s.nansen_base_url = _env("NANSEN_BASE_URL") or s.nansen_base_url
        s.apollo_api_key = _env("APOLLO_API_KEY")
        s.hunter_api_key = _env("HUNTER_API_KEY")
        s.eth_rpc_url = _env("ETH_RPC_URL")
        s.github_token = _env("GITHUB_TOKEN")
        s.fetch_websites = (_env("LEAD_FINDER_FETCH_WEBSITES") or "true").lower() != "false"
        s.cookie_secure = (_env("LEAD_FINDER_COOKIE_SECURE") or "true").lower() != "false"
        if raw := _env("LEAD_FINDER_SEED_TOKENS"):
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("LEAD_FINDER_SEED_TOKENS must be a JSON object {chain: [token, ...]}")
            s.seed_tokens = {str(k).lower(): [str(t) for t in v] for k, v in parsed.items()}
        if raw := _env("LEAD_FINDER_MAX_CANDIDATES"):
            s.max_candidates = max(1, min(200, int(raw)))
        return s
