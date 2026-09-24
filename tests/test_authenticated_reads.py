"""Authenticated read-only integration, exercised against mocked Coinbase responses."""
import base64
import logging
from decimal import Decimal

import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from config.settings import Credentials
from exchange.client import CoinbaseAdvancedClient, summarize_balances
from exchange.transport import ReadOnlyTransport
from market_data.websocket_feed import CoinbaseMarketDataFeed, replay_file
from paper_trading.diagnostics import run_rest_checks

FAKE_KEY = "organizations/fake-org-0000/apiKeys/fake-key-1111"
PRODUCT = {"product_id": "BTC-USD", "base_currency_id": "BTC", "quote_currency_id": "USD",
           "base_increment": "0.00000001", "quote_increment": "0.01", "price_increment": "0.01",
           "base_min_size": "0.00000001", "base_max_size": "3400", "quote_min_size": "1", "status": "online"}
ACCOUNTS_P1 = {"accounts": [{"uuid": "a1", "currency": "USD", "available_balance": {"value": "123.45", "currency": "USD"}}],
               "has_next": True, "cursor": "c2"}
ACCOUNTS_P2 = {"accounts": [{"uuid": "a2", "currency": "BTC", "available_balance": {"value": "0.0100", "currency": "BTC"}},
                            {"uuid": "a3", "currency": "ETH", "available_balance": {"value": "1", "currency": "ETH"}}],
               "has_next": False, "cursor": ""}
FEES = {"total_volume": 0, "total_fees": 0,
        "fee_tier": {"pricing_tier": "Advanced 1", "usd_from": "0", "usd_to": "10000",
                     "taker_fee_rate": "0.009", "maker_fee_rate": "0.005"}}
PERMS = {"can_view": True, "can_trade": False, "can_transfer": False, "portfolio_uuid": "p", "portfolio_type": "DEFAULT"}


def fake_secret():
    sk = ed25519.Ed25519PrivateKey.generate()
    seed = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(seed + pub).decode()


class Resp:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload
        self.text = "Unauthorized" if status == 401 else "{}"

    def json(self):
        return self._p


class FakeCoinbase:
    """Routes GETs by path. auth_ok=False makes every authenticated path return 401."""

    def __init__(self, auth_ok=True, perms=PERMS):
        self.auth_ok, self.perms, self.calls = auth_ok, perms, []

    def get(self, url, params=None, headers=None, timeout=None):
        path = url.replace("https://api.coinbase.com", "")
        authed = "Authorization" in (headers or {})
        self.calls.append((path, authed, dict(params or {})))
        public = {"/api/v3/brokerage/market/products/BTC-USD": PRODUCT}
        if path in public:
            return Resp(200, public[path])
        if not authed or not self.auth_ok:
            return Resp(401, {"error": "UNAUTHORIZED"})
        assert headers["Authorization"].startswith("Bearer ey")
        if path == "/api/v3/brokerage/key_permissions":
            return Resp(200, self.perms)
        if path == "/api/v3/brokerage/products/BTC-USD":
            return Resp(200, PRODUCT)
        if path == "/api/v3/brokerage/accounts":
            return Resp(200, ACCOUNTS_P2 if (params or {}).get("cursor") == "c2" else ACCOUNTS_P1)
        if path == "/api/v3/brokerage/transaction_summary":
            return Resp(200, FEES)
        if path == "/api/v3/brokerage/portfolios":
            return Resp(200, {"portfolios": [{"name": "Default", "uuid": "p", "type": "DEFAULT"}]})
        return Resp(404, {})


def client_for(fake, secret=None):
    creds = Credentials(FAKE_KEY, secret or fake_secret())
    return CoinbaseAdvancedClient(transport=ReadOnlyTransport(creds, session=fake))


def test_account_reads_with_pagination_and_balances():
    fake = FakeCoinbase()
    c = client_for(fake)
    accts = c.get_accounts()
    assert [a["uuid"] for a in accts] == ["a1", "a2", "a3"]
    assert summarize_balances(accts) == {"USD": Decimal("123.45"), "BTC": Decimal("0.0100")}
    assert c.get_portfolios()[0]["type"] == "DEFAULT"
    assert all(authed for _p, authed, _ in fake.calls)


def test_fee_parsing_from_mocked_transaction_summary():
    rates = client_for(FakeCoinbase()).get_fee_rates()
    assert rates["maker_fee_rate"] == Decimal("0.005") and rates["taker_fee_rate"] == Decimal("0.009")
    assert rates["pricing_tier"] == "Advanced 1"


