"""Test doubles: HTTP-level simulations of Nansen, Ethereum RPC (ENS), GitHub,
personal websites, Apollo and Hunter.

These exist ONLY for tests. The application code under test is the real
provider clients; only the network is replaced by ``httpx.MockTransport``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx

from lead_finder.providers.ens import ENS_REGISTRY, namehash, selector

RESOLVER = "0x" + "11" * 20
NOW = datetime.now(timezone.utc)


def ts(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _word_address(addr: str) -> str:
    return "0x" + "0" * 24 + addr[2:].lower()


def _abi_string(value: str) -> str:
    data = value.encode()
    padded = data + b"\x00" * ((32 - len(data) % 32) % 32)
    return "0x" + (32).to_bytes(32, "big").hex() + len(data).to_bytes(32, "big").hex() + padded.hex()


@dataclass
class EnsEntry:
    name: str
    address: str
    records: dict = field(default_factory=dict)
    set_reverse: bool = True


@dataclass
class World:
    # Nansen
    balances: dict = field(default_factory=dict)        # (chain, addr) -> list[rows]
    trades: dict = field(default_factory=dict)          # (chain, addr) -> list[rows]
    labels: dict = field(default_factory=dict)          # (chain, addr) -> list[rows]
    discovery: dict = field(default_factory=dict)       # (chain, token) -> list[rows]
    nansen_error: tuple | None = None                   # (status_code, body)
    # ENS
    ens: list = field(default_factory=list)
    contracts: set = field(default_factory=set)
    # GitHub / web
    github: dict = field(default_factory=dict)          # login -> profile json
    websites: dict = field(default_factory=dict)        # url -> html
    # Apollo / Hunter
    apollo: dict = field(default_factory=dict)          # (first,last) -> person json
    apollo_error: tuple | None = None
    hunter_find: dict = field(default_factory=dict)     # (first,last,domain) -> data json
    hunter_verify: dict = field(default_factory=dict)   # email -> status
    hunter_error: tuple | None = None
    calls: list = field(default_factory=list)

    # ------------------------------------------------------------ handlers
    def handler(self, request: httpx.Request) -> httpx.Response:
        url = urlparse(str(request.url))
        self.calls.append((url.netloc, url.path))
        if url.netloc == "api.nansen.test":
            return self._nansen(request, url.path)
        if url.netloc == "rpc.test":
            return self._rpc(json.loads(request.content))
        if url.netloc == "api.github.test":
            login = url.path.rsplit("/", 1)[-1]
            prof = self.github.get(login)
            return httpx.Response(200, json=prof) if prof else httpx.Response(404, json={"message": "Not Found"})
        if url.netloc == "api.apollo.test":
            return self._apollo(json.loads(request.content))
        if url.netloc == "api.hunter.test":
            return self._hunter(url.path, parse_qs(url.query))
        page = self.websites.get(f"{url.scheme}://{url.netloc}{url.path}".rstrip("/"))
        if page is not None:
            return httpx.Response(200, text=page)
        return httpx.Response(404, text="not found")

    def _nansen(self, request: httpx.Request, path: str) -> httpx.Response:
        if request.headers.get("apiKey") != "test-nansen-key":
            return httpx.Response(401, json={"detail": "Invalid API key"})
        if self.nansen_error:
            return httpx.Response(self.nansen_error[0], json=self.nansen_error[1])
        body = json.loads(request.content)
        chain = body.get("chain")
        if path == "/api/v1/tgm/who-bought-sold":
            rows = self.discovery.get((chain, body["token_address"]), [])
        elif path == "/api/v1/profiler/address/current-balance":
            key = (chain, body["address"])
            if key not in self.balances:
                return httpx.Response(422, json={"detail": f"chain {chain} not supported"})
            rows = self.balances[key]
        elif path == "/api/v1/profiler/dex-trades":
            rows = self.trades.get((chain, body["address"]), [])
        elif path == "/api/v1/profiler/address/labels":
            rows = self.labels.get((chain, body["address"]), [])
        else:
            return httpx.Response(404, json={"detail": "unknown endpoint"})
        return httpx.Response(200, json={"data": rows, "pagination": {"page": 1, "per_page": 100, "is_last_page": True}})

    def _rpc(self, payload: dict) -> httpx.Response:
        method, params = payload["method"], payload["params"]
        if method == "eth_blockNumber":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x10"})
        if method == "eth_getCode":
            code = "0x6080" if params[0].lower() in self.contracts else "0x"
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": code})
        call = params[0]
        to, data = call["to"].lower(), call["data"][2:]
        sel, node = data[:8], bytes.fromhex(data[8:72])
        result = "0x"
        nodes = {}
        for e in self.ens:
            nodes[namehash(e.name)] = ("forward", e)
            if e.set_reverse:
                nodes[namehash(f"{e.address.lower()[2:]}.addr.reverse")] = ("reverse", e)
        hit = nodes.get(node)
        if to == ENS_REGISTRY.lower() and sel == selector("resolver(bytes32)"):
            result = _word_address(RESOLVER) if hit else "0x" + "0" * 64
        elif to == RESOLVER and hit:
            kind, e = hit
            if sel == selector("name(bytes32)") and kind == "reverse":
                result = _abi_string(e.name)
            elif sel == selector("addr(bytes32)") and kind == "forward":
                result = _word_address(e.address)
            elif sel == selector("text(bytes32,string)") and kind == "forward":
                raw = bytes.fromhex(data[8:])
                length = int.from_bytes(raw[64:96], "big")
                key = raw[96:96 + length].decode()
                result = _abi_string(e.records.get(key, ""))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    def _apollo(self, body: dict) -> httpx.Response:
        if self.apollo_error:
            return httpx.Response(self.apollo_error[0], json=self.apollo_error[1])
        person = self.apollo.get((body.get("first_name"), body.get("last_name")))
        return httpx.Response(200, json={"person": person})

    def _hunter(self, path: str, q: dict) -> httpx.Response:
        if self.hunter_error:
            return httpx.Response(self.hunter_error[0], json=self.hunter_error[1])
        if path == "/v2/email-finder":
            data = self.hunter_find.get((q["first_name"][0], q["last_name"][0], q["domain"][0]))
            return httpx.Response(200, json={"data": data or {"email": None, "score": None}})
        if path == "/v2/email-verifier":
            return httpx.Response(200, json={"data": {"status": self.hunter_verify.get(q["email"][0], "unknown")}})
        if path == "/v2/account":
            return httpx.Response(200, json={"data": {"email": "ops@firm.test"}})
        return httpx.Response(404, json={})


# ------------------------------------------------------------------ scenario
ALICE = "0xa11ce00000000000000000000000000000000001"
ERIN = "0xe1110000000000000000000000000000000000e5"
ACME = "0xacace00000000000000000000000000000000ac3"
WHALE = "0x3a1e000000000000000000000000000000000077"
FAMOUS = "0xfa3e000000000000000000000000000000000f00"
NOPRICE = "0x0b1ce000000000000000000000000000000000b1"
SOL_WALLET = "7EYnhQoR9YM3N7UoaKRoA44Uy8JeaZV3qyouov87awMs"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"


def bal(symbol, amount, value, token="0x" + "22" * 20):
    return {"chain": "ethereum", "address": "", "token_address": token, "token_symbol": symbol,
            "token_amount": amount, "price_usd": (value / amount) if value is not None and amount else None,
            "value_usd": value}


def build_world() -> World:
    w = World()
    eth_native = "0x0000000000000000000000000000000000000000"
    # Alice: private individual, bidirectional ENS<->GitHub, modest wallet, recently active.
    w.balances[("ethereum", ALICE)] = [bal("ETH", 10, 30000, eth_native), bal("USDC", 12500, 12500),
                                       bal("variableDebtEthUSDC", 5000, 5000)]
    w.balances[("base", ALICE)] = [dict(bal("ETH", 1, 3000, eth_native), chain="base")]
    w.trades[("ethereum", ALICE)] = [{"block_timestamp": ts(3), "transaction_hash": "0x1", "token_bought_symbol": "ETH",
                                      "token_sold_symbol": "USDC", "trade_value_usd": 2000}]
    w.ens.append(EnsEntry("alicecarter.eth", ALICE, {"com.github": "alicecarter", "url": "https://alicecarter.dev",
                                                     "com.linkedin": "alice-carter-123"}))
    w.github["alicecarter"] = {"login": "alicecarter", "type": "User", "name": "Alice Carter",
                               "company": "@CarterAnalytics", "blog": "https://alicecarter.dev",
                               "location": "Austin, TX", "email": None, "bio": "Builder. alicecarter.eth",
                               "followers": 120, "html_url": "https://github.com/alicecarter"}
    w.apollo[("Alice", "Carter")] = {
        "id": "ap1", "first_name": "Alice", "last_name": "Carter", "title": "Founder & CEO",
        "linkedin_url": "http://www.linkedin.com/in/alice-carter-123", "email": "alice@carteranalytics.com",
        "email_status": "verified", "phone_numbers": [{"sanitized_number": "+15125550123"}],
        "city": "Austin", "state": "Texas", "country": "United States",
        "organization": {"name": "Carter Analytics", "primary_domain": "carteranalytics.com",
                         "estimated_num_employees": 12, "founded_year": 2019, "industry": "Information Technology"}}

    # Erin: ENS + GitHub without back-link (Medium), self-published ENS email; Apollo has no match.
    w.balances[("ethereum", ERIN)] = [bal("ETH", 1, 3000, eth_native)]
    w.trades[("ethereum", ERIN)] = [{"block_timestamp": ts(20), "transaction_hash": "0x2", "trade_value_usd": 100}]
    w.ens.append(EnsEntry("erinlee.eth", ERIN, {"com.github": "erinlee", "email": "erin@erinlee.io",
                                                "url": "https://erinlee.io"}))
    w.github["erinlee"] = {"login": "erinlee", "type": "User", "name": "Erin Lee", "company": None,
                           "blog": "https://erinlee.io", "location": "Denver", "email": None, "bio": "Engineer",
                           "followers": 40, "html_url": "https://github.com/erinlee"}
    w.websites["https://erinlee.io"] = "<html>Erin's home page. No wallet here.</html>"
    w.hunter_verify["erin@erinlee.io"] = "valid"

    # Acme Capital: an entity with an ENS name and an Organization GitHub.
    w.balances[("ethereum", ACME)] = [bal("USDC", 2_000_000, 2_000_000)]
    w.ens.append(EnsEntry("acmecapital.eth", ACME, {"com.github": "acme-capital", "email": "deals@acme.capital"}))
    w.github["acme-capital"] = {"login": "acme-capital", "type": "Organization", "name": "Acme Capital LLC",
                                "bio": "acmecapital.eth", "followers": 300, "html_url": "https://github.com/acme-capital"}
    w.labels[("ethereum", ACME)] = [{"label": "Acme Capital: Treasury", "category": "Fund"}]

    # Whale: huge, active, but anonymous (no self-published identity).
    w.balances[("ethereum", WHALE)] = [bal("ETH", 2000, 6_000_000, eth_native)]
    w.trades[("ethereum", WHALE)] = [{"block_timestamp": ts(1), "transaction_hash": "0x3", "trade_value_usd": 1e6}]

    # Famous: bidirectionally attributed but a prominent public figure.
    w.balances[("ethereum", FAMOUS)] = [bal("ETH", 100, 300000, eth_native)]
    w.ens.append(EnsEntry("famousdev.eth", FAMOUS, {"com.github": "famousdev", "email": "famous@dev.io"}))
    w.github["famousdev"] = {"login": "famousdev", "type": "User", "name": "Morgan Famous", "bio": "famousdev.eth",
                             "followers": 85000, "html_url": "https://github.com/famousdev"}

    # Unpriced holdings: tokens exist but the provider has no USD value.
    w.balances[("ethereum", NOPRICE)] = [bal("OBSCURE", 1000, None)]

    # Solana wallet: provider data, no attribution source.
    w.balances[("solana", SOL_WALLET)] = [dict(bal("SOL", 50, 7500, "So11111111111111111111111111111111111111111"),
                                               chain="solana")]
    w.trades[("solana", SOL_WALLET)] = [{"block_timestamp": ts(2), "transaction_hash": "s1"}]

    w.discovery[("ethereum", WETH)] = [{"address": a, "address_label": None, "trade_volume_usd": 1000}
                                       for a in (ALICE, ERIN, ACME, WHALE, FAMOUS, NOPRICE)]
    return w
