"""multi_crypto_momentum: signals, execution timing, regime filter, caps, priority, costs, accounting, data
loading, backtest pipeline and the paper session (synthetic data and fake HTTP only -- no network)."""
import ast
import io
import json
import math
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from strategy.multi_crypto_momentum import (LONG, SHORT, UNIVERSE, MCMEngine, MCMParams, Portfolio, build_states,
                                            indicators)

P = MCMParams()
REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------------------- helpers
def series(n=600, drift=0.0, seed=0, start="2020-01-01", vol=0.02, p0=100.0):
    rng = np.random.default_rng(seed)
    close = p0 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    op = np.r_[p0, close[:-1]] * (1 + rng.normal(0, 0.001, n))
    hi = np.maximum(op, close) * 1.01
    lo = np.minimum(op, close) * 0.99
    idx = pd.date_range(start, periods=n, freq="1D", tz="UTC")
    return pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close, "volume": 1.0}, index=idx)


def frames10(n=700, seed=1):
    return {c: series(n, drift=(0.002 if i % 3 == 0 else -0.001 if i % 3 == 1 else 0.0), seed=seed + i)
            for i, c in enumerate(UNIVERSE)}


def state(close=100.0, ret=0.1, ema=90.0, long=None, short=None, regime_long=True, regime_short=True):
    raw_long = ret > P.long_threshold and close > ema
    raw_short = ret < P.short_threshold and close < ema
    return pd.Series({"close": close, "ret": ret, "ema": ema, "raw_long": raw_long, "raw_short": raw_short,
                      "regime_ok_long": regime_long, "regime_ok_short": regime_short,
                      "long_sig": raw_long and regime_long if long is None else long,
                      "short_sig": raw_short and regime_short if short is None else short,
                      "exit_long": ret < 0 or close < ema, "exit_short": ret > 0 or close > ema})


T = [pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(days=i) for i in range(10)]


# ------------------------------------------------------------------------------------- indicators
def test_indicators_use_only_past_candles():
    fr = frames10(700)
    fut = {c: df.copy() for c, df in fr.items()}
    cut = 500
    for df in fut.values():
        df.iloc[cut + 1:, :4] *= np.random.default_rng(9).uniform(0.3, 3.0, (len(df) - cut - 1, 1))
    a, b = build_states(fr), build_states(fut)
    for c in UNIVERSE:
        pd.testing.assert_frame_equal(a[c].iloc[:cut + 1], b[c].iloc[:cut + 1])


def test_ret40_and_ema200_definitions():
    df = series(300, seed=4)
    ind = indicators(df.close)
    assert math.isclose(ind.ret.iloc[250], df.close.iloc[250] / df.close.iloc[210] - 1)
    assert ind.ret.iloc[:40].isna().all() and ind.ema.iloc[:199].isna().all() and ind.ema.iloc[199:].notna().all()
    ref = df.close.ewm(span=200, adjust=False).mean()
    assert np.allclose(ind.ema.iloc[199:], ref.iloc[199:])


def test_signal_thresholds_are_strict():
    s = build_states({"BTC": series(400, seed=2)})["BTC"].dropna(subset=["ret", "ema"])
    assert (s.raw_long == ((s.ret > 0.05) & (s.close > s.ema))).all()
    assert (s.raw_short == ((s.ret < -0.05) & (s.close < s.ema))).all()
    assert (s.exit_long == ((s.ret < 0) | (s.close < s.ema))).all()
    assert (s.exit_short == ((s.ret > 0) | (s.close > s.ema))).all()


# ---------------------------------------------------------------------------------- regime filter
def test_btc_regime_filter_for_altcoins_only():
    up, down = series(500, drift=0.004, vol=0.01, seed=1), series(500, drift=-0.004, vol=0.01, seed=2)
    s = build_states({"BTC": down, "ETH": up})          # BTC bearish, ETH bullish
    eth, btc = s["ETH"].iloc[300:], s["BTC"].iloc[300:]
    assert eth.raw_long.any() and not eth.long_sig.any()          # longs blocked by the BTC regime
    assert (btc.short_sig == btc.raw_short).all() and btc.short_sig.any()   # BTC itself is not filtered
    s2 = build_states({"BTC": up, "ETH": up})
    assert (s2["ETH"].long_sig.iloc[300:] == s2["ETH"].raw_long.iloc[300:]).all()
    s3 = build_states({"BTC": up, "ETH": down})         # ETH shorts need BTC below its EMA
    assert s3["ETH"].raw_short.iloc[300:].any() and not s3["ETH"].short_sig.iloc[300:].any()


