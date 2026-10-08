"""Unit tests: address validation, ENS encoding, classification, attribution, scoring."""
from lead_finder import classification as cls
from lead_finder.attribution import assess
from lead_finder.chains import evm_checksum, is_valid_address, normalize_address
from lead_finder.providers.ens import EnsProfile, namehash, selector
from lead_finder.providers.profiles import GithubProfile, github_login_from_record
from lead_finder.scoring import ScoreInput, compute, eligibility, score_class

from .fakes import ALICE, ERIN, ACME, WHALE, FAMOUS, NOPRICE, SOL_WALLET


def test_fixture_addresses_are_valid():
    for a in (ALICE, ERIN, ACME, WHALE, FAMOUS, NOPRICE):
        assert is_valid_address("ethereum", a), a
    assert is_valid_address("solana", SOL_WALLET)


def test_address_validation_multichain():
    good = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    assert evm_checksum(good.lower()) == good
    assert is_valid_address("ethereum", good)
    assert is_valid_address("base", good.lower())
    assert not is_valid_address("ethereum", good[:-1] + "4")          # mixed case, bad checksum
    assert not is_valid_address("ethereum", "0x1234")
    assert is_valid_address("bitcoin", "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq")
    assert is_valid_address("bitcoin", "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2")
    assert not is_valid_address("bitcoin", "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN3")
    assert is_valid_address("solana", "So11111111111111111111111111111111111111112")
    assert is_valid_address("tron", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    assert not is_valid_address("solana", good)
    assert not is_valid_address("unknownchain", good)
    assert normalize_address("ethereum", good) == good.lower()
    assert normalize_address("solana", SOL_WALLET) == SOL_WALLET   # base58 stays case-sensitive


def test_ens_encoding_matches_spec():
    assert namehash("eth").hex() == "93cdeb708b7545dc668eb9280176169d1c33cfd8ed6f04690a0bcc88a93fc4ae"
    assert selector("addr(bytes32)") == "3b3b57de"
    assert selector("resolver(bytes32)") == "0178b8bf"
    assert selector("name(bytes32)") == "691f3431"
    assert selector("text(bytes32,string)") == "59d1d43c"
    assert github_login_from_record("https://github.com/alice/") == "alice"
    assert github_login_from_record("@bob") == "bob"
    assert github_login_from_record("not a login!") is None


def test_person_name_and_entity_keywords():
    assert cls.looks_like_person_name("Alice Carter")
    assert cls.looks_like_person_name("José María Núñez")
    for bad in ("Acme Capital", "Blue Labs", "alice.eth", "vitalik", "Jump Trading Holdings", "Alpha DAO", "J. K"):
        assert not cls.looks_like_person_name(bad), bad
    for kw in ("Foo Inc", "Bar LLC", "Baz Ltd", "Qux Ventures", "Zed Protocol", "Moon Foundation",
               "Big Exchange", "Fi Finance", "Al Partners", "Ho Holdings", "X Fund"):
        assert cls.entity_keyword_hits(kw), kw
    assert not cls.entity_keyword_hits("Funding Smith")   # word-boundary, not substring


def test_classification_uses_more_than_keywords():
    c, _ = cls.classify(name="Alice Carter", ens_name="alice.eth", github_type="User", labels=[], is_contract=False)
    assert c == cls.INDIVIDUAL
    # Organization account, no keyword in name
    c, r = cls.classify(name="Sam Rivers", ens_name=None, github_type="Organization", labels=[], is_contract=False)
    assert c == cls.ENTITY and "Organization" in r[0]
    # Provider label category
    c, _ = cls.classify(name="Sam Rivers", ens_name=None, github_type="User", labels=[("Wintermute", "Market Maker")],
                        is_contract=False)
    assert c == cls.ENTITY
    # Contract wallet -> uncertain, never individual
    c, _ = cls.classify(name="Sam Rivers", ens_name=None, github_type="User", labels=[], is_contract=True)
    assert c == cls.UNCERTAIN
    c, _ = cls.classify(name=None, ens_name=None, github_type=None, labels=[], is_contract=None)
    assert c == cls.UNCERTAIN


def test_prominence():
    assert cls.assess_prominence(github_followers=50_000, labels=[], bio=None)[0] == "High"
    assert cls.assess_prominence(github_followers=3_000, labels=[], bio=None)[0] == "Medium"
    assert cls.assess_prominence(github_followers=12, labels=[], bio=None)[0] == "Low"
    assert cls.assess_prominence(github_followers=None, labels=[], bio=None)[0] == "Unknown"
    assert cls.assess_prominence(github_followers=1, labels=[("Crypto Influencer", None)], bio=None)[0] == "High"


def _gh(**kw):
    base = dict(login="a", type="User", name="Alice Carter", company=None, blog=None, location=None, email=None,
                bio=None, twitter_username=None, followers=10, html_url="https://github.com/a")
    base.update(kw)
    return GithubProfile(**base)


def test_attribution_levels():
    ens = EnsProfile(address=ALICE, name="alice.eth", records={"com.github": "a"})
    # back-link from GitHub -> High / High
    a = assess(chain="ethereum", address=ALICE, ens=ens, github=_gh(bio="gm alice.eth"), website_hits=[], is_contract=False)
    assert (a.wallet_confidence, a.identity_confidence) == ("High", "High")
    # one-way (owner points at GitHub, GitHub does not point back) -> Medium / Medium
    a = assess(chain="ethereum", address=ALICE, ens=ens, github=_gh(bio="hello"), website_hits=[], is_contract=False)
    assert (a.wallet_confidence, a.identity_confidence) == ("Medium", "Medium")
    # ENS name only, no records -> Low, pseudonymous
    a = assess(chain="ethereum", address=ALICE, ens=EnsProfile(ALICE, "alice.eth", {}), github=None,
               website_hits=[], is_contract=False)
    assert (a.wallet_confidence, a.identity_confidence) == ("Low", "Low")
    # No ENS -> None: co-occurrence elsewhere is never used
    a = assess(chain="ethereum", address=ALICE, ens=None, github=None, website_hits=[], is_contract=None)
    assert a.wallet_confidence == "None" and a.full_name is None
    # Other EVM chain with unknown contract status -> downgraded
    a = assess(chain="base", address=ALICE, ens=ens, github=_gh(bio="alice.eth"), website_hits=[], is_contract=None)
    assert a.wallet_confidence == "Medium"


def test_scoring_weights_unknowns_and_ranking():
    small_strong = compute(ScoreInput(wallet_verified=True, asset_count=2, is_contract=False, attribution="High",
                                      holdings_usd=8_000, holdings_status="Known", has_email=True, has_phone=False,
                                      email_verification="Verified", last_active_at=None, classification="individual",
                                      prominence="Low"))
    big_weak = compute(ScoreInput(wallet_verified=True, asset_count=40, is_contract=False, attribution="Low",
                                  holdings_usd=50_000_000, holdings_status="Known", has_email=False, has_phone=False,
                                  email_verification=None, last_active_at="2099-01-01T00:00:00+00:00",
                                  classification="uncertain", prominence="Unknown"))
    assert small_strong.total > big_weak.total
    unknown = compute(ScoreInput(wallet_verified=False, asset_count=None, is_contract=None, attribution="None",
                                 holdings_usd=None, holdings_status="Holdings unavailable", has_email=False,
                                 has_phone=False, email_verification=None, last_active_at=None,
                                 classification="uncertain", prominence="Unknown"))
    assert unknown.total == 0                                 # no points for unknown information
    assert compute(ScoreInput(True, 1, False, "High", 2e6, "Known", True, True, "Verified",
                              "2099-01-01T00:00:00+00:00", "individual", "Low")).total == 100
    assert [score_class(s) for s in (100, 80, 79, 60, 59, 40, 39, 0)] == \
        ["High", "High", "Good", "Good", "Moderate", "Moderate", "Low", "Low"]


def test_eligibility_requires_every_condition():
    ok = dict(name="Alice Carter", name_is_person=True, address_valid=True, chain_valid=True, has_crypto_evidence=True,
              wallet_attribution="High", identity_confidence="High", contact_self_published=False, has_email=True,
              has_phone=False, classification="individual", prominence="Low", status="new")
    assert eligibility(**ok).contactable
    for key, val in [("name", None), ("address_valid", False), ("chain_valid", False), ("has_crypto_evidence", False),
                     ("wallet_attribution", "Low"), ("identity_confidence", "Low"), ("has_email", False),
                     ("classification", "entity"), ("prominence", "High"), ("status", "do_not_contact")]:
        assert not eligibility(**{**ok, key: val}).contactable, key
    # Medium attribution qualifies only when the contact was self-published by the wallet owner
    assert not eligibility(**{**ok, "wallet_attribution": "Medium"}).contactable
    assert eligibility(**{**ok, "wallet_attribution": "Medium", "contact_self_published": True}).contactable


def _nansen_holdings(rows):
    import httpx
    from lead_finder.providers.nansen import NansenClient

    def handler(request):
        return httpx.Response(200, json={"data": rows, "pagination": {"is_last_page": True}})
    client = NansenClient("k", "https://api.nansen.test", httpx.Client(transport=httpx.MockTransport(handler)))
    return client.holdings("ethereum", ALICE)


def test_nansen_holdings_math():
    eth = "0x0000000000000000000000000000000000000000"
    row = lambda sym, amt, val, tok="0x" + "22" * 20: {"token_symbol": sym, "token_amount": amt,  # noqa: E731
                                                      "value_usd": val, "token_address": tok}
    h = _nansen_holdings([row("ETH", 2, 6000, eth), row("USDC", 1000, 1000), row("variableDebtEthUSDC", 500, 500)])
    assert (h.estimated_value_usd, h.holdings_status, h.asset_count) == (6500, "Known", 2)   # debt subtracted
    assert h.native_balance == 2 and h.debt_positions == ["variableDebtEthUSDC"]
    h = _nansen_holdings([row("ETH", 2, 6000, eth), row("OBSCURE", 5, None)])
    assert (h.estimated_value_usd, h.holdings_status) == (6000, "Partial")
    h = _nansen_holdings([row("OBSCURE", 5, None)])
    assert (h.estimated_value_usd, h.holdings_status) == (None, "Holdings unavailable")
    h = _nansen_holdings([row("variableDebtEthUSDC", 500, None)])
    assert (h.estimated_value_usd, h.holdings_status) == (None, "Holdings unavailable")   # never 0 from unknowns
    h = _nansen_holdings([])
    assert (h.estimated_value_usd, h.holdings_status, h.asset_count) == (0.0, "Known", 0)  # provider-confirmed empty


def test_nansen_error_mapping():
    import httpx
    import pytest
    from lead_finder.providers.base import ProviderError
    from lead_finder.providers.nansen import NansenClient
    for code, body, expected in [(401, {"detail": "bad key"}, "Invalid API key"),
                                 (402, {"detail": "pay"}, "Insufficient credits"),
                                 (403, {"detail": "Insufficient credits"}, "Insufficient credits"),
                                 (403, {"detail": "plan does not include endpoint"}, "Access denied"),
                                 (429, {"detail": "slow down"}, "Rate limited"),
                                 (503, {"detail": "down"}, "Provider error")]:
        http = httpx.Client(transport=httpx.MockTransport(lambda r, c=code, b=body: httpx.Response(c, json=b,
                                                                                                    headers={"Retry-After": "0"})))
        with pytest.raises(ProviderError) as exc:
            NansenClient("k", "https://api.nansen.test", http).holdings("ethereum", ALICE)
        assert exc.value.status == expected, (code, body)