def test_product_read_authenticated():
    spec = client_for(FakeCoinbase()).get_product("BTC-USD")
    assert spec.product_id == "BTC-USD" and spec.quote_min_size == Decimal(1)


def test_diagnostics_all_success_with_mocked_coinbase():
    d = run_rest_checks(client_for(FakeCoinbase()), credentials_loaded=True)
    assert (d.authenticated, d.product, d.account, d.fees) == (True, True, True, True)
    assert d.fee_schedule.maker_rate == Decimal("0.005")
    lines = d.lines()
    assert lines == ["API credentials loaded: YES", "Authenticated Coinbase connection: SUCCESS",
                     "BTC/USD product: SUCCESS", "Market data stream: FAIL", "Account data: SUCCESS",
                     "Fee data: SUCCESS", "PAPER MODE: ENABLED"]


def test_authentication_failure_is_handled_safely(caplog):
    caplog.set_level(logging.DEBUG)
    secret = fake_secret()
    fake = FakeCoinbase(auth_ok=False)
    d = run_rest_checks(client_for(fake, secret), credentials_loaded=True)   # must not raise
    assert not d.authenticated and not d.account and not d.fees
    assert d.product  # public product endpoint still works
    assert d.errors["authentication"] == "ExchangeAPIError (HTTP 401)"
    blob = caplog.text + repr(d.errors) + "\n".join(d.lines())
    assert secret not in blob and FAKE_KEY not in blob


def test_malformed_secret_is_handled_safely():
    bad = "this-is-not-a-valid-key-but-looks-secret-123456"
    d = run_rest_checks(client_for(FakeCoinbase(), secret=bad), credentials_loaded=True)
    assert not d.authenticated and d.product
    assert bad not in repr(d.errors) and bad not in "\n".join(d.lines())


def test_no_credentials_reports_no_and_fail():
    c = CoinbaseAdvancedClient(transport=ReadOnlyTransport(None, session=FakeCoinbase()))
    d = run_rest_checks(c, credentials_loaded=False)
    assert d.lines()[:2] == ["API credentials loaded: NO", "Authenticated Coinbase connection: FAIL"]
    assert d.product and not d.account and not d.fees


@pytest.fixture
def live_like(monkeypatch):
    """Mock Coinbase REST via requests.Session.get and the WS feed via the synthetic replay."""
    fake = FakeCoinbase()
    monkeypatch.setattr(requests.Session, "get", lambda self, url, **kw: fake.get(url, **kw))

    async def fake_stream(self, stop_after=None):
        for ev in replay_file("tests/fixtures/ws_btcusd_synthetic.jsonl"):
            self.state.messages += 1
            yield ev
    monkeypatch.setattr(CoinbaseMarketDataFeed, "stream", fake_stream)
    return fake


def test_full_authenticated_session_output(monkeypatch, capsys, tmp_path, live_like):
    secret = fake_secret()
    monkeypatch.setenv("COINBASE_API_KEY", FAKE_KEY)
    monkeypatch.setenv("COINBASE_API_SECRET", secret)
    from paper_trading.runner import main
    rc = main(["--duration", "60", "--records-dir", str(tmp_path)])
    out = capsys.readouterr()
    assert rc == 0
    lines = out.out.splitlines()
    assert lines[:7] == ["API credentials loaded: YES", "Authenticated Coinbase connection: SUCCESS",
                         "BTC/USD product: SUCCESS", "Market data stream: SUCCESS", "Account data: SUCCESS",
                         "Fee data: SUCCESS", "PAPER MODE: ENABLED"]
    assert "order_endpoint_called: NO" in out.out and "simulated_trades: 0" in out.out
    assert "authentication: SUCCESS" in out.out and "fee_info: {'maker': '0.005'" in out.out
    for blob in [out.out, out.err] + [p.read_text() for p in tmp_path.rglob("*") if p.is_file()]:
        assert secret not in blob and FAKE_KEY not in blob
        assert "123.45" not in blob   # real balances are never printed or written by default
    assert not any("/orders" in p for p, _a, _ in live_like.calls)


def test_trade_scoped_key_refused_at_startup(monkeypatch, capsys, tmp_path, live_like):
    live_like.perms = dict(PERMS, can_trade=True)
    monkeypatch.setenv("COINBASE_API_KEY", FAKE_KEY)
    monkeypatch.setenv("COINBASE_API_SECRET", fake_secret())
    from paper_trading.runner import main
    assert main(["--duration", "5", "--records-dir", str(tmp_path)]) == 3
    assert "STARTUP REFUSED" in capsys.readouterr().err
