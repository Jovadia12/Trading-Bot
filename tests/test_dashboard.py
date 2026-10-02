"""Dashboard: read-only data layer (both state.json formats), no fabricated data, GET-only local app, safety."""
import ast
import contextlib
import io
import json
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from dashboard.data import StateReader, build_dashboard, find_session_dir

REPO = Path(__file__).resolve().parent.parent
SCHEMA2_ONLY = ("schema", "paper_mode", "started_at", "start_equity", "params", "poll_seconds", "available_symbols",
                "unavailable_symbols", "paper_orders", "live_orders", "order_endpoint_called", "fees_paid",
                "slippage_paid", "last_decision_day", "last_prices", "positions_detail", "signal_states",
                "startup_signals_not_traded")


@pytest.fixture(scope="module")
def session_records(tmp_path_factory):
    """Run the real paper runner (fake Coinbase, no network) from 2026-09-30 23:05 to 2026-11-14 to get genuine
    state.json content with entries, exits and open positions."""
    import tests.test_multi_crypto_momentum as T
    from exchange.client import CoinbaseAdvancedClient
    from exchange.transport import ReadOnlyTransport
    from paper_trading.mcm_runner import MCMPaperSession
    from strategy.multi_crypto_momentum import MCMParams
    root = tmp_path_factory.mktemp("records")
    n = 1400
    fr = T.frames10(n, seed=29)
    for df in fr.values():
        df.index = pd.date_range(end="2026-11-20", periods=n, freq="1D", tz="UTC")
    clock = T.Clock(datetime(2026, 9, 30, 23, 5, tzinfo=timezone.utc))
    http = T.RoutedSession(fr, missing=(), clock=clock)
    s = MCMPaperSession(CoinbaseAdvancedClient(transport=ReadOnlyTransport(session=http)), MCMParams(), 200.0,
                        now=clock, sleep=lambda _x: None, out_dir=root / "mcm_20260930T230500Z")
    s.poll_s = 300
    s.startup()
    with contextlib.redirect_stdout(io.StringIO()):
        while clock.t < datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc):
            clock.t += timedelta(hours=1)
            s.step()
    return root, s, pd.Timestamp(clock.t)


def _read(root):
    return StateReader(root).read()


def _schema1(root, tmp_path):
    """The format written by the runner version currently in use (commit 1c04321): no schema-2 fields."""
    st = json.loads((root / "mcm_20260930T230500Z" / "state.json").read_text())
    for k in SCHEMA2_ONLY:
        st.pop(k, None)
    d = tmp_path / "old" / "mcm_20260930T230500Z"
    d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps(st))
    return tmp_path / "old"


# ---------------------------------------------------------------------------------------------- reading
def test_reader_picks_newest_session_and_reports_missing(tmp_path):
    assert StateReader(tmp_path).read()["ok"] is False
    for name in ("mcm_20260101T000000Z", "mcm_20260201T000000Z"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "state.json").write_text(json.dumps({"now": name}))
    (tmp_path / "mcm_20260301T000000Z").mkdir()                    # no state.json -> ignored
    assert find_session_dir(tmp_path).name == "mcm_20260201T000000Z"
    assert StateReader(tmp_path, "mcm_20260101T000000Z").read()["state"]["now"] == "mcm_20260101T000000Z"


def test_reader_keeps_last_good_copy_on_partial_write(tmp_path):
    d = tmp_path / "mcm_20260101T000000Z"
    d.mkdir()
    (d / "state.json").write_text(json.dumps({"now": "2026-01-01 00:00:00+00:00", "snapshot": {}}))
    r = StateReader(tmp_path)
    assert r.read()["stale_read"] is False
    (d / "state.json").write_text('{"now": "2026-01-01 00:05')                 # torn write
    out = r.read()
    assert out["ok"] and out["stale_read"] and out["state"]["now"].startswith("2026-01-01 00:00") and out["error"]


# --------------------------------------------------------------------------------------- accounting
def test_overview_matches_engine_and_reconciles(session_records):
    root, s, now = session_records
    d = build_dashboard(_read(root), server_now=now)
    o = d["overview"]
    eng = s.engine
    assert d["schema"] == 2 and o["start_equity"] == 200.0 and o["start_equity_source"] == "recorded by the runner"
    assert o["equity"] == pytest.approx(eng.equity()) and o["cash"] == pytest.approx(eng.pf.cash)
    assert o["open_positions"] == len(eng.pf.positions) and o["closed_trades"] == len(eng.pf.trades)
    assert o["realized_pnl"] == pytest.approx(sum(t["pnl"] for t in eng.pf.trades))
    assert o["total_pnl"] == pytest.approx(o["realized_pnl"] + o["unrealized_pnl"] - o["open_position_costs"])
    entry_fees_open = sum(p.entry_fee for p in eng.pf.positions.values())
    assert o["open_position_costs"] == pytest.approx(entry_fees_open)
    assert o["bot_status"]["state"] == "RUNNING" and o["error_count"] == 0


