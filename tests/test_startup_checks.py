from decimal import Decimal

import pytest

from config.settings import Settings
from exchange.client import CoinbaseAdvancedClient
from exchange.transport import ReadOnlyTransport
from execution.fees import FeeSchedule
from paper_trading.runner import StartupRefused, check_key_permissions
from tests.test_no_live_orders import RecordingSession


def settings(allow=False):
    return Settings(paper_mode=True, credentials=None, allow_trade_scoped_key=allow)


def test_view_only_key_accepted():
    assert check_key_permissions({"can_view": True, "can_trade": False, "can_transfer": False}, settings()) == []


def test_transfer_key_always_refused():
    with pytest.raises(StartupRefused, match="TRANSFER"):
        check_key_permissions({"can_view": True, "can_trade": False, "can_transfer": True}, settings(allow=True))


def test_trade_key_refused_unless_explicitly_allowed():
    with pytest.raises(StartupRefused, match="TRADE"):
        check_key_permissions({"can_view": True, "can_trade": True, "can_transfer": False}, settings())
    notes = check_key_permissions({"can_view": True, "can_trade": True, "can_transfer": False}, settings(allow=True))
    assert "blocked" in notes[0]


def test_fee_rates_parsed_from_transaction_summary():
    session = RecordingSession({"total_volume": 0, "fee_tier": {"pricing_tier": "Advanced 1",
                                "maker_fee_rate": "0.006", "taker_fee_rate": "0.012"}})

    class AuthedTransport(ReadOnlyTransport):
        authenticated = True

        def request(self, method, path, params=None):
            return self._session.get("https://api.coinbase.com" + path).json()

    c = CoinbaseAdvancedClient(transport=AuthedTransport(session=session))
    fees = FeeSchedule.from_account(c.get_fee_rates())
    assert fees.maker_rate == Decimal("0.006") and fees.taker_rate == Decimal("0.012")
    assert "Advanced 1" in fees.source
