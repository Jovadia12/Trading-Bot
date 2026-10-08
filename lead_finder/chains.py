"""Chain registry and wallet address validation.

The registry lists the chains the Nansen v1 API accepts. A chain listed here is
NOT shown to users until the provider has actually returned valid data for it
(see ``provider_chain_support`` in the database).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from Crypto.Hash import keccak


def keccak256(data: bytes) -> bytes:
    h = keccak.new(digest_bits=256)
    h.update(data)
    return h.digest()


@dataclass(frozen=True)
class Chain:
    key: str          # provider identifier (Nansen chain name)
    name: str         # display name
    family: str       # "evm" | "solana" | "bitcoin" | "tron"
    native_symbol: str


CHAINS: dict[str, Chain] = {c.key: c for c in [
    Chain("ethereum", "Ethereum", "evm", "ETH"),
    Chain("base", "Base", "evm", "ETH"),
    Chain("arbitrum", "Arbitrum", "evm", "ETH"),
    Chain("optimism", "Optimism", "evm", "ETH"),
    Chain("polygon", "Polygon", "evm", "POL"),
    Chain("bnb", "BNB Chain", "evm", "BNB"),
    Chain("avalanche", "Avalanche", "evm", "AVAX"),
    Chain("linea", "Linea", "evm", "ETH"),
    Chain("scroll", "Scroll", "evm", "ETH"),
    Chain("mantle", "Mantle", "evm", "MNT"),
    Chain("sonic", "Sonic", "evm", "S"),
    Chain("hyperevm", "HyperEVM", "evm", "HYPE"),
    Chain("solana", "Solana", "solana", "SOL"),
    Chain("bitcoin", "Bitcoin", "bitcoin", "BTC"),
    Chain("tron", "Tron", "tron", "TRX"),
]}


def get_chain(key: str | None) -> Chain | None:
    if not key:
        return None
    return CHAINS.get(key.strip().lower())


# ---------------------------------------------------------------- validation

_EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]+$")


def _b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + _B58_ALPHABET.index(ch)
    full = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + full


def _b58check_payload(s: str) -> bytes | None:
    if not _B58_RE.match(s):
        return None
    raw = _b58decode(s)
    if len(raw) < 5:
        return None
    payload, checksum = raw[:-4], raw[-4:]
    if hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] != checksum:
        return None
    return payload


def evm_checksum(address: str) -> str:
    lower = address[2:].lower()
    digest = keccak256(lower.encode()).hex()
    return "0x" + "".join(c.upper() if int(digest[i], 16) >= 8 else c for i, c in enumerate(lower))


def _valid_evm(address: str) -> bool:
    if not _EVM_RE.match(address):
        return False
    body = address[2:]
    if body.islower() or body.isupper() or body.isdigit():
        return True
    return evm_checksum(address) == address  # mixed case must be a valid EIP-55 checksum


_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _bech32_polymod(values: list[int]) -> int:
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if ((top >> i) & 1) else 0
    return chk


def _valid_bech32_btc(address: str) -> bool:
    if address.lower() != address and address.upper() != address:
        return False
    addr = address.lower()
    if not addr.startswith("bc1") or len(addr) < 14 or len(addr) > 90:
        return False
    hrp, data = "bc", addr[3:]
    if any(c not in _BECH32_CHARSET for c in data):
        return False
    values = [_BECH32_CHARSET.index(c) for c in data]
    expanded = [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]
    const = _bech32_polymod(expanded + values)
    witness_version = values[0]
    if witness_version == 0:
        return const == 1            # bech32
    return const == 0x2BC830A3        # bech32m (taproot and later)


def _valid_bitcoin(address: str) -> bool:
    if address.lower().startswith("bc1"):
        return _valid_bech32_btc(address)
    if address[:1] in ("1", "3"):
        payload = _b58check_payload(address)
        return payload is not None and len(payload) == 21 and payload[0] in (0x00, 0x05)
    return False


def _valid_solana(address: str) -> bool:
    if not (32 <= len(address) <= 44) or not _B58_RE.match(address):
        return False
    return len(_b58decode(address)) == 32


def _valid_tron(address: str) -> bool:
    if not address.startswith("T"):
        return False
    payload = _b58check_payload(address)
    return payload is not None and len(payload) == 21 and payload[0] == 0x41


_VALIDATORS = {
    "evm": _valid_evm,
    "bitcoin": _valid_bitcoin,
    "solana": _valid_solana,
    "tron": _valid_tron,
}


def is_valid_address(chain_key: str, address: str | None) -> bool:
    chain = get_chain(chain_key)
    if chain is None or not address:
        return False
    return _VALIDATORS[chain.family](address.strip())


def normalize_address(chain_key: str, address: str) -> str:
    """Canonical form used for deduplication (chain + address)."""
    chain = get_chain(chain_key)
    address = address.strip()
    if chain is None:
        raise ValueError(f"Unsupported chain: {chain_key}")
    if chain.family == "evm" or (chain.family == "bitcoin" and address.lower().startswith("bc1")):
        return address.lower()
    return address  # base58 encodings are case-sensitive


def detect_families(address: str) -> list[str]:
    """Which chain families an address string is valid for (used by search parsing)."""
    address = address.strip()
    return [fam for fam, fn in _VALIDATORS.items() if fn(address)]


def chains_for_family(family: str) -> list[str]:
    return [c.key for c in CHAINS.values() if c.family == family]


def mask_address(address: str | None) -> str | None:
    if not address:
        return None
    if len(address) <= 12:
        return address
    return f"{address[:5]}...{address[-3:]}" if address.startswith("0x") else f"{address[:4]}...{address[-4:]}"
