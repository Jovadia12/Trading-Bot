"""Proof that no live order / funds endpoint is reachable."""
import ast
import re
import socket
from pathlib import Path

import pytest
import requests

from exchange.client import DISABLED_METHODS, CoinbaseAdvancedClient, ExchangeClient
from exchange.endpoints import FORBIDDEN_ENDPOINTS, READ_ONLY_ENDPOINTS, match_read_only
from exchange.errors import LIVE_DISABLED_MESSAGE, ForbiddenEndpointError, LiveOrderExecutionDisabled
from exchange.transport import ReadOnlyTransport

REPO = Path(__file__).resolve().parent.parent
MSG = "LIVE ORDER EXECUTION DISABLED: research/paper mode only."


class RecordingSession:
    """Stands in for requests.Session; records every call and never touches the network."""

    def __init__(self, payload=None):
        self.calls = []
        self.payload = payload or {}

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, params, headers))

        class R:
            status_code = 200
            text = "{}"

            def json(_):
                return self.payload
        return R()

    def post(self, *a, **k):  # pragma: no cover - must never be reached
        self.calls.append(("POST", a, k))
        raise AssertionError("POST reached the session")

    request = put = delete = patch = post


def test_message_is_exact():
    assert LIVE_DISABLED_MESSAGE == MSG


@pytest.mark.parametrize("name", DISABLED_METHODS)
def test_every_order_and_funds_method_raises(name):
    client = CoinbaseAdvancedClient(transport=ReadOnlyTransport(session=RecordingSession()))
    with pytest.raises(LiveOrderExecutionDisabled, match=re.escape(MSG)):
        getattr(client, name)("BTC-USD", "BUY", "1")


@pytest.mark.parametrize("name", ["market_order_buy", "limit_order_gtc_sell", "create_order_v2", "withdraw_btc",
                                  "send_money", "transfer", "move_funds", "preview_market_order"])
def test_unknown_trading_like_attributes_raise(name):
    client = CoinbaseAdvancedClient(transport=ReadOnlyTransport(session=RecordingSession()))
    with pytest.raises(LiveOrderExecutionDisabled, match=re.escape(MSG)):
        getattr(client, name)


@pytest.mark.parametrize("method,path", FORBIDDEN_ENDPOINTS)
def test_transport_refuses_forbidden_endpoints_before_network(method, path):
    session = RecordingSession()
    t = ReadOnlyTransport(session=session)
    with pytest.raises(ForbiddenEndpointError, match=re.escape(MSG)):
        t.request(method, path)
    assert session.calls == []


@pytest.mark.parametrize("verb", ["post", "put", "delete", "patch"])
def test_transport_write_verbs_raise(verb):
    with pytest.raises(ForbiddenEndpointError):
        getattr(ReadOnlyTransport(session=RecordingSession()), verb)("/api/v3/brokerage/orders", json={})


def test_allowlist_is_get_only_and_contains_no_order_paths():
    for pattern, _ in READ_ONLY_ENDPOINTS:
        src = pattern.pattern
        assert "orders" not in src and "convert" not in src and "move_funds" not in src
    for m in ("POST", "PUT", "DELETE", "PATCH"):
        assert match_read_only(m, "/api/v3/brokerage/accounts") == (False, False)


def test_client_reads_only_issue_allowlisted_gets():
    session = RecordingSession({"product_id": "BTC-USD", "pricebook": {"bids": [{"price": "1", "size": "1"}],
                                "asks": [{"price": "2", "size": "1"}], "time": "2026-09-24T00:00:00Z"},
                                "candles": [], "trades": []})
    c = CoinbaseAdvancedClient(transport=ReadOnlyTransport(session=session))
    c.get_product("BTC-USD"); c.get_order_book("BTC-USD"); c.get_best_bid_ask("BTC-USD")
    from datetime import datetime, timezone
    c.get_candles("BTC-USD", datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 9, 2, tzinfo=timezone.utc))
    c.get_market_trades("BTC-USD")
    assert session.calls, "expected GET calls"
    for verb, url, _params, _headers in session.calls:
        assert verb == "GET"
        path = url.replace("https://api.coinbase.com", "")
        assert match_read_only("GET", path)[0], path
        assert "/orders" not in path


def test_paper_engine_has_no_exchange_dependency():
    for mod in ("execution/paper_engine.py", "execution/models.py", "execution/fees.py",
                "paper_trading/account.py", "paper_trading/recorder.py"):
        tree = ast.parse((REPO / mod).read_text())
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | \
                   {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any(m.startswith(("exchange", "requests", "websockets", "socket", "http", "urllib"))
                       for m in imported), (mod, imported)


def test_no_live_execution_engine_exists():
    for path in REPO.rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
        assert not any(n.lower().startswith(("liveexecution", "live_execution", "place_live")) for n in names), path


def test_no_code_calls_write_http_methods():
    offenders = []
    for path in REPO.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text()
        if re.search(r"requests\.(post|put|delete|patch)\(|session\.(post|put|delete|patch)\(|\.request\(\s*['\"](POST|PUT|DELETE|PATCH)",
                     text, re.I):
            offenders.append(str(path))
        # the only file allowed to mention the orders endpoint is the documented blocklist
        if "brokerage/orders" in text or '/orders"' in text:
            if path.name != "endpoints.py":
                offenders.append(f"{path}: mentions orders endpoint")
    assert offenders == []


def test_full_paper_session_makes_no_network_calls(monkeypatch, tmp_path):
    """Run the whole paper pipeline (replay + scripted round trip) with the network sabotaged."""
    def boom(*a, **k):
        raise AssertionError(f"network access attempted: {a!r}")
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(requests.Session, "request", boom)
    from paper_trading.runner import main
    rc = main(["--replay", "tests/fixtures/ws_btcusd_synthetic.jsonl", "--demo-roundtrip",
               "--records-dir", str(tmp_path)])
    assert rc == 0
    trades = list(tmp_path.rglob("trades.csv"))[0].read_text().strip().splitlines()
    assert len(trades) == 2  # header + one round trip
