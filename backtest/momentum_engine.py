"""Position engine with partial exits, breakeven and highest-close trailing stops (study "momentum").

Execution rules (conservative, no look-ahead; see MOMENTUM_BREAKOUT_PROTOCOL.md):
  * Signals use completed bars only. Entry is on the NEXT bar:
      taker: market at the next bar's open;
      maker: post-only limit at the signal close for one bar, filled only if the bar's low trades THROUGH it by
             `penetration`; otherwise the trade is MISSED (never chased). Fill = limit price.
  * 1R = stop_atr x ATR(signal bar). Initial stop = entry - 1R. Stops are stop-market (TAKER) orders: a bar that
    opens at/below the stop fills at the open, otherwise at the stop, plus stop slippage.
  * Maker entry bar: its high may precede the fill, so it never counts for the target or the +time_exit_r check.
  * Partial exit: `partial_frac` is sold when a bar's HIGH is strictly above entry + partial_r x R, at that price
    (taker case: charged as a taker exit; maker case: resting limit, maker fee).
  * Same bar contains the stop and the target -> the STOP is assumed first (whole remaining position).
  * After the partial: the remaining stop moves to breakeven (entry price) and the trail becomes active, both
    from the NEXT bar (intrabar order is unknown).
  * Trail = highest close since entry - trail_atr x ATR(current bar), updated at each close, never lowered.
  * Time exit: after `time_exit_hours` of holding, if no bar's high has exceeded entry + time_exit_r x R and no
    partial has filled, exit at the next bar (taker: market at open; maker: one-bar limit at the close, else
    taker at the following open). The stop stays active meanwhile.
  * Windows are isolated: entries only from signal bars inside the window; anything still open at the window
    end is closed (taker) at the first bar outside it. One position at a time, long only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from backtest.costs import CostModel
from backtest.engine import AccountResult
from backtest.strategies_momentum import MomentumSignals


@dataclass
class Leg:
    frac: float
    exit_i: int
    exit_ref: float
    exit_type: str        # stop | partial_target | time | time_maker | time_taker_fallback | window_end | data_end
    maker: bool = False


@dataclass
class Position:
    signal_i: int
    entry_i: int
    entry_ref: float
    stop0: float
    entry_maker: bool
    legs: list = field(default_factory=list)

    @property
    def exit_i(self) -> int:
        return max(l.exit_i for l in self.legs)


def generate_positions(df: pd.DataFrame, sig: MomentumSignals, window: Optional[tuple] = None, mode: str = "taker",
                       penetration: float = 0.001, stats: Optional[dict] = None) -> list[Position]:
    if mode not in ("taker", "maker"):
        raise ValueError(mode)
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(df)
    lo_i, hi_i = 0, n
    if window is not None:
        lo_i = int(df.index.searchsorted(pd.Timestamp(window[0])))
        hi_i = int(df.index.searchsorted(pd.Timestamp(window[1])))
    spec, atr = sig.exit, np.asarray(sig.atr, float)
    time_bars = None if spec.time_exit_hours is None else int(round(spec.time_exit_hours / sig.bar_hours))
    st = {"entry_signals": 0, "missed_entries": 0, "partials": 0, "time_exits": 0}
    out: list[Position] = []
    cand = np.flatnonzero(np.asarray(sig.entry, bool)[lo_i:hi_i]) + lo_i
    ci = 0
    while ci < len(cand):
        i = cand[ci]
        ci += 1
        j0 = i + 1
        if j0 >= hi_i or j0 >= n or not (np.isfinite(atr[i]) and atr[i] > 0):
            continue
        st["entry_signals"] += 1
        if mode == "taker":
            e, e_maker = o[j0], False
        else:
            if not (l[j0] < c[i] * (1 - penetration)):
                st["missed_entries"] += 1
                continue
            e, e_maker = c[i], True
        R = spec.stop_atr * atr[i]
        stop = e - R
        if stop <= 0:
            continue
        pos = Position(int(i), int(j0), float(e), float(stop), e_maker)
        target = e + spec.partial_r * R if spec.partial_r is not None else np.inf
        reach = e + spec.time_exit_r * R
        remaining, partial_done, reached, hc = 1.0, False, False, -np.inf
        pending, x_lim, done = None, np.nan, False
        j = j0
        while j < hi_i:
            if (j > j0 and o[j] <= stop) or l[j] <= stop:
                ref = o[j] if o[j] <= stop else stop
                pos.legs.append(Leg(remaining, j, float(ref), "stop"))
                done = True
                break
            if pending == j:
                if h[j] > x_lim * (1 + penetration):
                    pos.legs.append(Leg(remaining, j, float(x_lim), "time_maker", True))
                elif j + 1 < n:
                    pos.legs.append(Leg(remaining, j + 1, float(o[j + 1]),
                                        "window_end" if j + 1 >= hi_i else "time_taker_fallback"))
                else:
                    j += 1
                    continue
                done = True
                break
            # maker entry bar: the high may have printed BEFORE our limit filled, so it cannot count
            hi_ok = not (e_maker and j == j0)
            if hi_ok and not partial_done and h[j] > target:
                pos.legs.append(Leg(spec.partial_frac, j, float(target), "partial_target", mode == "maker"))
                remaining -= spec.partial_frac
                partial_done = True
                st["partials"] += 1
            reached = reached or (hi_ok and h[j] > reach)
            hc = max(hc, c[j])
            if (pending is None and time_bars is not None and not reached and not partial_done
                    and (j - j0 + 1) >= time_bars and j + 1 < n):
                st["time_exits"] += 1
                if j + 1 >= hi_i:
                    pos.legs.append(Leg(remaining, j + 1, float(o[j + 1]), "window_end"))
                    done = True
                    break
                if mode == "taker":
                    pos.legs.append(Leg(remaining, j + 1, float(o[j + 1]), "time"))
                    done = True
                    break
                pending, x_lim = j + 1, c[j]
            if partial_done and spec.breakeven_after_partial:
                stop = max(stop, e)
            if (spec.trail_from_entry or partial_done) and np.isfinite(atr[j]):
                stop = max(stop, hc - spec.trail_atr * atr[j])
            j += 1
        if not done:
            if hi_i < n:
                pos.legs.append(Leg(remaining, hi_i, float(o[hi_i]), "window_end"))
            else:
                pos.legs.append(Leg(remaining, n - 1, float(c[n - 1]), "data_end"))
        out.append(pos)
        ex = pos.exit_i
        while ci < len(cand) and cand[ci] < ex:
            ci += 1
    if stats is not None:
        stats.update(st)
    return out


_AT_OPEN = ("time", "time_taker_fallback", "window_end")


def simulate_positions(df: pd.DataFrame, positions: list[Position], costs: CostModel, start: float = 10_000.0,
                       risk: float = 0.01, min_order_usd: float = 1.0) -> AccountResult:
    """Cash-only compounding. Size = risk * equity / (entry - initial stop), capped so value + entry fee <= cash.
    Maker legs: maker fee at the limit, no spread/slippage. Taker legs: taker fee + half-spread + slippage
    (+ stop slippage on stops). Equity is marked to market at every close, including partially closed positions."""
    close = df.close.to_numpy(float)
    n = len(df)
    eq = np.full(n, np.nan)
    eq[0] = start
    cash = start
    rows, skipped = [], 0
    for p in positions:
        if p.entry_maker:
            e_fill, e_rate = p.entry_ref, costs.maker_fee
        else:
            e_fill, e_rate = p.entry_ref * (1 + costs.taker_price_impact()), costs.taker_fee
        dist = p.entry_ref - p.stop0
        qty = min(risk * cash / dist, cash / (e_fill * (1 + e_rate)))
        if qty * e_fill < min_order_usd or qty <= 0:
            skipped += 1
            continue
        e_fee = qty * e_fill * e_rate
        cash_after_entry = cash - qty * e_fill - e_fee
        a, b = p.entry_i, p.exit_i
        mtm = np.full(max(b - a, 0), cash_after_entry)
        gross = slip = fees = 0.0
        for leg in p.legs:
            q = qty * leg.frac
            if leg.maker:
                x_fill, x_rate = leg.exit_ref, costs.maker_fee
            else:
                x_fill = leg.exit_ref * (1 - costs.taker_price_impact(is_stop=(leg.exit_type == "stop")))
                x_rate = costs.taker_fee
            proceeds = q * x_fill * (1 - x_rate)
            k = leg.exit_i - a                      # bars [a, exit_i) hold this leg; from exit_i on it is cash
            if k > 0:
                mtm[:k] += q * close[a:leg.exit_i]
            mtm[k:] += proceeds
            gross += q * (leg.exit_ref - p.entry_ref)
            slip += q * (leg.exit_ref - x_fill)
            fees += q * x_fill * x_rate
        slip += qty * (e_fill - p.entry_ref)
        fees += e_fee
        net = gross - slip - fees
        if b > a:
            eq[a:b] = mtm
        eq_before = cash
        cash += net
        eq[b] = cash
        last = max(p.legs, key=lambda x: x.exit_i)
        rows.append(dict(entry_time=df.index[p.entry_i], exit_time=df.index[b], signal_time=df.index[p.signal_i],
                         entry_ref=p.entry_ref, stop0=p.stop0, entry_maker=p.entry_maker,
                         exit_type="+".join(x.exit_type for x in p.legs), partial=any(x.exit_type == "partial_target" for x in p.legs),
                         qty=qty, notional=qty * e_fill, gross=gross, fees=fees, slippage=slip, net=net,
                         ret=net / eq_before, r_mult=net / (qty * dist) if dist > 0 else np.nan,
                         bars=b - a + (0 if last.exit_type in _AT_OPEN else 1), equity_after=cash))
    return AccountResult(pd.DataFrame(rows), pd.Series(eq, index=df.index).ffill(), start, skipped)