def test_regime_uses_latest_completed_btc_candle_not_future():
    btc, eth = series(400, drift=0.004, vol=0.01, seed=1), series(400, drift=0.004, vol=0.01, seed=3)
    gap = btc.index[360]
    btc2 = btc.drop(gap)                                  # BTC has no candle on `gap`; ETH does
    b = build_states({"BTC": btc2})["BTC"]
    prev_bull = bool(b.close.loc[btc.index[359]] > b.ema.loc[btc.index[359]])
    s = build_states({"BTC": btc2, "ETH": eth})
    assert bool(s["ETH"].regime_ok_long.loc[gap]) == prev_bull  # latest completed BTC candle, never a later one
    assert not s["ETH"].regime_ok_long.iloc[:199].any()   # no BTC EMA200 yet -> alts blocked


def test_regime_rejection_is_logged():
    e = MCMEngine(200)
    e.on_close(T[0], {"ETH": state(ret=0.2, regime_long=False)})
    assert e.pending == {} and e.events[-1]["reason"] == "BTC regime filter"


# ----------------------------------------------------------------------------- timing & execution
def test_signal_on_close_fills_at_next_open_only():
    e = MCMEngine(200)
    e.on_close(T[0], {"BTC": state(close=100, ret=0.2)})
    assert e.pf.positions == {}                                   # nothing fills at the signal close
    e.on_open(T[1], {"BTC": 105.0})
    pos = e.pf.positions["BTC"]
    assert pos.entry_ref == 105.0 and pos.entry_time == T[1] and math.isclose(pos.entry_fill, 105 * 1.0002)


def test_next_available_candle_when_coin_has_no_candle():
    e = MCMEngine(200)
    e.on_close(T[0], {"ETH": state(ret=0.2)})
    e.on_open(T[1], {"BTC": 50.0})                                # ETH has no candle at T1 -> stays pending
    assert "ETH" not in e.pf.positions and "ETH" in e.pending
    e.on_open(T[2], {"ETH": 101.0})
    assert e.pf.positions["ETH"].entry_ref == 101.0


def test_backtest_entries_are_next_candle_open_after_signal():
    from backtest.mcm_backtest import simulate
    fr = frames10(800, seed=5)
    eng, curve, trades = simulate(fr, P, 200.0)
    st = build_states(fr)
    assert len(trades) > 5
    for t in trades.to_dict("records"):
        s = st[t["coin"]]
        prev = s.index[s.index.get_loc(t["entry_time"]) - 1]
        assert bool(s.loc[prev, "long_sig" if t["side"] == LONG else "short_sig"])
        assert t["entry_ref"] == fr[t["coin"]].loc[t["entry_time"], "open"]
        if not t["exit_reason"].startswith("end_of_data"):
            prev_x = s.index[s.index.get_loc(t["exit_time"]) - 1]
            assert bool(s.loc[prev_x, "exit_long" if t["side"] == LONG else "exit_short"])
            assert t["exit_ref"] == fr[t["coin"]].loc[t["exit_time"], "open"]


# ---------------------------------------------------------------------------------------- exits
@pytest.mark.parametrize("side,st,why", [(LONG, state(close=100, ret=-0.01, ema=90), "ret40 < 0"),
                                         (LONG, state(close=85, ret=0.03, ema=90), "close < EMA200"),
                                         (SHORT, state(close=80, ret=0.01, ema=90), "ret40 > 0"),
                                         (SHORT, state(close=95, ret=-0.02, ema=90), "close > EMA200")])
def test_exits(side, st, why):
    e = MCMEngine(200)
    e.pf.open("BTC", side, 100.0, 20.0, T[0], 0.1)
    e.on_close(T[1], {"BTC": st})
    assert e.pending["BTC"].action == "exit"
    e.on_open(T[2], {"BTC": 99.0})
    assert "BTC" not in e.pf.positions and e.pf.trades[-1]["exit_reason"] == why


def test_no_exit_while_conditions_hold():
    e = MCMEngine(200)
    e.pf.open("BTC", LONG, 100.0, 20.0, T[0], 0.1)
    e.on_close(T[1], {"BTC": state(close=100, ret=0.02, ema=90)})
    e.on_open(T[2], {"BTC": 101.0})
    assert "BTC" in e.pf.positions