def test_positions_are_only_engine_fills(session_records):
    root, s, now = session_records
    d = build_dashboard(_read(root), server_now=now)
    eng = s.engine
    assert {p["symbol"] for p in d["positions"]} == set(eng.pf.positions)
    for p in d["positions"]:
        pos = eng.pf.positions[p["symbol"]]
        assert p["entry_fill"] == pytest.approx(pos.entry_fill) and p["qty"] == pytest.approx(pos.qty)
        assert p["unrealized_pnl"] == pytest.approx(p["market_value"] - pos.qty * pos.entry_fill)
        assert p["allocation_pct"] == pytest.approx(abs(pos.qty * p["current_price"]) / d["overview"]["equity"])
        assert p["entry_reason"].startswith(f"{pos.side.upper()} signal on the ") and p["ret40"] is not None
    # coins with an entry signal but no fill are NOT positions
    sig_only = [c for c, st in json.loads((root / "mcm_20260930T230500Z" / "state.json").read_text())["signal_states"].items()
                if (st["long_sig"] or st["short_sig"]) and c not in eng.pf.positions]
    assert not set(sig_only) & {p["symbol"] for p in d["positions"]}


def test_trade_history_distinguishes_open_and_closed(session_records):
    root, s, now = session_records
    d = build_dashboard(_read(root), server_now=now)
    closed = [t for t in d["trades"] if t["status"] == "CLOSED"]
    opened = [t for t in d["trades"] if t["status"] == "OPEN"]
    assert len(closed) == len(s.engine.pf.trades) >= 1 and len(opened) == len(s.engine.pf.positions)
    for t in closed:
        assert t["gross_pnl"] == pytest.approx(t["net_pnl"] + t["fees"]) and t["exit_time"] and t["exit_reason"]
    for t in opened:
        assert t["exit_time"] is None and t["net_pnl"] is None and t["unrealized_pnl"] is not None


def test_status_counters_and_pipeline(session_records):
    root, s, now = session_records
    st = build_dashboard(_read(root), server_now=now)["status"]
    fills = [e for e in s.engine.events if e["kind"].startswith("fill")]
    assert st["paper_orders"] == s.engine.pf.paper_orders == len(fills) and st["paper_orders_source"] == "runner counter"
    assert st["live_orders"] == 0 and st["order_endpoint_called"] is False
    assert st["pipeline"]["entry_fills"] + st["pipeline"]["exit_fills"] == st["pipeline"]["paper_orders_filled"]
    assert st["pipeline"]["open_positions"] + st["pipeline"]["closed_trades"] == st["pipeline"]["entry_fills"]


def test_performance_from_recorded_marks_and_trades(session_records):
    root, s, now = session_records
    p = build_dashboard(_read(root), server_now=now)["performance"]
    assert p["equity_curve"] and p["equity_curve"][-1][1] == pytest.approx(s.engine.equity())
    assert all(v <= 1e-12 for _t, v in p["drawdown"])
    assert sum(r["pnl"] for r in p["daily"]) == pytest.approx(p["daily"][-1]["equity"] - 200.0)
    assert p["stats"]["trades"] == len(s.engine.pf.trades)
    assert {m["month"] for m in p["monthly"]} == {"2026-09", "2026-10", "2026-11"}


# ------------------------------------------------------------------------------------ old format / N/A
def test_schema1_shows_na_instead_of_inventing(session_records, tmp_path):
    root, s, now = session_records
    d = build_dashboard(_read(_schema1(root, tmp_path)), server_now=now)
    assert d["schema"] == 1
    assert d["overview"]["start_equity"] == 200.0 and "first equity mark" in d["overview"]["start_equity_source"]
    for p in d["positions"]:
        assert p["ema200"] is None and p["ret40"] is None and p["entry_price"] is None
        assert p["price_source"] == "derived from the position's marked value"
        assert p["current_price"] == pytest.approx(s.engine.last_price[p["symbol"]])
    st = d["status"]
    assert st["order_endpoint_called"] is None and "not recorded" in st["order_endpoint_source"]
    assert st["paper_orders"] == s.engine.pf.paper_orders and st["paper_orders_source"] == "counted from recorded fill events"
    assert d["strategy"]["signals_source"].startswith("LAST DECISION EVENTS ONLY")
    assert all(r["ema200"] is None and r["long_eligible"] is None for r in d["strategy"]["signals"])


