"""Execution-cost model for backtests (per side, as fractions of notional).

Defaults = Coinbase Advanced US entry tier for a small account (0.50% maker / 0.90% taker; see
VENUE_EXECUTION_RESEARCH.md -- third-party sourced, UNCONFIRMED) unless research_data/fees.json
(written by backtest.fetch_coinbase from YOUR account) exists, which then takes precedence.
Spread and slippage are ASSUMED until measured by market_data.spread_monitor.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from backtest.data import DATA_DIR


@dataclass(frozen=True)
class CostModel:
    name: str
    maker_fee: float = 0.0050
    taker_fee: float = 0.0090
    half_spread: float = 0.00005      # 0.5 bp: BTC-USD top-of-book spread is ~1 bp or less (ASSUMED)
    slippage: float = 0.0002          # 2 bp per taker leg for a small order (ASSUMED)
    stop_slippage: float = 0.0005     # 5 bp extra on stop-market exits (fast markets; ASSUMED)
    source: str = "Coinbase Advanced US entry tier (UNCONFIRMED default)"

    def taker_price_impact(self, is_stop: bool = False) -> float:
        return self.half_spread + self.slippage + (self.stop_slippage if is_stop else 0.0)

    def scaled(self, factor: float, name: str) -> "CostModel":
        return replace(self, name=name, maker_fee=self.maker_fee * factor, taker_fee=self.taker_fee * factor,
                       half_spread=self.half_spread * factor, slippage=self.slippage * factor,
                       stop_slippage=self.stop_slippage * factor)


ZERO = CostModel("zero (gross)", 0, 0, 0, 0, 0, "no costs -- for diagnosis only")


def default_costs(fees_file: Path = DATA_DIR / "fees.json") -> CostModel:
    base = CostModel("coinbase_small_account")
    if fees_file.is_file():
        f = json.loads(fees_file.read_text())
        return replace(base, maker_fee=float(f["maker_fee_rate"]), taker_fee=float(f["taker_fee_rate"]),
                       source=f"{f.get('source', 'your Coinbase account')} ({f.get('pricing_tier')}, {f.get('fetched_at')})")
    return base