def test_reversal_exits_then_enters_other_side_at_same_open():
    e = MCMEngine(200)
    e.pf.open("BTC", LONG, 100.0, 20.0, T[0], 0.1)
    e.on_close(T[1], {"BTC": state(close=80, ret=-0.2, ema=90)})
    e.on_open(T[2], {"BTC": 79.0})
    assert e.pf.trades[-1]["side"] == LONG and e.pf.positions["BTC"].side == SHORT


# --------------------------------------------------------------------------------- caps & priority
def test_ten_percent_per_coin_cap():
    e = MCMEngine(200)
    e.on_close(T[0], {"BTC": state(ret=0.3)})
    e.on_open(T[1], {"BTC": 100.0})
    assert math.isclose(e.pf.positions["BTC"].notional, 20.0)


def test_all_ten_signals_fit_and_never_exceed_100pct():
    e = MCMEngine(200)
    e.on_close(T[0], {c: state(ret=0.1 + i / 100) for i, c in enumerate(UNIVERSE)})
    e.on_open(T[1], {c: 100.0 for c in UNIVERSE})
    snap = e.snapshot()
    assert len(snap["positions"]) == 10 and snap["gross_exposure"] <= snap["equity"] + 1e-9 and e.pf.cash >= -1e-9


def test_portfolio_exposure_cap_rejects_when_full():
    e = MCMEngine(200)
    for c in UNIVERSE[:9]:
        e.pf.open(c, SHORT, 100.0, 20.0, T[0], -0.1)
    e.mark({c: 120.0 for c in UNIVERSE[:9]})                    # losing shorts: exposure up, equity down
    e.on_close(T[1], {c: state(close=120, ret=-0.2, ema=150) for c in UNIVERSE[:9]}
               | {"DOT": state(ret=0.3)})
    e.on_open(T[2], {"DOT": 10.0})
    assert "DOT" not in e.pf.positions
    assert e.events[-1]["kind"] == "signal_rejected" and "exposure cap" in e.events[-1]["reason"]


def test_partial_capacity_goes_to_next_candidate_and_is_flagged():
    e = MCMEngine(200, MCMParams(max_total=0.15))
    e.on_close(T[0], {"BTC": state(ret=0.5), "ETH": state(ret=0.3)})
    e.on_open(T[1], {"BTC": 100.0, "ETH": 100.0})
    assert math.isclose(e.pf.positions["BTC"].notional, 20.0)
    # capacity at ETH's turn = 15% of equity minus BTC's exposure marked at market (100): ~10.00, below 10%
    assert 9.99 < e.pf.positions["ETH"].notional < 10.01 and e.pf.positions["ETH"].notional < 0.10 * e.equity()
    assert [x for x in e.events if x["kind"] == "fill_entry"][-1]["capped"]


def test_simultaneous_signals_prioritised_by_abs_momentum_then_universe_order():
    e = MCMEngine(200, MCMParams(max_total=0.2))                # room for exactly two 10% positions
    e.on_close(T[0], {"BTC": state(ret=0.2), "SOL": state(ret=0.5), "ETH": state(ret=0.5),
                      "DOT": state(close=80, ret=-0.7, ema=90)})
    e.on_open(T[1], {"BTC": 1.0, "SOL": 1.0, "ETH": 1.0, "DOT": 1.0})
    assert list(e.pf.positions) == ["DOT", "ETH"]                  # |-0.7| first, then ETH before SOL (tie)
    rej = [x["coin"] for x in e.events if x["kind"] == "signal_rejected"]
    assert rej == ["SOL", "BTC"]


def test_prioritisation_is_deterministic():
    from backtest.mcm_backtest import simulate
    fr = frames10(700, seed=8)
    a, b = simulate(fr, P, 200.0)[2], simulate(fr, P, 200.0)[2]
    pd.testing.assert_frame_equal(a, b)


# ------------------------------------------------------------------------------- costs & accounting
def test_long_fees_slippage_and_cash():
    pf = Portfolio(200.0)
    pf.open("BTC", LONG, 100.0, 20.0, T[0], 0.1)
    qty = 20 / 100.02
    assert math.isclose(pf.cash, 200 - 20 - 0.01)
    t = pf.close("BTC", 110.0, T[1], "x")
    xf = 110 * 0.9998
    fee = qty * xf * 0.0005
    assert math.isclose(t["pnl"], qty * (xf - 100.02) - 0.01 - fee)
    assert math.isclose(pf.cash, 200 + t["pnl"])
    assert math.isclose(pf.fees_paid, 0.01 + fee) and math.isclose(t["slippage"], qty * 0.02 + qty * 110 * 0.0002)


