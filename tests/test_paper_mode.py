import pytest

from config.settings import PaperModeError, load_settings, require_paper_mode
from exchange.client import CoinbaseAdvancedClient
from execution.fees import DEFAULT_US_ENTRY_TIER
from execution.paper_engine import PaperExecutionEngine
from paper_trading.account import PaperAccount
from paper_trading.runner import main


@pytest.mark.parametrize("value", [None, "", "false", "False", "0", "1", "yes", "live", "true-ish", "no"])
def test_refuses_unless_paper_mode_true(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("PAPER_MODE", raising=False)
    else:
        monkeypatch.setenv("PAPER_MODE", value)
    with pytest.raises(PaperModeError):
        require_paper_mode()
    with pytest.raises(PaperModeError):
        load_settings(env_file="/nonexistent/.env")


@pytest.mark.parametrize("value", ["true", "TRUE", " True "])
def test_accepts_true(monkeypatch, value):
    monkeypatch.setenv("PAPER_MODE", value)
    require_paper_mode()


def test_components_refuse_to_construct_without_paper_mode(monkeypatch, product):
    monkeypatch.setenv("PAPER_MODE", "false")
    with pytest.raises(PaperModeError):
        CoinbaseAdvancedClient()
    with pytest.raises(PaperModeError):
        PaperExecutionEngine(product, DEFAULT_US_ENTRY_TIER, PaperAccount())


def test_application_exits_nonzero_without_paper_mode(monkeypatch, capsys):
    monkeypatch.delenv("PAPER_MODE", raising=False)
    assert main(["--replay", "tests/fixtures/ws_btcusd_synthetic.jsonl"]) == 2
    assert "PAPER_MODE must be set to 'true'" in capsys.readouterr().err