def test_period_pnl_and_bot_status(tmp_path):
    d = tmp_path / "mcm_20261001T000000Z"
    d.mkdir()
    marks = [["2026-09-30T23:00:00+00:00", 200.0], ["2026-10-01T23:55:00+00:00", 210.0],
             ["2026-10-02T06:00:00+00:00", 205.0]]
    st = {"now": "2026-10-02 06:00:00+00:00", "status": "next decision", "equity_marks": marks,
          "snapshot": {"equity": 205.0, "cash": 205.0, "gross_exposure": 0.0, "positions": {}}}
    (d / "state.json").write_text(json.dumps(st))
    out = build_dashboard(StateReader(tmp_path).read(), server_now=pd.Timestamp("2026-10-02 06:03", tz="UTC"))
    o = out["overview"]
    assert o["today_pnl"] == pytest.approx(-5.0) and o["today_pnl_pct"] == pytest.approx(-5 / 210)
    assert o["month_pnl"] == pytest.approx(5.0) and o["total_pnl"] == pytest.approx(5.0)
    assert o["current_drawdown"] == pytest.approx(205 / 210 - 1) and o["bot_status"]["state"] == "RUNNING"
    stale = build_dashboard(StateReader(tmp_path).read(), server_now=pd.Timestamp("2026-10-02 07:00", tz="UTC"))
    assert stale["overview"]["bot_status"]["state"] == "STALE"
    (d / "final_report.json").write_text(json.dumps({"end_reason": "duration reached", "order_endpoint_called": False}))
    done = build_dashboard(StateReader(tmp_path).read(), server_now=pd.Timestamp("2026-10-02 07:00", tz="UTC"))
    assert done["overview"]["bot_status"]["state"] == "STOPPED" and done["status"]["order_endpoint_called"] is False


def test_no_session_is_reported_not_faked(tmp_path):
    out = build_dashboard(StateReader(tmp_path).read())
    assert out["available"] is False and "no paper session" in out["source"]["error"]


# ---------------------------------------------------------------------------------------------- web app
@pytest.fixture
def client(session_records):
    from dashboard.app import create_app
    return create_app(session_records[0]).test_client()


def test_routes_serve_page_and_json(client):
    r = client.get("/")
    assert r.status_code == 200 and b"PAPER MODE: ON" in r.data and b"LIVE TRADING: OFF" in r.data
    j = client.get("/api/dashboard").get_json()
    assert j["available"] and j["safety"] == {"paper_mode": "ON", "live_trading": "OFF",
                                               "dashboard": j["safety"]["dashboard"]} and j["refresh_ms"] <= 5000
    assert client.get("/api/health").get_json()["live_trading"] == "OFF"
    assert client.get("/static/app.js").status_code == 200
    assert r.headers["Cache-Control"] == "no-store" and "default-src 'self'" in r.headers["Content-Security-Policy"]


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize("path", ["/", "/api/dashboard", "/api/health"])
def test_dashboard_is_read_only(client, method, path):
    assert getattr(client, method)(path).status_code == 405


def test_dashboard_makes_no_network_calls(client, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("dashboard attempted a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert client.get("/api/dashboard").status_code == 200


def test_main_requires_paper_mode_loopback_and_never_loads_dotenv(monkeypatch, capsys):
    from dashboard import app as appmod
    monkeypatch.setenv("PAPER_MODE", "false")
    assert appmod.main([]) == 2
    monkeypatch.setenv("PAPER_MODE", "true")
    assert appmod.main(["--host", "0.0.0.0"]) == 2 and "local-only" in capsys.readouterr().err
    seen = {}
    monkeypatch.setattr("flask.Flask.run", lambda self, **kw: seen.update(kw))
    assert appmod.main(["--port", "8099"]) == 0
    assert seen["host"] == "127.0.0.1" and seen["port"] == 8099 and seen["load_dotenv"] is False and seen["debug"] is False


@pytest.mark.parametrize("path", ["dashboard/data.py", "dashboard/app.py"])
def test_dashboard_imports_no_exchange_or_order_code(path):
    tree = ast.parse((REPO / path).read_text())
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
           {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and m.split(".")[0] in ("exchange", "execution", "requests", "websockets", "urllib3", "socket",
                                              "paper_trading", "strategy") for m in mods), mods
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert "/orders" not in node.value


def test_frontend_only_issues_get_requests():
    js = (REPO / "dashboard/static/app.js").read_text()
    assert js.count("fetch(") == 1 and 'fetch("/api/dashboard"' in js
    for bad in ("method:", "POST", "XMLHttpRequest", "WebSocket", "coinbase", "/orders"):
        assert bad not in js, bad
    assert "style=" not in js       # inline styles would be blocked by the page's CSP
