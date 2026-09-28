"""Bar-by-bar long-only spot backtest engine with explicit, conservative execution.

Execution rules (no look-ahead):
  * A strategy's entry/exit SIGNALS use information up to and including the CLOSE of bar i.
  * ENTRY: market (taker) at the OPEN of bar i+1, paying half-spread + slippage + taker fee.
  * STOP (stop-market, taker): triggered when a bar's LOW <= stop. If the bar OPENS at/below the
    stop (gap) the fill is the open, otherwise the stop price; stop slippage is applied adversely.
  * TAKE-PROFIT (resting limit, maker): fills at the target only if a bar's HIGH > target (strict:
    touching is not a fill). No slippage.
  * If stop and target are both inside the same bar, the STOP is assumed first (worst case).
  * The entry bar itself is checked for stop/target after the open.
  * SIGNAL / TIME exits: taker at the OPEN of the next bar.
  * Trailing stops update at each bar CLOSE and apply from the next bar.
  * One position at a time; signals while in a position are ignored. Long only, no leverage:
    position value is capped by cash (sizing happens in ``simulate_account``).
  * ``window=(t0, t1)`` restricts entries to signal bars in [t0, t1) and force-closes open trades
    at the first bar >= t1 (so train/test windows never share a trade).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from backtest.costs import CostModel


@dataclass
class Signals:
    entry: np.ndarray                    # bool, signal at bar close
    stop_dist: np.ndarray                # float >0, price distance below the entry fill reference
    tp_dist: Optional[np.ndarray] = None # float or NaN (no target)
    exit_sig: Optional[np.ndarray] = None  # bool, exit at next open
    max_hold: Optional[int] = None       # bars; exit at next open once held this many bars
    trail_dist: Optional[np.ndarray] = None  # float: trailing stop distance below the close


@dataclass
class RawTrade:
    signal_i: int
    entry_i: int
    exit_i: int
    entry_ref: float        # raw open price at entry
    exit_ref: float         # raw reference price (stop/target/open) before costs
    stop0: float            # initial stop
    exit_type: str          # stop | target | signal | time | window_end | data_end


def generate_trades(df: pd.DataFrame, sig: Signals, window: Optional[tuple] = None) -> list[RawTrade]:
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(df)
    idx = df.index
    lo_i, hi_i = 0, n
    if window is not None:
        lo_i = int(idx.searchsorted(pd.Timestamp(window[0])))
        hi_i = int(idx.searchsorted(pd.Timestamp(window[1])))
    entry = np.asarray(sig.entry, bool)
    stop_d = np.asarray(sig.stop_dist, float)
    tp_d = None if sig.tp_dist is None else np.asarray(sig.tp_dist, float)
    ex = None if sig.exit_sig is None else np.asarray(sig.exit_sig, bool)
    tr = None if sig.trail_dist is None else np.asarray(sig.trail_dist, float)
    trades: list[RawTrade] = []
    i = lo_i
    cand = np.flatnonzero(entry[lo_i:hi_i]) + lo_i
    ci = 0
    while ci < len(cand):
        i = cand[ci]
        ci += 1
        j0 = i + 1
        if j0 >= hi_i or j0 >= n or not (stop_d[i] > 0) or not np.isfinite(stop_d[i]):
            continue
        e = o[j0]
        stop = e - stop_d[i]
        if stop <= 0:
            continue
        tp = e + tp_d[i] if tp_d is not None and np.isfinite(tp_d[i]) else np.inf
        exit_i, exit_ref, etype = None, None, None
        j = j0
        while j < hi_i:
            if j > j0 and o[j] <= stop:
                exit_i, exit_ref, etype = j, o[j], "stop"
                break
            if l[j] <= stop:
                exit_i, exit_ref, etype = j, stop, "stop"
                break
            if h[j] > tp:
                exit_i, exit_ref, etype = j, tp, "target"
                break
            if ex is not None and ex[j] and j + 1 < n:
                if j + 1 >= hi_i:
                    exit_i, exit_ref, etype = j + 1, o[j + 1], "window_end"
                else:
                    exit_i, exit_ref, etype = j + 1, o[j + 1], "signal"
                break
            if sig.max_hold is not None and (j - j0 + 1) >= sig.max_hold and j + 1 < n:
                exit_i, exit_ref, etype = j + 1, o[j + 1], ("time" if j + 1 < hi_i else "window_end")
                break
            if tr is not None and np.isfinite(tr[j]):
                stop = max(stop, c[j] - tr[j])
            j += 1
        if exit_i is None:
            if hi_i < n:
                exit_i, exit_ref, etype = hi_i, o[hi_i], "window_end"
            else:
                exit_i, exit_ref, etype = n - 1, c[n - 1], "data_end"
        trades.append(RawTrade(int(i), int(j0), int(exit_i), float(e), float(exit_ref), float(e - stop_d[i]), etype))
        # next candidate must signal at or after the exit bar (flat from exit onwards)
        while ci < len(cand) and cand[ci] < exit_i:
            ci += 1
    return trades


@dataclass
class AccountResult:
    trades: pd.DataFrame
    equity: pd.Series                 # mark-to-market at bar closes
    start: float
    skipped_min_order: int = 0
    params: dict = field(default_factory=dict)


def simulate_account(df: pd.DataFrame, raw: list[RawTrade], costs: CostModel, start: float = 1000.0,
                     risk: float = 0.01, min_order_usd: float = 1.0, fixed_fraction: Optional[float] = None
                     ) -> AccountResult:
    """Compound a trade list on a cash-only account.

    Size = risk * equity / (entry_ref - initial_stop) BTC, capped so value + fees <= cash (no leverage).
    ``fixed_fraction`` (e.g. 1.0) instead invests that fraction of cash per trade (diagnostics).
    """
    close = df.close.to_numpy(float)
    n = len(df)
    eq = np.full(n, np.nan)
    eq[0] = start
    cash = start
    rows, skipped = [], 0
    for t in raw:
        e_imp = costs.taker_price_impact()
        e_fill = t.entry_ref * (1 + e_imp)
        dist = t.entry_ref - t.stop0
        if fixed_fraction is not None:
            qty = fixed_fraction * cash / (e_fill * (1 + costs.taker_fee))
        else:
            qty = min(risk * cash / dist, cash / (e_fill * (1 + costs.taker_fee)))
        if qty * e_fill < min_order_usd or qty <= 0:
            skipped += 1
            continue
        e_fee = qty * e_fill * costs.taker_fee
        if t.exit_type == "target":
            x_fill, x_fee_rate = t.exit_ref, costs.maker_fee
        else:
            x_imp = costs.taker_price_impact(is_stop=(t.exit_type == "stop"))
            x_fill, x_fee_rate = t.exit_ref * (1 - x_imp), costs.taker_fee
        x_fee = qty * x_fill * x_fee_rate
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
                         qty=qty, notional=qty * e_fill, gross=gross, fees=fees, slippage=slip, net=net,
                         ret=net / eq_before, r_mult=(net / (qty * dist)) if dist > 0 else np.nan,
                         bars=t.exit_i - t.entry_i + (0 if t.exit_type in ("signal", "time", "window_end") else 1),
                         equity_after=cash))
    s = pd.Series(eq, index=df.index).ffill()
    return AccountResult(pd.DataFrame(rows), s, start, skipped)