def test_short_collateral_and_pnl():
    pf = Portfolio(200.0)
    pf.open("ETH", SHORT, 100.0, 20.0, T[0], -0.1)
    qty = 20 / 99.98
    assert math.isclose(pf.cash, 200 - 20 - 0.01)
    assert math.isclose(pf.equity({"ETH": 90.0}), pf.cash + 20 + qty * (99.98 - 90))
    t = pf.close("ETH", 90.0, T[1], "x")
    xf = 90 * 1.0002
    assert math.isclose(t["pnl"], qty * (99.98 - xf) - 0.01 - qty * xf * 0.0005)
    assert math.isclose(pf.cash, 200 + t["pnl"])


def test_fees_are_configurable():
    pf = Portfolio(200.0, MCMParams(fee_rate=0.001, slippage_rate=0.0))
    pf.open("BTC", LONG, 100.0, 50.0, T[0], 0.1)
    assert math.isclose(pf.fees_paid, 0.05) and math.isclose(pf.positions["BTC"].entry_fill, 100.0)


def test_portfolio_pnl_reconciles_and_no_leverage_ever():
    from backtest.mcm_backtest import simulate
    fr = frames10(900, seed=3)
    st = build_states(fr)
    recs = {c: s.to_dict("index") for c, s in st.items()}
    e = MCMEngine(200.0, P, enabled=set(fr))
    for d in sorted(set().union(*[set(df.index) for df in fr.values()])):
        e.on_open(d, {c: fr[c].loc[d, "open"] for c in fr if d in fr[c].index})
        snap = e.snapshot()
        assert e.pf.cash >= -1e-9
        assert snap["gross_exposure"] <= snap["equity"] * P.max_total * 1.02 + 1e-9  # only price drift after entry
        e.on_close(d, {c: recs[c][d] for c in fr if d in recs[c]})
        eq = e.pf.cash + sum(p.value(e.last_price[c]) for c, p in e.pf.positions.items())
        assert math.isclose(eq, e.equity())
    eng, curve, trades = simulate(fr, P, 200.0)
    assert len(trades) > 10 and math.isclose(curve.equity.iloc[-1], 200 + trades.pnl.sum(), rel_tol=1e-9)
    assert math.isclose(trades.fees.sum(), eng.pf.fees_paid)


# ---------------------------------------------------------------------------------------- loader
def _zip(tmp_path, files: dict) -> Path:
    p = tmp_path / "crypto_data.zip"
    with zipfile.ZipFile(p, "w") as z:
        for name, df in files.items():
            z.writestr(name, df.to_csv(index=False))
    return p


