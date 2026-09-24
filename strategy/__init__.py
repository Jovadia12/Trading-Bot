"""Strategy layer.

Deliberately empty of trading rules in this phase. Version A and the preregistered RSI(2)
pullback are NOT implemented or modified here (see NEW_STRATEGY_RESEARCH_PLAN.md). This package
only defines the interface a frozen strategy will later implement for paper trading.
"""
from strategy.base import Signal, Strategy

__all__ = ["Signal", "Strategy"]
