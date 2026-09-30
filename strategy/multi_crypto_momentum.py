"""multi_crypto_momentum: daily 40-day momentum + EMA200, 10 coins, long/short, BTC regime filter for alts.

Rules are fixed (see MULTI_CRYPTO_MOMENTUM.md); nothing here is optimised. The SAME code drives the backtest
(backtest/mcm_backtest.py) and the paper engine (paper_trading/mcm_runner.py):

  * build_states(frames)    -> per-coin indicator/signal table from COMPLETED daily candles only.
  * MCMEngine.on_close(...) -> at a completed candle's close, decide exits and entry candidates.
  * MCMEngine.on_open(...)  -> at the NEXT available candle's open, execute exits first, then entries
                               (prioritised by |40-day return| desc, then universe order), respecting the
                               10%-per-coin and 100%-total exposure caps and available cash.

Accounting (1x, no leverage, no borrowing): a long spends notional + fee from cash. A short (a paper/perp-proxy
short on spot prices) locks notional as 1x cash collateral + fee; its value is collateral + qty*(entry - price).
Nothing here can place an order; it only moves numbers in a paper Portfolio.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

UNIVERSE: tuple[str, ...] = ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "LINK", "ADA", "AVAX", "DOT")
REGIME_COIN = "BTC"
LONG, SHORT = "long", "short"


@dataclass(frozen=True)
class MCMParams:
    lookback: int = 40              # 40-day return
    long_threshold: float = 0.05    # +5%
    short_threshold: float = -0.05  # -5%
    ema_n: int = 200                # EMA200 (valid only after 200 completed candles)
    max_per_coin: float = 0.10      # of current equity, at entry
    max_total: float = 1.00         # gross exposure / equity
    fee_rate: float = 0.0005        # 0.05% per side
    slippage_rate: float = 0.0002   # 0.02% per side, adverse
    min_order_usd: float = 1.0


# ------------------------------------------------------------------------------------------ signals
def indicators(close: pd.Series, p: MCMParams = MCMParams()) -> pd.DataFrame:
    """ret40[t] = close[t]/close[t-40] - 1 ; ema[t] = EMA(span=200, adjust=False), NaN before 200 candles.
    Both use candles <= t only."""
    ret = close / close.shift(p.lookback) - 1
    ema = close.ewm(span=p.ema_n, adjust=False).mean()
    ema[np.arange(len(close)) < p.ema_n - 1] = np.nan
    return pd.DataFrame({"close": close, "ret": ret, "ema": ema})


def build_states(frames: dict[str, pd.DataFrame], p: MCMParams = MCMParams()) -> dict[str, pd.DataFrame]:
    """Per coin, indexed by that coin's candle dates (all COMPLETED candles):
    raw_long/raw_short (momentum + EMA only), regime_ok_long/short, long_sig/short_sig (after the BTC filter for
    alts), exit_long/exit_short. The BTC regime at an alt's date d is BTC's latest completed candle <= d."""
    out = {}
    btc = None
    if REGIME_COIN in frames:
        b = indicators(frames[REGIME_COIN].close, p)
        btc = pd.DataFrame({"bull": b.close > b.ema, "bear": b.close < b.ema, "valid": b.ema.notna()})
    for coin, df in frames.items():
        s = indicators(df.close, p)
        valid = s.ret.notna() & s.ema.notna()
        s["raw_long"] = valid & (s.ret > p.long_threshold) & (s.close > s.ema)
        s["raw_short"] = valid & (s.ret < p.short_threshold) & (s.close < s.ema)
        if coin == REGIME_COIN:
            s["regime_ok_long"] = True
            s["regime_ok_short"] = True
        elif btc is None:
            s["regime_ok_long"] = False       # no BTC data -> alts cannot pass the regime filter
            s["regime_ok_short"] = False
        else:
            r = btc.reindex(btc.index.union(s.index)).ffill().reindex(s.index)
            ok = r.valid.fillna(False).astype(bool)
            s["regime_ok_long"] = ok & r.bull.fillna(False).astype(bool)
            s["regime_ok_short"] = ok & r.bear.fillna(False).astype(bool)
        s["long_sig"] = s.raw_long & s.regime_ok_long
        s["short_sig"] = s.raw_short & s.regime_ok_short
        # exits: level conditions checked while holding == the crossing, since entries require the other side
        s["exit_long"] = valid & ((s.ret < 0) | (s.close < s.ema))
        s["exit_short"] = valid & ((s.ret > 0) | (s.close > s.ema))
        out[coin] = s
    return out


# --------------------------------------------------------------------------------------- portfolio
@dataclass
class Position:
    coin: str
    side: str
    qty: float
    entry_fill: float
    entry_ref: float
    entry_time: pd.Timestamp
    notional: float           # qty * entry_fill (= collateral for a short)
    entry_fee: float
    entry_slippage: float
    signal_ret: float

    def value(self, price: float) -> float:
        if self.side == LONG:
            return self.qty * price
        return self.notional + self.qty * (self.entry_fill - price)

    def exposure(self, price: float) -> float:
        return abs(self.qty * price)


@dataclass
class Portfolio:
    cash: float
    p: MCMParams = field(default_factory=MCMParams)
    positions: dict = field(default_factory=dict)
    trades: list = field(default_factory=list)
    fees_paid: float = 0.0
    slippage_paid: float = 0.0
    paper_orders: int = 0            # simulated fills; there is no live order path at all

    def equity(self, prices: dict) -> float:
        return self.cash + sum(pos.value(prices[c]) for c, pos in self.positions.items())

    def gross_exposure(self, prices: dict) -> float:
        return sum(pos.exposure(prices[c]) for c, pos in self.positions.items())

    def open(self, coin, side, ref_price, notional, when, signal_ret) -> Position:
        s, f = self.p.slippage_rate, self.p.fee_rate
        fill = ref_price * (1 + s) if side == LONG else ref_price * (1 - s)
        qty = notional / fill
        fee = notional * f
        self.cash -= notional + fee
        slip = qty * abs(fill - ref_price)
        pos = Position(coin, side, qty, fill, ref_price, when, notional, fee, slip, signal_ret)
        self.positions[coin] = pos
        self.fees_paid += fee
        self.slippage_paid += slip
        self.paper_orders += 1
        return pos

    def close(self, coin, ref_price, when, reason) -> dict:
        pos = self.positions.pop(coin)
        s, f = self.p.slippage_rate, self.p.fee_rate
        fill = ref_price * (1 - s) if pos.side == LONG else ref_price * (1 + s)
        fee = pos.qty * fill * f
        slip = pos.qty * abs(fill - ref_price)
        if pos.side == LONG:
            self.cash += pos.qty * fill - fee
            gross = pos.qty * (fill - pos.entry_fill)
        else:
            gross = pos.qty * (pos.entry_fill - fill)
            self.cash += pos.notional + gross - fee
        pnl = gross - pos.entry_fee - fee
        self.fees_paid += fee
        self.slippage_paid += slip
        self.paper_orders += 1
        t = {"coin": coin, "side": pos.side, "entry_time": pos.entry_time, "exit_time": when,
             "entry_ref": pos.entry_ref, "entry_fill": pos.entry_fill, "exit_ref": ref_price, "exit_fill": fill,
             "qty": pos.qty, "notional": pos.notional, "fees": pos.entry_fee + fee,
             "slippage": pos.entry_slippage + slip, "pnl": pnl, "ret_on_notional": pnl / pos.notional,
             "days": (when - pos.entry_time).days, "exit_reason": reason, "signal_ret40": pos.signal_ret}
        self.trades.append(t)
        return t


# ------------------------------------------------------------------------------------------ engine
@dataclass
class Pending:
    action: str               # "exit" | "long" | "short"
    ret: float
    signal_time: pd.Timestamp
    reason: str = ""


class MCMEngine:
    """Event-driven core shared by backtest and paper trading. Call on_close() with states of COMPLETED candles,
    then on_open() with the next candle's open prices."""

    def __init__(self, start_equity: float = 200.0, p: MCMParams = MCMParams(), universe=UNIVERSE,
                 enabled: Optional[set] = None):
        self.p = p
        self.universe = tuple(universe)
        self.order = {c: i for i, c in enumerate(self.universe)}
        self.enabled = set(self.universe if enabled is None else enabled)
        self.pf = Portfolio(start_equity, p)
        self.start_equity = start_equity
        self.pending: dict[str, Pending] = {}
        self.last_price: dict[str, float] = {}
        self.events: list[dict] = []          # signals, rejections, fills (audit log)
        self.short_collateral_breach_marks = 0   # marks where a 1x short lost more than its collateral

    # -- prices ---------------------------------------------------------------------------------
    def mark(self, prices: dict) -> None:
        self.last_price.update({c: float(v) for c, v in prices.items() if v is not None and np.isfinite(v)})
        for c, pos in self.pf.positions.items():
            if pos.side == SHORT and pos.value(self.last_price[c]) < 0:
                self.short_collateral_breach_marks += 1

    def equity(self) -> float:
        return self.pf.equity(self.last_price)

    def _log(self, kind, when, coin, **kw):
        self.events.append({"kind": kind, "time": when, "coin": coin, **kw})

    # -- decisions at a completed close ----------------------------------------------------------
    def on_close(self, when: pd.Timestamp, states: dict) -> None:
        """states: coin -> row (Series) of build_states() for the candle that just COMPLETED at `when`."""
        self.mark({c: s["close"] for c, s in states.items()})
        for coin, s in states.items():
            if coin not in self.enabled:
                continue
            self.pending.pop(coin, None)              # every close re-decides from scratch
            self.pending.pop(coin + "#entry", None)
            pos = self.pf.positions.get(coin)
            if pos is not None:
                ex = bool(s["exit_long"]) if pos.side == LONG else bool(s["exit_short"])
                if ex:
                    why = []
                    if pos.side == LONG:
                        why += ["ret40 < 0"] if s["ret"] < 0 else []
                        why += ["close < EMA200"] if s["close"] < s["ema"] else []
                    else:
                        why += ["ret40 > 0"] if s["ret"] > 0 else []
                        why += ["close > EMA200"] if s["close"] > s["ema"] else []
                    self.pending[coin] = Pending("exit", float(s["ret"]), when, " & ".join(why))
                    self._log("exit_signal", when, coin, side=pos.side, reason=" & ".join(why))
                    self._entry_candidate(coin, s, when, after_exit_of=pos.side)
                continue
            self._entry_candidate(coin, s, when)

    def _entry_candidate(self, coin, s, when, after_exit_of=None):
        for side, raw, sig, ok in ((LONG, "raw_long", "long_sig", "regime_ok_long"),
                                   (SHORT, "raw_short", "short_sig", "regime_ok_short")):
            if not bool(s[raw]):
                continue
            if not bool(s[ok]):
                self._log("signal_rejected", when, coin, side=side, reason="BTC regime filter", ret40=float(s["ret"]))
                continue
            if after_exit_of == side:
                continue
            self._log("signal", when, coin, side=side, ret40=float(s["ret"]))
            if after_exit_of is None:
                self.pending[coin] = Pending(side, float(s["ret"]), when)
            else:                                      # reversal: exit then enter the other side at the same open
                self.pending[coin + "#entry"] = Pending(side, float(s["ret"]), when)

    # -- execution at the next available open ------------------------------------------------------
    def on_open(self, when: pd.Timestamp, opens: dict) -> list[dict]:
        """opens: coin -> open price of the candle starting at `when` (only coins that HAVE such a candle).
        Exits first, then entries ordered by |ret40| desc, then universe order."""
        fills = []
        self.mark(opens)
        for coin in sorted(opens, key=lambda c: self.order.get(c, 99)):
            pd_ = self.pending.get(coin)
            if pd_ is not None and pd_.action == "exit" and coin in self.pf.positions:
                t = self.pf.close(coin, float(opens[coin]), when, pd_.reason)
                self._log("fill_exit", when, coin, side=t["side"], price=t["exit_fill"], pnl=t["pnl"])
                fills.append(t)
                del self.pending[coin]
                if coin + "#entry" in self.pending:
                    self.pending[coin] = self.pending.pop(coin + "#entry")
        cands = [(c, pd_) for c, pd_ in self.pending.items()
                 if pd_.action in (LONG, SHORT) and c in opens and c not in self.pf.positions]
        cands.sort(key=lambda x: (-abs(x[1].ret), self.order.get(x[0], 99)))
        for coin, pd_ in cands:
            del self.pending[coin]
            eq = self.equity()
            capacity = self.p.max_total * eq - self.pf.gross_exposure(self.last_price)
            cash_room = self.pf.cash / (1 + self.p.fee_rate)
            notional = min(self.p.max_per_coin * eq, capacity, cash_room)
            if notional < self.p.min_order_usd:
                reason = "portfolio exposure cap (100%)" if capacity <= cash_room else "insufficient cash"
                self._log("signal_rejected", when, coin, side=pd_.action, reason=reason, ret40=pd_.ret)
                continue
            pos = self.pf.open(coin, pd_.action, float(opens[coin]), notional, when, pd_.ret)
            self._log("fill_entry", when, coin, side=pos.side, price=pos.entry_fill, notional=notional,
                      capped=bool(notional < self.p.max_per_coin * eq - 1e-9))
            fills.append({"coin": coin, "side": pos.side, "notional": notional})
        # entry candidates for coins without an open at `when` stay pending until their next candle
        return fills

    def snapshot(self) -> dict:
        eq = self.equity()
        return {"equity": eq, "cash": self.pf.cash, "gross_exposure": self.pf.gross_exposure(self.last_price),
                "positions": {c: {"side": p.side, "qty": p.qty, "entry_fill": p.entry_fill,
                                  "value": p.value(self.last_price[c]), "entry_time": str(p.entry_time)}
                              for c, p in self.pf.positions.items()}}


def params_dict(p: MCMParams) -> dict:
    return asdict(p)
