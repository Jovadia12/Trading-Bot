"""Objective EMA-trend + BOS + Fibonacci + FVG continuation strategy (and its "Unicorn" variant).

Research only (see FIB_FVG_STUDY.md for the exact definitions and every assumption). Nothing here is used by
the paper runner. All signals use COMPLETED candles only; entries fill at the NEXT 5m open.

Pipeline per coin:
  indicators_5m / indicators_15m -> find_signals (setup state machine, one trade per setup)
  -> simulate_trades (per variant: stop + exit rule, 5m fills, 15m management) -> portfolio (10% equity/trade).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from backtest import indicators as ind


# ------------------------------------------------------------------------------------------- parameters
@dataclass(frozen=True)
class Rules:
    swing_k: int = 3                 # 5m fractal: pivot must beat 3 bars on each side; confirmed 3 bars later
    swing_k_15m: int = 3             # same on 15m (exit/trailing structure)
    fib_shallow: float = 0.382       # retracement band [38.2%, 61.8%] of the impulse
    fib_deep: float = 0.618
    setup_expiry_bars: int = 288     # a BOS setup lives at most 24h of 5m bars
    unicorn_tol_atr: float = 0.25    # EMA200 within the confluence zone +/- 0.25 x ATR14(5m)
    min_impulse_atr: float = 3.0     # impulse (H - L) must span >= 3 x ATR14(5m) at the trigger bar (ignore micro-structure)
    struct_buffer_atr: float = 0.10  # structural stops sit 0.1 x ATR beyond the level
    atr_n: int = 14


@dataclass(frozen=True)
class Costs:
    name: str
    maker_fee: float
    taker_fee: float
    half_spread: float = 0.00005
    slippage: float = 0.0002
    stop_slippage: float = 0.0005
    maker_entries: bool = False      # entries and fixed TPs as resting limits (maker fee, no spread/slippage)
    note: str = ""

    def impact(self, stop: bool = False) -> float:
        return self.half_spread + self.slippage + (self.stop_slippage if stop else 0.0)


COST_CASES = [
    Costs("coinbase_taker", 0.005, 0.009, note="your Coinbase Intro tier: every leg taker 0.90% + 0.025% spread/slippage "
                                               "(+0.05% on stops)"),
    Costs("coinbase_maker_like", 0.005, 0.009, maker_entries=True,
          note="entries and fixed take-profits at maker 0.50% assuming the limit fills at the next open (OPTIMISTIC: "
               "no missed fills); stops and signal/trailing exits stay taker 0.90% + slippage"),
    Costs("low_fee_venue_reference", 0.0002, 0.0005, maker_entries=True,
          note="REFERENCE ONLY, not your account: typical perp-exchange base tier (maker 0.02%, taker 0.05%)"),
]


# ------------------------------------------------------------------------------------------- structure
def swings(high: np.ndarray, low: np.ndarray, k: int):
    """Fractal pivots. Bar i is a swing high if high[i] > every high in [i-k, i+k] except itself (strict);
    swing low mirrored. A pivot is CONFIRMED at the close of bar i+k (it needs k later bars) and is only usable
    from then on. Returns, for every bar t, the price and pivot index of the most recent pivot confirmed at or
    before t (NaN / -1 if none)."""
    n = len(high)
    sh_px, sl_px = np.full(n, np.nan), np.full(n, np.nan)
    sh_ix, sl_ix = np.full(n, -1), np.full(n, -1)
    hs, ls = pd.Series(high), pd.Series(low)
    left_h = hs.shift(1).rolling(k, min_periods=k).max().to_numpy()
    right_h = hs[::-1].shift(1).rolling(k, min_periods=k).max()[::-1].to_numpy()
    left_l = ls.shift(1).rolling(k, min_periods=k).min().to_numpy()
    right_l = ls[::-1].shift(1).rolling(k, min_periods=k).min()[::-1].to_numpy()
    is_sh = (high > left_h) & (high > right_h)
    is_sl = (low < left_l) & (low < right_l)
    cur_h, cur_hi, cur_l, cur_li = np.nan, -1, np.nan, -1
    for t in range(n):
        p = t - k                        # pivot that becomes confirmed at the close of bar t
        if p >= 0:
            if is_sh[p]:
                cur_h, cur_hi = high[p], p
            if is_sl[p]:
                cur_l, cur_li = low[p], p
        sh_px[t], sh_ix[t], sl_px[t], sl_ix[t] = cur_h, cur_hi, cur_l, cur_li
    return sh_px, sh_ix, sl_px, sl_ix


def fvgs(high: np.ndarray, low: np.ndarray):
    """3-candle fair value gaps, indexed by the THIRD candle j (known at its close).
    Bullish at j: high[j-2] < low[j] -> zone [high[j-2], low[j]]. Bearish at j: low[j-2] > high[j] -> [high[j], low[j-2]]."""
    n = len(high)
    bull = np.zeros(n, bool)
    bear = np.zeros(n, bool)
    bull[2:] = high[:-2] < low[2:]
    bear[2:] = low[:-2] > high[2:]
    return bull, bear


def indicators_5m(df: pd.DataFrame, r: Rules = Rules()) -> dict:
    c = df.close
    out = {k: df[k].to_numpy(float) for k in ("open", "high", "low", "close")}
    out["ema20"], out["ema50"], out["ema200"] = (ind.ema(c, n).to_numpy() for n in (20, 50, 200))
    out["atr"] = ind.atr(df, r.atr_n).to_numpy()
    out["sh_px"], out["sh_ix"], out["sl_px"], out["sl_ix"] = swings(out["high"], out["low"], r.swing_k)
    out["fvg_bull"], out["fvg_bear"] = fvgs(out["high"], out["low"])
    warm = np.arange(len(df)) >= 200
    out["trend_long"] = warm & (out["ema20"] > out["ema50"]) & (out["ema50"] > out["ema200"]) & (out["close"] > out["ema200"])
    out["trend_short"] = warm & (out["ema20"] < out["ema50"]) & (out["ema50"] < out["ema200"]) & (out["close"] < out["ema200"])
    return out


def resample_15m(df5: pd.DataFrame) -> pd.DataFrame:
    """UTC-aligned 15m bars built only from COMPLETE groups of three 5m bars."""
    g = df5.resample("15min", label="left", closed="left")
    out = g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out[g.close.count() == 3]


def management_15m(df5: pd.DataFrame, r: Rules = Rules()) -> dict:
    """15m exit/trailing information mapped onto the 5m grid WITHOUT look-ahead: a 15m bar starting at T is
    complete at T+15m, so its values are usable from the 5m bar that OPENS at T+15m onwards."""
    d15 = resample_15m(df5)
    h, l, c = (d15[k].to_numpy(float) for k in ("high", "low", "close"))
    e20, e50 = ind.ema(d15.close, 20).to_numpy(), ind.ema(d15.close, 50).to_numpy()
    a15 = ind.atr(d15, r.atr_n).to_numpy()
    sh, _shi, sl, _sli = swings(h, l, r.swing_k_15m)
    warm = np.arange(len(d15)) >= 50
    exit_long = warm & ((e20 < e50) | (c < sl))       # opposite EMA or bearish 15m structure break
    exit_short = warm & ((e20 > e50) | (c > sh))
    avail = d15.index + pd.Timedelta(minutes=15)      # time from which the completed 15m bar is known
    frame = pd.DataFrame({"exit_long": exit_long, "exit_short": exit_short,
                          "trail_long": sl - r.struct_buffer_atr * a15, "trail_short": sh + r.struct_buffer_atr * a15,
                          "src": df5.index.searchsorted(avail)}, index=avail)
    m = frame.reindex(df5.index, method="ffill")       # last 15m info available at each 5m bar's OPEN
    return {"exit_long": m.exit_long.fillna(False).to_numpy(bool), "exit_short": m.exit_short.fillna(False).to_numpy(bool),
            "trail_long": m.trail_long.to_numpy(float), "trail_short": m.trail_short.to_numpy(float),
            # first 5m bar at whose open this 15m bar's information was available
            "src": m.src.fillna(-1).to_numpy(int)}


# --------------------------------------------------------------------------------------------- signals
@dataclass
class Signal:
    i: int                 # signal bar (completed); entry at the open of i+1
    side: str              # "long" | "short"
    zone_lo: float
    zone_hi: float
    fvg_edge: float        # far edge of the FVG (long: FVG low; short: FVG high)
    impulse_start: float   # L (long) / H (short)
    impulse_end: float     # H (long) / L (short)
    atr: float
    bos_i: int
    trigger_extreme: float  # low (long) / high (short) of the signal bar


def find_signals(x: dict, unicorn: bool = False, r: Rules = Rules(), lo_i: int = 0, hi_i: Optional[int] = None) -> list[Signal]:
    """Setup state machine (see FIB_FVG_STUDY.md). Only data up to each bar's close is used."""
    o, h, l, c = x["open"], x["high"], x["low"], x["close"]
    n = len(c)
    hi_i = n if hi_i is None else hi_i
    out: list[Signal] = []
    for side in ("long", "short"):
        bull = side == "long"
        setup = None
        broken = -1                                       # pivot index already used for a BOS
        for t in range(max(lo_i, 3), hi_i):
            # ---- 1) manage an existing setup with information up to bar t-1, then test bar t as trigger
            if setup is not None:
                if t > setup["expires"]:
                    setup = None
            if setup is not None:
                L, H = setup["L"], setup["H"]
                rng = H - L
                if bull:
                    fib_lo, fib_hi = H - r.fib_deep * rng, H - r.fib_shallow * rng
                else:
                    fib_lo, fib_hi = L + r.fib_shallow * rng, L + r.fib_deep * rng
                # invalidations decided at this bar's close
                if (bull and c[t] < L) or ((not bull) and c[t] > H):
                    setup = None
                else:
                    zone = None
                    for (j, f_lo, f_hi) in reversed(setup["fvgs"]):     # most recent valid FVG first
                        z_lo, z_hi = max(f_lo, fib_lo), min(f_hi, fib_hi)
                        if z_lo < z_hi:
                            zone = (z_lo, z_hi, f_lo if bull else f_hi)
                            break
                    trend = x["trend_long"][t] if bull else x["trend_short"][t]
                    big = rng >= r.min_impulse_atr * x["atr"][t]
                    if zone is not None and trend and big and t > setup["ext_i"]:
                        z_lo, z_hi, edge = zone
                        mid = 0.5 * (z_lo + z_hi)
                        if bull:
                            react = l[t] <= z_hi and c[t] > o[t] and c[t] > mid
                        else:
                            react = h[t] >= z_lo and c[t] < o[t] and c[t] < mid
                        ok = react
                        if ok and unicorn:
                            tol = r.unicorn_tol_atr * x["atr"][t]
                            ok = (z_lo - tol) <= x["ema200"][t] <= (z_hi + tol)
                        if ok and np.isfinite(x["atr"][t]):
                            out.append(Signal(t, side, z_lo, z_hi, edge, L if bull else H, H if bull else L,
                                              float(x["atr"][t]), setup["bos_i"], l[t] if bull else h[t]))
                            setup = None                         # one trade per setup
                    # FVG bookkeeping (after the trigger test: an FVG completing at t is usable from t+1)
                    if setup is not None:
                        setup["fvgs"] = [(j, a, b) for (j, a, b) in setup["fvgs"]
                                         if (c[t] >= a if bull else c[t] <= b)]          # closed through -> dead
                        if bull and x["fvg_bull"][t] and t - 2 > setup["L_i"]:
                            setup["fvgs"].append((t, h[t - 2], l[t]))
                        if (not bull) and x["fvg_bear"][t] and t - 2 > setup["H_i"]:
                            setup["fvgs"].append((t, h[t], l[t - 2]))
                        # impulse extension (new extreme) -> zone re-anchors from the next bar
                        if bull and h[t] > setup["H"]:
                            setup["H"], setup["ext_i"] = h[t], t
                        if (not bull) and l[t] < setup["L"]:
                            setup["L"], setup["ext_i"] = l[t], t
            # ---- 2) break of structure at bar t (close beyond the last CONFIRMED pivot) -> new setup
            if bull:
                lvl, piv = x["sh_px"][t], x["sh_ix"][t]
                bos = piv >= 0 and piv != broken and c[t] > lvl
            else:
                lvl, piv = x["sl_px"][t], x["sl_ix"][t]
                bos = piv >= 0 and piv != broken and c[t] < lvl
            if bos:
                broken = piv
                seg = slice(piv + 1, t + 1)
                if bull:
                    li = piv + 1 + int(np.argmin(l[seg]))       # impulse origin: lowest low after the broken high
                    L, Li = l[li], li
                    H = float(np.max(h[li:t + 1]))
                    fv = [(j, h[j - 2], l[j]) for j in range(li + 2, t + 1) if x["fvg_bull"][j]]
                    setup = {"L": L, "L_i": Li, "H": H, "H_i": t, "ext_i": t, "bos_i": t, "fvgs": fv,
                             "expires": t + r.setup_expiry_bars}
                else:
                    hi_ = piv + 1 + int(np.argmax(h[seg]))      # impulse origin: highest high after the broken low
                    H, Hi = h[hi_], hi_
                    L = float(np.min(l[hi_:t + 1]))
                    fv = [(j, h[j], l[j - 2]) for j in range(hi_ + 2, t + 1) if x["fvg_bear"][j]]
                    setup = {"L": L, "L_i": t, "H": H, "H_i": Hi, "ext_i": t, "bos_i": t, "fvgs": fv,
                             "expires": t + r.setup_expiry_bars}
                # drop FVGs already closed through before the BOS bar
                setup["fvgs"] = [(j, a, b) for (j, a, b) in setup["fvgs"]
                                 if (np.all(c[j + 1:t + 1] >= a) if bull else np.all(c[j + 1:t + 1] <= b))]
    out.sort(key=lambda s: (s.i, s.side))
    return out