def _csv(df, ms=False, col="timestamp"):
    out = df.reset_index().rename(columns={"index": col})
    out[col] = (out[col].astype("int64") // (10 ** 6 if ms else 10 ** 9)) if ms else out[col].dt.strftime("%Y-%m-%d")
    return out.rename(columns=str.title if ms else (lambda c: c))


def test_loader_per_file_names_and_formats(tmp_path):
    from backtest.mcm_backtest import load_crypto_zip
    fr = frames10(300)
    files = {"data/BTC-USD.csv": _csv(fr["BTC"]), "data/ethusdt_1d.csv": _csv(fr["ETH"], ms=True),
             "SOL.csv": _csv(fr["SOL"], col="date"), "README.csv": pd.DataFrame({"a": [1]})}
    got, notes = load_crypto_zip(_zip(tmp_path, files))
    assert list(got) == ["BTC", "ETH", "SOL"]
    assert np.allclose(got["ETH"].close, fr["ETH"].close) and got["ETH"].index[0] == fr["ETH"].index[0]
    assert any("MISSING coins" in n for n in notes) and any("README" in n for n in notes)


def test_loader_combined_file_with_symbol_column(tmp_path):
    from backtest.mcm_backtest import load_crypto_zip
    fr = frames10(250)
    rows = pd.concat([_csv(df).assign(symbol=f"{c}USDT") for c, df in fr.items()])
    got, notes = load_crypto_zip(_zip(tmp_path, {"all.csv": rows}))
    assert list(got) == list(UNIVERSE) and not any("MISSING" in n for n in notes)


def test_loader_refuses_ambiguous_nondaily_or_no_btc(tmp_path):
    from backtest.mcm_backtest import DataError, load_crypto_zip
    fr = frames10(100)
    with pytest.raises(DataError, match="more than one"):
        load_crypto_zip(_zip(tmp_path, {"BTC.csv": _csv(fr["BTC"]), "BTC-USD.csv": _csv(fr["BTC"])}))
    hourly = fr["BTC"].copy()
    hourly.index = pd.date_range("2024-01-01", periods=len(hourly), freq="1h", tz="UTC")
    with pytest.raises(DataError, match="DAILY"):
        load_crypto_zip(_zip(tmp_path, {"BTC.csv": _csv(hourly).assign(timestamp=hourly.index.astype(str))}))
    with pytest.raises(DataError, match="BTC is required"):
        load_crypto_zip(_zip(tmp_path, {"ETH.csv": _csv(fr["ETH"])}))


# -------------------------------------------------------------------------------------- pipeline
def test_backtest_end_to_end(tmp_path):
    from backtest import mcm_backtest as mb
    fr = frames10(1200, seed=11)
    z = _zip(tmp_path, {f"{c}-USD.csv": _csv(df) for c, df in fr.items()})
    assert mb.main(["--data", str(z), "--out", str(tmp_path / "o")]) == 0
    rep = (tmp_path / "o" / "REPORT.md").read_text()
    for s in ("PROXY for perpetual", "Ending balance from $200", "OOS return", "OOS PF", "OOS max drawdown",
              "BTC buy-and-hold", "Equal-weight buy-and-hold (10 coins)", "Results by coin", "Long vs short",
              "Results by year", "Longest losing streak", "Fees paid", "Exposure", "equity_curve.svg"):
        assert s in rep, s
    summ = json.loads((tmp_path / "o" / "summary.json").read_text())
    assert summ["params"]["lookback"] == 40 and summ["params"]["max_per_coin"] == 0.10
    svg = (tmp_path / "o" / "equity_curve.svg").read_text()
    assert svg.startswith("<svg") and "prefers-color-scheme: dark" in svg
    import xml.dom.minidom
    xml.dom.minidom.parseString(svg)                  # must be well-formed XML (labels contain '&')
    assert len(pd.read_csv(tmp_path / "o" / "equity_curve.csv")) > 1000


def test_backtest_missing_data(tmp_path, capsys):
    from backtest import mcm_backtest as mb
    assert mb.main(["--data", str(tmp_path / "nope.zip")]) == 3 and "MISSING DATA" in capsys.readouterr().err


# ---------------------------------------------------------------------------------- paper session
class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class RoutedSession:
    """Fake requests.Session: serves Coinbase-shaped JSON for allowlisted GETs; records everything."""

    def __init__(self, frames, missing=("BNB",), clock=None):
        self.frames, self.missing, self.clock, self.calls = frames, set(missing), clock, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(url)
        path = url.split("api.coinbase.com", 1)[1]
        pid = path.split("/products/")[1].split("/")[0]
        coin = pid.split("-")[0]
        status, body = 200, {}
        if coin in self.missing or coin not in self.frames:
            status = 404
        elif path.endswith("/candles"):
            s, e = int(params["start"]), int(params["end"])
            now = self.clock()
            df = self.frames[coin]
            rows = []
            for t, r in df.iterrows():
                ts = int(t.timestamp())
                if s <= ts <= e and t <= pd.Timestamp(now):
                    close = r.close if t + pd.Timedelta(days=1) <= pd.Timestamp(now) else r.open  # in-progress
                    rows.append({"start": str(ts), "open": str(r.open), "high": str(r.high), "low": str(r.low),
                                 "close": str(close), "volume": "1"})
            body = {"candles": rows[::-1]}
        else:
            body = {"product_id": pid, "status": "online", "trading_disabled": False}

        class R:
            status_code = status
            text = json.dumps(body)

            def json(_):
                return body
        return R()

    def post(self, *a, **k):
        raise AssertionError("POST reached the session")

    put = delete = patch = request = post


def _paper(tmp_path, n=1200):
    from exchange.client import CoinbaseAdvancedClient
    from exchange.transport import ReadOnlyTransport
    from paper_trading.mcm_runner import MCMPaperSession
    fr = frames10(n, seed=13)
    for df in fr.values():
        df.index = pd.date_range("2023-06-01", periods=n, freq="1D", tz="UTC")
    last = fr["BTC"].index[-4]
    clock = Clock(datetime(last.year, last.month, last.day, 15, 0, tzinfo=timezone.utc))
    sess_http = RoutedSession(fr, clock=clock)
    client = CoinbaseAdvancedClient(transport=ReadOnlyTransport(session=sess_http))
    s = MCMPaperSession(client, P, 200.0, now=clock, sleep=lambda _s: None, out_dir=tmp_path / "rec")
    return s, clock, sess_http, fr


def test_paper_startup_report_and_unavailable_symbols_not_substituted(tmp_path):
    s, clock, http, _fr = _paper(tmp_path)
    lines = "\n".join(s.startup())
    for needle in ("PAPER MODE: ENABLED", "order_endpoint_called: NO", "paper orders: 0 | live orders: 0",
                   "starting equity: $200.00", "Unavailable  : BNB", "NOT substituted", "PRICE PROXY"):
        assert needle in lines, needle
    assert "BNB" not in s.available and "product not found on Coinbase (HTTP 404)" in s.unavailable["BNB"]
    assert s.connection_errors == []
    products = {u.split("/products/")[1].split("/")[0] for u in http.calls}
    assert products == {f"{c}-USD" for c in UNIVERSE}               # only <COIN>-USD, nothing substituted
    assert all("/orders" not in u for u in http.calls)


def test_paper_decides_on_completed_candle_and_fills_at_new_open(tmp_path):
    s, clock, http, fr = _paper(tmp_path)
    s.startup()
    assert s.engine.pf.paper_orders == 0                              # never trades at startup
    day0 = pd.Timestamp(clock.t).floor("1D")
    clock.t = clock.t + timedelta(hours=2)
    assert s.step() is None                                           # same UTC day: no decision
    clock.t = (day0 + pd.Timedelta(days=1, minutes=10)).to_pydatetime()
    msg = s.step()
    assert msg and "evaluated 9 completed candles" in msg
    new_day = day0 + pd.Timedelta(days=1)
    for x in s.engine.events:
        if x["kind"] in ("signal", "exit_signal"):
            assert x["time"] == day0                                  # signals from the COMPLETED candle
        if x["kind"].startswith("fill"):
            assert x["time"] == new_day
    for t in s.engine.pf.trades:
        assert t["exit_ref"] == fr[t["coin"]].loc[new_day, "open"]
    for c, p in s.engine.pf.positions.items():
        if p.entry_time == new_day:
            assert p.entry_ref == fr[c].loc[new_day, "open"]
    assert s.step() is None                                           # one decision per day


def test_paper_in_progress_candle_never_feeds_signals(tmp_path):
    from paper_trading.mcm_runner import split_completed
    df = series(10, start="2024-01-01")
    now = datetime(2024, 1, 10, 12, tzinfo=timezone.utc)
    comp, cur = split_completed(df, now)
    assert comp.index[-1] == pd.Timestamp("2024-01-09", tz="UTC") and cur.name == pd.Timestamp("2024-01-10", tz="UTC")


def test_paper_final_report_confirms_no_order_endpoint(tmp_path):
    from paper_trading.mcm_runner import format_final, run
    s, clock, http, _fr = _paper(tmp_path)
    s.startup()
    for _ in range(3):
        clock.t += timedelta(days=1)
        s.step()
    final = run(s, duration_s=10, poll_s=0, max_polls=1)
    txt = format_final(final)
    assert final["order_endpoint_called"] is False and final["live_orders"] == 0
    assert "CONFIRMATION: NO live order endpoint was called." in txt
    for k in ("starting_equity", "ending_equity", "pnl", "return_pct", "max_drawdown", "trades_by_coin",
              "winning_trades", "losing_trades", "fees_paid", "current_positions", "signals_generated",
              "signals_rejected", "market_data_messages", "connection_errors"):
        assert k in final
    assert final["market_data_messages"] > 0 and (tmp_path / "rec" / "final_report.json").is_file()


def test_paper_connection_errors_are_recorded_not_fatal(tmp_path):
    s, clock, http, _fr = _paper(tmp_path)
    s.startup()
    http.missing.add("ETH")                                           # ETH starts failing mid-session
    clock.t += timedelta(days=1)
    s.step()
    assert any("ETH-USD" in e for e in s.connection_errors)


def test_paper_refuses_without_paper_mode(monkeypatch, capsys):
    from paper_trading import mcm_runner
    monkeypatch.setenv("PAPER_MODE", "false")
    assert mcm_runner.main(["--duration", "1"]) == 2


# ------------------------------------------------------------------------------------- no live orders
@pytest.mark.parametrize("path", ["strategy/multi_crypto_momentum.py", "backtest/mcm_backtest.py",
                                  "paper_trading/mcm_runner.py"])
def test_new_modules_never_reference_order_endpoints_or_methods(path):
    src = (REPO / path).read_text()
    tree = ast.parse(src)
    banned = {"place_order", "create_order", "market_order", "limit_order", "preview_order", "edit_order",
              "cancel_order", "cancel_orders", "close_position", "move_portfolio_funds", "withdraw", "deposit",
              "convert", "post", "put", "delete", "patch"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in banned, (path, node.attr)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "/orders" not in node.value, path
    assert "import requests" not in src and "websockets" not in src


def test_paper_network_failure_is_not_reported_as_unlisted_product(tmp_path):
    from exchange.errors import ExchangeAPIError
    s, clock, http, _fr = _paper(tmp_path)

    def boom(url, params=None, headers=None, timeout=None):
        import requests
        raise requests.ConnectionError("proxy refused")
    http.get = boom
    s.startup()
    assert s.available == {} and all("Coinbase unreachable" in v for v in s.unavailable.values())
    assert len(s.connection_errors) == len(UNIVERSE)


def _klines(df):
    ot = (df.index.astype("int64") // 10 ** 6).astype("int64") if df.index.dtype.unit == "ns" else \
        (df.index.as_unit("ms").asi8)
    return [[int(t), f"{r.open:.8f}", f"{r.high:.8f}", f"{r.low:.8f}", f"{r.close:.8f}", "1.0", int(t) + 86_399_999,
             "0", 1, "0", "0", "0"] for t, r in zip(ot, df.itertuples())]


def test_loader_reads_binance_kline_json(tmp_path):
    from backtest.mcm_backtest import DataError, load_crypto_zip
    fr = frames10(120)
    p = tmp_path / "k.zip"
    with zipfile.ZipFile(p, "w") as z:
        for c in ("BTC", "ETH"):
            z.writestr(f"crypto_data/{c}USDT_1d.json", json.dumps(_klines(fr[c])))
    got, _ = load_crypto_zip(p)
    assert list(got) == ["BTC", "ETH"] and got["BTC"].index[0] == fr["BTC"].index[0]
    assert np.allclose(got["ETH"][["open", "high", "low", "close"]].to_numpy(),
                       fr["ETH"][["open", "high", "low", "close"]].to_numpy())
    hourly = _klines(fr["BTC"])
    for row in hourly:
        row[6] = row[0] + 3_599_999
    with zipfile.ZipFile(tmp_path / "h.zip", "w") as z:
        z.writestr("BTCUSDT_1h.json", json.dumps(hourly))
    with pytest.raises(DataError, match="1-day"):
        load_crypto_zip(tmp_path / "h.zip")


# ------------------------------------------------------------ market-data reliability (Oct 1 regression)
class FutureEndRejecting(RoutedSession):
    """Coinbase-like fake that rejects a candles request whose `end` is in the future (HTTP 400)
    and records every candles request's parameters."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.candle_params = []

    def get(self, url, params=None, headers=None, timeout=None):
        if url.endswith("/candles"):
            self.candle_params.append(dict(params))
            if int(params["end"]) > int(self.clock().timestamp()):
                self.calls.append(url)

                class R:
                    status_code = 400
                    text = "{}"
                return R()
        return super().get(url, params, headers, timeout)


def _oct1_session(tmp_path, Http=FutureEndRejecting, start=datetime(2026, 9, 30, 23, 5, tzinfo=timezone.utc)):
    from exchange.client import CoinbaseAdvancedClient
    from exchange.transport import ReadOnlyTransport
    from paper_trading.mcm_runner import MCMPaperSession
    n = 1300
    fr = frames10(n, seed=13)
    for df in fr.values():
        df.index = pd.date_range(end="2026-10-02", periods=n, freq="1D", tz="UTC")
    clock = Clock(start)
    http = Http(fr, missing=(), clock=clock)
    s = MCMPaperSession(CoinbaseAdvancedClient(transport=ReadOnlyTransport(session=http)), P, 200.0, now=clock,
                        sleep=lambda _s: None, out_dir=tmp_path / "rec")
    return s, clock, http, fr


def test_refresh_never_requests_a_future_end_time(tmp_path):
    s, clock, http, _fr = _oct1_session(tmp_path)
    s.startup()
    for _ in range(3):
        clock.t += timedelta(minutes=5)
        s.step()
    assert http.candle_params and all(int(p["end"]) <= int(clock.t.timestamp()) for p in http.candle_params)


def test_oct1_regression_future_end_rejecting_coinbase_still_executes_next_open(tmp_path, capsys):
    """Replays the 2026-10-01 failure: startup 23:05 UTC, polls every 5 min. Before the fix every refresh used
    end=now+5min, was rejected, was swallowed, and the 00:00 decision never ran."""
    s, clock, http, fr = _oct1_session(tmp_path)
    s.startup()
    decided = None
    while clock.t < datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc):
        clock.t += timedelta(minutes=5)
        decided = s.step() or decided
    assert decided and decided.startswith("2026-10-01: evaluated 10 completed candles")
    assert s.connection_errors == [] and s.engine.pf.paper_orders > 0
    oct1 = pd.Timestamp("2026-10-01", tz="UTC")
    for c, p in s.engine.pf.positions.items():
        assert p.entry_time == oct1 and p.entry_ref == fr[c].loc[oct1, "open"]   # filled at the Oct 1 open
    assert "MARKET-DATA ERROR" not in capsys.readouterr().out


def test_refresh_errors_are_printed_and_written_to_state_json(tmp_path, capsys):
    s, clock, http, _fr = _oct1_session(tmp_path)
    s.startup()
    http.missing.add("ETH")
    clock.t += timedelta(minutes=5)
    s.step()
    out = capsys.readouterr().out
    assert "MARKET-DATA ERROR 2026-09-30 23:10:00 UTC ETH (ETH-USD):" in out and "HTTP 404" in out
    st = json.loads((tmp_path / "rec" / "state.json").read_text())
    assert st["connection_errors_total"] == 1 and "ETH-USD" in st["connection_errors"][0] and "HTTP 404" in st["connection_errors"][0]
    assert st["last_successful_refresh"] == "None"      # not every coin refreshed in that poll
    assert "status" in st


def test_waiting_status_and_heartbeat_are_visible(tmp_path, capsys):
    class NoNewCandle(FutureEndRejecting):          # Coinbase has not published the Oct 1 candle yet
        def get(self, url, params=None, headers=None, timeout=None):
            r = super().get(url, params, headers, timeout)
            if url.endswith("/candles") and r.status_code == 200:
                body = r.json()
                body["candles"] = [c for c in body["candles"]
                                   if pd.Timestamp(int(c["start"]), unit="s", tz="UTC") < pd.Timestamp("2026-10-01", tz="UTC")]
            return r
    s, clock, http, _fr = _oct1_session(tmp_path, Http=NoNewCandle)
    s.startup()
    capsys.readouterr()
    for _ in range(50):                              # 23:06 .. 23:55 then 00:00 .. 00:56, one poll per 2 min
        clock.t += timedelta(minutes=2)
        s.step()
    out = capsys.readouterr().out
    beats = [l for l in out.splitlines() if l.startswith("HEARTBEAT")]
    assert 15 <= len(beats) <= 22                     # every 5 min, not every poll (100 min / 5)
    assert all("last successful market-data refresh: 20" in b and "candles held:" in b and "equity $200.00" in b
               and "open positions: none" in b for b in beats)
    waits = [l for l in out.splitlines() if "WAITING for the 2026-10-01 daily candle" in l]
    assert waits and "2026-10-01 candle for 0/10 coins" in waits[0]
    assert any("WARNING: still not ready 30 min after 00:00 UTC" in l for l in waits)
    assert s.engine.pf.paper_orders == 0             # never trades without the real next-candle open
    assert "WAITING" in json.loads((tmp_path / "rec" / "state.json").read_text())["status"]


def test_restart_does_not_backfill_the_missed_oct1_trade(tmp_path):
    s, clock, http, _fr = _oct1_session(tmp_path, start=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc))
    s.startup()
    for _ in range(12):                              # rest of Oct 1: no decision, no orders
        clock.t += timedelta(hours=1)
        assert s.step() is None or clock.t >= datetime(2026, 10, 2, tzinfo=timezone.utc)
    assert all(e["time"] >= pd.Timestamp("2026-10-01", tz="UTC") for e in s.engine.events)
    assert not any(e["kind"].startswith("fill") and e["time"] == pd.Timestamp("2026-10-01", tz="UTC")
                   for e in s.engine.events)
    while clock.t < datetime(2026, 10, 2, 0, 10, tzinfo=timezone.utc):
        clock.t += timedelta(minutes=5)
        s.step()
    fills = [e for e in s.engine.events if e["kind"].startswith("fill")]
    assert fills and all(e["time"] == pd.Timestamp("2026-10-02", tz="UTC") for e in fills)   # first fills: Oct 2 open
