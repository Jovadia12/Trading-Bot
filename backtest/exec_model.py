"""Execution cases for the daily study (see DAILY_STRATEGY_PROTOCOL.md): TAKER and MAKER-oriented.

TAKER: exactly the existing engine (backtest/engine.py): market entry at the next open, stop-market
stops, signal exits at the next open, all taker.

MAKER-oriented (conservative OHLC model; there is no historical order-book / queue data):
  * ENTRY: a post-only limit BUY at the signal bar's CLOSE, working for ONE bar (bar i+1). It counts as
    filled only if that bar's LOW trades THROUGH the limit by `penetration` (touching, or trading at the
    price, is not a fill: we assume we are last in the queue). Fill price = the limit, maker fee, no
    spread/slippage. If not filled, the order is cancelled and the trade is MISSED (never chased).
    -> Adverse selection is inherent: we only get filled when price moves against us after the signal,
       and we miss the trades that run away immediately (often the best ones).
  * The protective STOP is always a stop-market (TAKER) order with stop slippage, active from the fill.
    On the entry bar, if the low also reaches the stop, the stop is assumed hit (fill came first).
  * SIGNAL exits: a post-only limit SELL at the exit-signal bar's CLOSE, working for ONE bar. Filled only
    if that bar's HIGH trades through it by `penetration`. If the stop is also inside that bar, the STOP
    is assumed first (worst case). If unfilled, exit is a TAKER market order at the following open.
  * Window-end exits are taker at the open (research artifact, as in the base engine).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np
import pandas as pd

from backtest.costs import CostModel
from backtest.engine import AccountResult, RawTrade, Signals, generate_trades

MODES = ("taker", "maker")


@dataclass(frozen=True)
class MakerRules:
    penetration: float = 0.001       # 0.10%: price must trade this far THROUGH the limit to count as a fill


@dataclass
class ExecTrade(RawTrade):
    entry_maker: bool = False
    exit_maker: bool = False


def generate_trades_exec(df: pd.DataFrame, sig: Signals, window: Optional[tuple] = None, mode: str = "taker",
                         rules: MakerRules = MakerRules(), stats: Optional[dict] = None) -> list[ExecTrade]:
    if mode not in MODES:
        raise ValueError(mode)
    if mode == "taker":
        return [ExecTrade(**asdict(t), entry_maker=False, exit_maker=(t.exit_type == "target"))
                for t in generate_trades(df, sig, window)]
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(df)
    lo_i, hi_i = 0, n
    if window is not None:
        lo_i = int(df.index.searchsorted(pd.Timestamp(window[0])))
        hi_i = int(df.index.searchsorted(pd.Timestamp(window[1])))
    entry = np.asarray(sig.entry, bool)
    stop_d = np.asarray(sig.stop_dist, float)
    tp_d = None if sig.tp_dist is None else np.asarray(sig.tp_dist, float)
    ex = None if sig.exit_sig is None else np.asarray(sig.exit_sig, bool)
    tr = None if sig.trail_dist is None else np.asarray(sig.trail_dist, float)
    pen = rules.penetration
    st = {"entry_signals": 0, "missed_entries": 0, "maker_exits": 0, "fallback_exits": 0}
    trades: list[ExecTrade] = []
    cand = np.flatnonzero(entry[lo_i:hi_i]) + lo_i
    ci = 0
    while ci < len(cand):
        i = cand[ci]
        ci += 1
        j0 = i + 1
        if j0 >= hi_i or j0 >= n or not (stop_d[i] > 0) or not np.isfinite(stop_d[i]):
            continue
        st["entry_signals"] += 1
        e = c[i]                                   # limit price = signal close
        if not (l[j0] < e * (1 - pen)):
            st["missed_entries"] += 1
            continue
        stop = e - stop_d[i]
        if stop <= 0:
            continue
        tp = e + tp_d[i] if tp_d is not None and np.isfinite(tp_d[i]) else np.inf
        exit_i, exit_ref, etype, xm = None, None, None, False
        pending, x_lim = None, np.nan
        j = j0
        while j < hi_i:
            if j > j0 and o[j] <= stop:
                exit_i, exit_ref, etype = j, o[j], "stop"
                break
            if l[j] <= stop:
                exit_i, exit_ref, etype = j, (min(stop, o[j]) if j == j0 else stop), "stop"
                break
            if pending == j:
                if h[j] > x_lim * (1 + pen):
                    exit_i, exit_ref, etype, xm = j, x_lim, "signal_maker", True
                    st["maker_exits"] += 1
                    break
                if j + 1 < n:
                    exit_i, exit_ref = j + 1, o[j + 1]
                    etype = "window_end" if j + 1 >= hi_i else "signal_taker_fallback"
                    st["fallback_exits"] += etype == "signal_taker_fallback"
                    break
            elif h[j] > tp:
                exit_i, exit_ref, etype, xm = j, tp, "target", True
                break
            elif pending is None and j + 1 < n and (
                    (ex is not None and ex[j]) or (sig.max_hold is not None and (j - j0 + 1) >= sig.max_hold)):
                if j + 1 >= hi_i:
                    exit_i, exit_ref, etype = j + 1, o[j + 1], "window_end"
                    break
                pending, x_lim = j + 1, c[j]
            if tr is not None and np.isfinite(tr[j]):
                stop = max(stop, c[j] - tr[j])
            j += 1
        if exit_i is None:
            if hi_i < n:
                exit_i, exit_ref, etype = hi_i, o[hi_i], "window_end"
            else:
                exit_i, exit_ref, etype = n - 1, c[n - 1], "data_end"
        trades.append(ExecTrade(int(i), int(j0), int(exit_i), float(e), float(exit_ref), float(e - stop_d[i]), etype,
                                entry_maker=True, exit_maker=xm))
        while ci < len(cand) and cand[ci] < exit_i:
            ci += 1
    if stats is not None:
        stats.update(st)
    return trades


_OPEN_EXITS = ("signal", "time", "window_end", "signal_taker_fallback")


def simulate_exec(df: pd.DataFrame, raw: list[ExecTrade], costs: CostModel, start: float = 1000.0,
                  risk: float = 0.01, min_order_usd: float = 1.0) -> AccountResult:
    """Cash-only compounding like engine.simulate_account, but each leg is priced by its liquidity flag:
    maker legs pay the maker fee at the limit price (no spread/slippage); taker legs pay the taker fee plus
    half-spread + slippage (+ stop slippage on stops). Size = risk * equity / (entry - initial stop),
    capped by cash including the entry fee (no leverage)."""
    close = df.close.to_numpy(float)
    n = len(df)
    eq = np.full(n, np.nan)
    eq[0] = start
    cash = start
    rows, skipped = [], 0
    for t in raw:
        if t.entry_maker:
            e_fill, e_rate = t.entry_ref, costs.maker_fee
        else:
            e_fill, e_rate = t.entry_ref * (1 + costs.taker_price_impact()), costs.taker_fee
        dist = t.entry_ref - t.stop0
        qty = min(risk * cash / dist, cash / (e_fill * (1 + e_rate)))
        if qty * e_fill < min_order_usd or qty <= 0:
            skipped += 1
            continue
        e_fee = qty * e_fill * e_rate
        if t.exit_maker:
            x_fill, x_rate = t.exit_ref, costs.maker_fee
        else:
            x_fill = t.exit_ref * (1 - costs.taker_price_impact(is_stop=(t.exit_type == "stop")))
            x_rate = costs.taker_fee
        x_fee = qty * x_fill * x_rate
        gross = qty * (t.exit_ref - t.entry_ref)
        slip = qty * (e_fill - t.entry_ref) + qty * (t.exit_ref - x_fill)
        fees = e_fee + x_fee
        net = gross - slip - fees
        cash_after_entry = cash - qty * e_fill - e_fee
        a, b = t.entry_i, t.exit_i
        if b > a:
            eq[a:b] = cash_after_entry + qty * close[a:b]
        eq_before = cash
        cash = cash + net
        eq[b] = cash
        rows.append(dict(entry_time=df.index[t.entry_i], exit_time=df.index[t.exit_i], signal_time=df.index[t.signal_i],
                         entry_ref=t.entry_ref, exit_ref=t.exit_ref, stop0=t.stop0, exit_type=t.exit_type,
                         entry_maker=t.entry_maker, exit_maker=t.exit_maker,
                         qty=qty, notional=qty * e_fill, gross=gross, fees=fees, slippage=slip, net=net,
                         ret=net / eq_before, r_mult=(net / (qty * dist)) if dist > 0 else np.nan,
                         bars=t.exit_i - t.entry_i + (0 if t.exit_type in _OPEN_EXITS else 1),
                         equity_after=cash))
    s = pd.Series(eq, index=df.index).ffill()
    return AccountResult(pd.DataFrame(rows), s, start, skipped)