# --------------------------------------------------------------------------------------------- trades
@dataclass
class Trade:
    coin: str
    side: str
    signal_i: int
    entry_i: int
    exit_i: int
    entry_ref: float
    exit_ref: float
    stop0: float
    exit_type: str
    entry_maker: bool
    exit_maker: bool
    version: str = ""
    variant: str = ""


def stop_price(sig: Signal, entry: float, stop_kind: str, r: Rules = Rules()) -> float:
    if stop_kind == "struct":
        b = r.struct_buffer_atr * sig.atr
        return (min(sig.fvg_edge, sig.trigger_extreme) - b) if sig.side == "long" else (max(sig.fvg_edge, sig.trigger_extreme) + b)
    k = float(stop_kind.replace("atr", ""))
    return entry - k * sig.atr if sig.side == "long" else entry + k * sig.atr


def simulate_trades(coin: str, x: dict, m15: dict, signals: list[Signal], stop_kind: str, exit_kind: str,
                    costs: Costs, lo_i: int = 0, hi_i: Optional[int] = None, r: Rules = Rules()) -> list[Trade]:
    """One position per coin. Entry at open[i+1]. Exit rules (5m fills):
      A: initial stop + exit at the next 5m open after a completed 15m bar shows the opposite EMA/structure condition
      B: initial stop, then trail to the latest confirmed 15m swing (+/-0.1 ATR15), only ever tightened
      R3/R5: initial stop + fixed take-profit at 3R / 5R (strict: price must trade THROUGH the target)
    Stop and target in the same bar -> stop first. A bar opening beyond the stop fills at the open.
    Trades still open at hi_i are closed at that bar's open (window end)."""
    o, h, l, c = x["open"], x["high"], x["low"], x["close"]
    n = len(c)
    hi_i = n if hi_i is None else hi_i
    trades: list[Trade] = []
    free_from = lo_i
    tp_mult = {"R3": 3.0, "R5": 5.0}.get(exit_kind)
    for s in signals:
        e_i = s.i + 1
        if s.i < lo_i or e_i >= hi_i or s.i < free_from:
            continue
        long = s.side == "long"
        entry = o[e_i]
        stop = stop_price(s, entry, stop_kind, r)
        R = (entry - stop) if long else (stop - entry)
        if not (R > 0) or not np.isfinite(R):
            continue
        tp = (entry + tp_mult * R if long else entry - tp_mult * R) if tp_mult else None
        ex_i, ex_ref, etype, xm = None, None, None, False
        moved = False
        for j in range(e_i, hi_i):
            fresh = m15["src"][j] > e_i            # 15m bar completed AFTER the entry open
            if j > e_i and fresh:
                if exit_kind == "A" and (m15["exit_long"][j] if long else m15["exit_short"][j]):
                    ex_i, ex_ref, etype = j, o[j], "15m_opposite"      # signal completed before this open
                    break
                if exit_kind == "B":
                    tr = m15["trail_long"][j] if long else m15["trail_short"][j]
                    if np.isfinite(tr):
                        new = max(stop, tr) if long else min(stop, tr)
                        moved = moved or new != stop
                        stop = new
            gap = (o[j] <= stop) if long else (o[j] >= stop)
            hit = (l[j] <= stop) if long else (h[j] >= stop)
            if j > e_i and gap:
                ex_i, ex_ref, etype = j, o[j], "trail_gap" if moved else "stop_gap"
                break
            if hit:
                ex_i, ex_ref, etype = j, stop, "trail" if moved else "stop"
                break
            if tp is not None and ((h[j] > tp) if long else (l[j] < tp)):
                ex_i, ex_ref, etype, xm = j, tp, f"target_{exit_kind}", costs.maker_entries
                break
        if ex_i is None:
            ex_i = hi_i if hi_i < n else n - 1
            ex_ref = o[ex_i] if hi_i < n else c[n - 1]
            etype = "window_end" if hi_i < n else "data_end"
        trades.append(Trade(coin, s.side, s.i, e_i, ex_i, float(entry), float(ex_ref), float((entry - R) if long else (entry + R)),
                            etype, costs.maker_entries, xm))
        free_from = ex_i                                      # next signal must come at/after the exit bar
    return trades


