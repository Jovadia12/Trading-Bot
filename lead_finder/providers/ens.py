"""ENS lookups over a standard Ethereum JSON-RPC endpoint (ETH_RPC_URL).

Why ENS is strong attribution evidence: a reverse record (primary name) can only
be set by a transaction signed by the address itself, and text records can only
be set by the name's owner. A primary name that forward-resolves back to the
same address is the wallet owner publicly naming themselves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import httpx

from ..chains import keccak256
from .base import PROVIDER_ERROR, NotConfigured, ProviderError, request_json

ENS_REGISTRY = "0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e"
ZERO_ADDRESS = "0x" + "0" * 40
TEXT_KEYS = ("name", "email", "url", "com.github", "com.twitter", "com.linkedin",
             "description", "location", "org.telegram")


@lru_cache(maxsize=None)
def selector(signature: str) -> str:
    return keccak256(signature.encode()).hex()[:8]


def namehash(name: str) -> bytes:
    node = b"\x00" * 32
    if name:
        for label in reversed(name.split(".")):
            node = keccak256(node + keccak256(label.encode()))
    return node


def _encode_string_arg(value: str) -> str:
    data = value.encode()
    padded = data + b"\x00" * ((32 - len(data) % 32) % 32)
    return len(data).to_bytes(32, "big").hex() + padded.hex()


def _decode_address(result: str) -> str | None:
    raw = result[2:] if result.startswith("0x") else result
    if len(raw) < 64:
        return None
    addr = "0x" + raw[24:64]
    return None if addr == ZERO_ADDRESS else addr


def _decode_string(result: str) -> str | None:
    raw = bytes.fromhex(result[2:] if result.startswith("0x") else result)
    if len(raw) < 64:
        return None
    offset = int.from_bytes(raw[0:32], "big")
    if offset + 32 > len(raw):
        return None
    length = int.from_bytes(raw[offset:offset + 32], "big")
    value = raw[offset + 32: offset + 32 + length]
    try:
        text = value.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    return text or None


@dataclass
class EnsProfile:
    address: str
    name: str                       # verified primary name
    records: dict[str, str] = field(default_factory=dict)


class EnsResolver:
    name = "ENS (Ethereum RPC)"

    def __init__(self, rpc_url: str | None, http: httpx.Client):
        self.rpc_url = rpc_url
        self.http = http

    @property
    def configured(self) -> bool:
        return bool(self.rpc_url)

    def _rpc(self, method: str, params: list) -> str:
        if not self.configured:
            raise NotConfigured(self.name)
        _, payload = request_json(self.http, self.name, "POST", self.rpc_url,
                                  json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if not isinstance(payload, dict):
            raise ProviderError(self.name, PROVIDER_ERROR, "Malformed JSON-RPC response")
        if payload.get("error"):
            err = payload["error"]
            # A revert means "no such record" for ENS resolvers, not a provider failure.
            if isinstance(err, dict) and "revert" in str(err.get("message", "")).lower():
                return "0x"
            raise ProviderError(self.name, PROVIDER_ERROR, str(err)[:200])
        return str(payload.get("result") or "0x")

    def _call(self, to: str, data: str) -> str:
        return self._rpc("eth_call", [{"to": to, "data": data}, "latest"])

    def _resolver(self, node: bytes) -> str | None:
        return _decode_address(self._call(ENS_REGISTRY, "0x" + selector("resolver(bytes32)") + node.hex()))

    def is_contract(self, address: str) -> bool:
        code = self._rpc("eth_getCode", [address, "latest"])
        return code not in ("0x", "0x0", "")

    def resolve_name(self, name: str) -> str | None:
        node = namehash(name.lower())
        resolver = self._resolver(node)
        if not resolver:
            return None
        return _decode_address(self._call(resolver, "0x" + selector("addr(bytes32)") + node.hex()))

    def text(self, name: str, key: str, resolver: str | None = None) -> str | None:
        node = namehash(name.lower())
        resolver = resolver or self._resolver(node)
        if not resolver:
            return None
        data = ("0x" + selector("text(bytes32,string)") + node.hex()
                + (64).to_bytes(32, "big").hex() + _encode_string_arg(key))
        result = self._call(resolver, data)
        return _decode_string(result) if result not in ("0x", "") else None

    def reverse_lookup(self, address: str) -> EnsProfile | None:
        """Verified primary name + owner-set text records, or None."""
        address = address.lower()
        node = namehash(f"{address[2:]}.addr.reverse")
        resolver = self._resolver(node)
        if not resolver:
            return None
        result = self._call(resolver, "0x" + selector("name(bytes32)") + node.hex())
        name = _decode_string(result) if result not in ("0x", "") else None
        if not name:
            return None
        # Forward verification: the name must resolve back to this address,
        # otherwise the reverse record is not a valid primary name.
        forward = self.resolve_name(name)
        if not forward or forward.lower() != address:
            return None
        name_resolver = self._resolver(namehash(name.lower()))
        records = {}
        for key in TEXT_KEYS:
            value = self.text(name, key, name_resolver)
            if value:
                records[key] = value[:500]
        return EnsProfile(address=address, name=name, records=records)
