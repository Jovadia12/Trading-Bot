"""Nansen API v1 client (https://api.nansen.ai).

Endpoints used (POST, JSON body, ``apiKey`` header):
  /api/v1/tgm/who-bought-sold          discovery: wallets actively trading a token
  /api/v1/profiler/address/current-balance   holdings with USD values
  /api/v1/profiler/dex-trades          recent on-chain trading activity
  /api/v1/profiler/address/labels      Nansen address labels

Unknown USD values stay ``None``. A token Nansen cannot price is never counted
as $0, and a wallet with no priced tokens is "Holdings unavailable".
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx

from ..chains import CHAINS, get_chain
from ..security import utcnow
from .base import NotConfigured, request_json
from .wallet import Activity, DiscoveredWallet, Holdings, ProviderLabel, TokenHolding

NATIVE_MARKERS = {
    "", "native", "0x0000000000000000000000000000000000000000",
    "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "so11111111111111111111111111111111111111111",
}
DEBT_PREFIXES = ("variabledebt", "stabledebt", "debt")
# Nansen v1 chain identifiers that the label endpoint accepts (from the API's chain enum).
LABEL_CHAINS = {"arbitrum", "avalanche", "base", "bnb", "ethereum", "hyperevm", "linea", "mantle",
                "optimism", "polygon", "scroll", "sei", "solana", "sonic", "tron"}
PAGE_SIZE = 100


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
    return []


def _is_last_page(payload: Any, got: int) -> bool:
    if isinstance(payload, dict):
        pag = payload.get("pagination")
        if isinstance(pag, dict) and "is_last_page" in pag:
            return bool(pag["is_last_page"])
    return got < PAGE_SIZE


class NansenClient:
    name = "Nansen"

    def __init__(self, api_key: str | None, base_url: str, http: httpx.Client):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.http = http

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def supported_chains(self) -> list[str]:
        return list(CHAINS)

    def _post(self, path: str, body: dict) -> Any:
        if not self.configured:
            raise NotConfigured(self.name)
        _, payload = request_json(
            self.http, self.name, "POST", f"{self.base_url}{path}", json=body,
            headers={"apiKey": self.api_key, "Content-Type": "application/json", "Accept": "application/json"},
        )
        return payload

    # ------------------------------------------------------------ discovery
    def discover(self, chain: str, token_address: str, days: int, limit: int) -> list[DiscoveredWallet]:
        now = utcnow()
        body = {
            "chain": chain,
            "token_address": token_address,
            "date": {"from": (now - timedelta(days=days)).isoformat(timespec="seconds"),
                     "to": now.isoformat(timespec="seconds")},
            "pagination": {"page": 1, "per_page": min(PAGE_SIZE, max(limit, 1))},
            "order_by": [{"field": "trade_volume_usd", "direction": "DESC"}],
        }
        payload = self._post("/api/v1/tgm/who-bought-sold", body)
        out: list[DiscoveredWallet] = []
        for row in _rows(payload):
            address = row.get("address")
            if not isinstance(address, str) or not address:
                continue
            out.append(DiscoveredWallet(
                chain=chain, address=address,
                source=f"Nansen tgm/who-bought-sold {token_address} ({days}d)",
                provider_label=row.get("address_label") or None,
                volume_usd=_num(row.get("trade_volume_usd")),
            ))
        return out[:limit]

    # ------------------------------------------------------------- holdings
    def holdings(self, chain: str, address: str) -> Holdings:
        info = get_chain(chain)
        native_symbol = info.native_symbol if info else ""
        rows: list[dict] = []
        for page in range(1, 4):
            payload = self._post("/api/v1/profiler/address/current-balance", {
                "address": address, "chain": chain, "hide_spam_token": True,
                "pagination": {"page": page, "per_page": PAGE_SIZE},
            })
            got = _rows(payload)
            rows.extend(got)
            if _is_last_page(payload, len(got)):
                break

        tokens: list[TokenHolding] = []
        for r in rows:
            row_chain = r.get("chain")
            if row_chain and str(row_chain).lower() != chain:
                continue
            tokens.append(TokenHolding(
                symbol=r.get("token_symbol"), token_address=r.get("token_address"),
                amount=_num(r.get("token_amount")), price_usd=_num(r.get("price_usd")),
                value_usd=_num(r.get("value_usd")),
            ))

        held = [t for t in tokens if (t.amount or 0) > 0 or (t.value_usd or 0) > 0]
        is_debt = lambda t: bool(t.symbol) and t.symbol.lower().startswith(DEBT_PREFIXES)  # noqa: E731
        assets = [t for t in held if not is_debt(t)]
        debts = [t for t in held if is_debt(t)]
        # Debt tokens (e.g. Aave variableDebt*) are liabilities: subtracted, never counted as holdings.
        priced_assets = [t.value_usd for t in assets if t.value_usd is not None]
        priced_debts = [t.value_usd for t in debts if t.value_usd is not None]
        if not held:
            # Provider answered and reports no balances: a known, empty wallet.
            estimated, status = 0.0, "Known"
        elif (assets and not priced_assets) or (not assets and not priced_debts):
            estimated, status = None, "Holdings unavailable"
        else:
            estimated = round(sum(priced_assets) - sum(priced_debts), 2)
            unpriced = len(priced_assets) < len(assets) or len(priced_debts) < len(debts)
            status = "Partial" if unpriced else "Known"

        native = None
        for t in assets:
            addr = (t.token_address or "").lower()
            if addr in NATIVE_MARKERS or (t.symbol or "").upper() == native_symbol:
                native = (native or 0.0) + (t.amount or 0.0)
        debt = sorted({t.symbol for t in debts})
        return Holdings(chain=chain, address=address, tokens=held, estimated_value_usd=estimated,
                        holdings_status=status, native_balance=native, native_symbol=native_symbol,
                        asset_count=len(assets), debt_positions=debt)

    # ------------------------------------------------------------- activity
    def activity(self, chain: str, address: str, days: int) -> Activity:
        now = utcnow()
        payload = self._post("/api/v1/profiler/dex-trades", {
            "address": address, "chain": chain,
            "date": {"from": (now - timedelta(days=days)).isoformat(timespec="seconds"),
                     "to": now.isoformat(timespec="seconds")},
            "pagination": {"page": 1, "per_page": PAGE_SIZE},
        })
        rows = _rows(payload)
        stamps = sorted((str(r["block_timestamp"]) for r in rows if r.get("block_timestamp")), reverse=True)
        recent = [{
            "timestamp": r.get("block_timestamp"),
            "tx": r.get("transaction_hash"),
            "bought": r.get("token_bought_symbol"),
            "sold": r.get("token_sold_symbol"),
            "value_usd": _num(r.get("trade_value_usd")),
        } for r in sorted(rows, key=lambda r: str(r.get("block_timestamp") or ""), reverse=True)[:10]]
        return Activity(chain=chain, address=address, trade_count=len(rows),
                        truncated=not _is_last_page(payload, len(rows)),
                        last_active_at=stamps[0] if stamps else None, window_days=days,
                        recent=recent, source=f"Nansen profiler/dex-trades ({days}d)")

    # --------------------------------------------------------------- labels
    def labels(self, chain: str, address: str) -> list[ProviderLabel]:
        if chain not in LABEL_CHAINS:
            return []
        payload = self._post("/api/v1/profiler/address/labels", {
            "address": address, "chain": chain, "pagination": {"page": 1, "per_page": PAGE_SIZE},
        })
        out = []
        for r in _rows(payload):
            if r.get("label"):
                out.append(ProviderLabel(label=str(r["label"]), category=r.get("category")))
        return out