# -------------------------------------------------------------------------------------------- portfolio
def portfolio(trades: list[Trade], closes: dict, index: pd.DatetimeIndex, costs: Costs, start: float = 200.0,
              alloc: float = 0.10) -> tuple[pd.DataFrame, pd.Series]:
    """Chronological account: each entry uses `alloc` x current equity as notional (1x; shorts lock the notional as
    cash collateral), capped by available cash. Equity is marked to market at every 5m close on `index`.
    closes: coin -> close array aligned to `index`."""
    import heapq
    order = sorted(trades, key=lambda t: (t.entry_i, t.coin))
    n = len(index)
    cash = start
    cash_delta = np.zeros(n + 1)
    mtm = np.zeros(n)
    open_pos = {}            # k -> (trade, qty, fill)
    rows = []
    pending = []             # heap of (exit_i, k) for OPEN trades

    def close_out(k):
        nonlocal cash
        t, qty, e_fill, notional, e_fee, e_slip = open_pos.pop(k)
        long = t.side == "long"
        if t.exit_maker:
            x_fill, x_rate = t.exit_ref, costs.maker_fee
        else:
            imp = costs.impact(stop=t.exit_type.startswith(("stop", "trail")))
            x_fill = t.exit_ref * (1 - imp) if long else t.exit_ref * (1 + imp)
            x_rate = costs.taker_fee
        x_fee = qty * x_fill * x_rate
        gross = qty * (x_fill - e_fill) if long else qty * (e_fill - x_fill)
        back = (qty * x_fill if long else notional + gross) - x_fee
        cash += back
        cash_delta[t.exit_i] += back
        pnl = gross - e_fee - x_fee
        R = abs(t.entry_ref - t.stop0)
        rows.append({"coin": t.coin, "side": t.side, "entry_time": index[t.entry_i], "exit_time": index[t.exit_i],
                     "entry_ref": t.entry_ref, "entry_fill": e_fill, "exit_ref": t.exit_ref, "exit_fill": x_fill,
                     "stop0": t.stop0, "qty": qty, "notional": notional, "fees": e_fee + x_fee,
                     "slippage": e_slip + qty * abs(x_fill - t.exit_ref), "pnl": pnl, "ret": pnl / notional,
                     "r_mult": pnl / (qty * R) if R > 0 else np.nan, "exit_type": t.exit_type,
                     "bars": t.exit_i - t.entry_i})

    for k, t in enumerate(order):
        # free the cash of trades that exited BEFORE this entry bar (an exit inside the entry bar is not reusable
        # at that bar's open)
        while pending and pending[0][0] < t.entry_i:
            close_out(heapq.heappop(pending)[1])
        long = t.side == "long"
        eq = cash + sum((q * closes[p.coin][max(t.entry_i - 1, 0)] if p.side == "long"
                         else nt + q * (f - closes[p.coin][max(t.entry_i - 1, 0)]))
                        for p, q, f, nt, _ef, _es in open_pos.values())
        if t.entry_maker:
            e_fill, e_rate = t.entry_ref, costs.maker_fee
        else:
            e_fill = t.entry_ref * (1 + costs.impact()) if long else t.entry_ref * (1 - costs.impact())
            e_rate = costs.taker_fee
        notional = min(alloc * eq, cash / (1 + e_rate))
        if notional < 1.0:
            continue
        qty = notional / e_fill
        e_fee = notional * e_rate
        cash -= notional + e_fee
        cash_delta[t.entry_i] -= notional + e_fee
        cl = closes[t.coin]
        seg = slice(t.entry_i, t.exit_i)
        mtm[seg] += qty * cl[seg] if long else notional + qty * (e_fill - cl[seg])
        open_pos[k] = (t, qty, e_fill, notional, e_fee, qty * abs(e_fill - t.entry_ref))
        heapq.heappush(pending, (t.exit_i, k))
    while pending:
        close_out(heapq.heappop(pending)[1])
    equity = pd.Series(start + np.cumsum(cash_delta[:n]) + mtm, index=index)
    return pd.DataFrame(rows), equity
