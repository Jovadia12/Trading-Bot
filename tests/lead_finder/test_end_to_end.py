"""End-to-end tests through the HTTP API with the real provider clients
(network simulated by httpx.MockTransport, see fakes.py)."""
import sqlite3

import pytest

from .conftest import H, db, login
from .fakes import ACME, ALICE, ERIN, FAMOUS, NOPRICE, SOL_WALLET, WHALE


def discover(client, query="", **filters):
    r = client.post("/api/searches", json={"query": query, "filters": filters}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def by_wallet(leads):
    return {l["wallet_address"].lower() if l["wallet_address"].startswith("0x") else l["wallet_address"]: l
            for l in leads}


def all_leads(client):
    c = client.get("/api/leads?category=contactable").json()["leads"]
    o = client.get("/api/leads?category=opportunity").json()["leads"]
    return c, o


# 1. Wallet discovery ---------------------------------------------------------
def test_wallet_discovery_and_pipeline_counts(world, make_client):
    client = make_client(world)
    res = discover(client)
    s = res["search"]
    assert s["discovered"] == 6
    assert s["qualified"] == 6                      # all have provider data + holdings
    assert s["identified"] == 3                     # Alice, Erin, Famous (Famous is then excluded for prominence)
    assert s["contactable"] == 2
    assert s["unattributed"] == 2                   # whale + unpriced wallet (no ENS)
    assert ("api.nansen.test", "/api/v1/tgm/who-bought-sold") in world.calls
    leads = by_wallet(res["contactable"] + res["opportunities"])
    assert set(leads) == {ALICE, ERIN, ACME, WHALE, FAMOUS, NOPRICE}
    pipe = client.get("/api/pipeline").json()
    assert pipe["discovered"] == 6 and pipe["contactable"] == 2 and pipe["saved"] == 0
    # nothing silently dropped: every non-contactable record carries reasons
    assert all(o["opportunity_reasons"] for o in res["opportunities"])


# 2. Provider failure ---------------------------------------------------------
def test_provider_failure_insufficient_credits(world, make_client):
    world.nansen_error = (403, {"detail": "Insufficient credits for this request"})
    client = make_client(world)
    res = discover(client, ALICE)
    assert res["contactable"] == []
    lead = res["opportunities"][0]
    assert lead["holdings_status"] == "Holdings unavailable" and lead["estimated_holdings_usd"] is None
    assert any("Insufficient credits" in r for r in lead["opportunity_reasons"])
    assert res["search"]["provider_report"]["providers"]["Nansen"]["errors"] == {"Insufficient credits": 1}
    status = {p["provider"]: p for p in client.get("/api/providers").json()["providers"]}
    assert status["Nansen"]["status"] == "Insufficient credits"
    # Wallet data failed -> no enrichment was attempted, nothing invented
    assert not any(host == "api.apollo.test" for host, _ in world.calls)


def test_provider_failure_discovery_and_bad_key(world, make_client):
    world.nansen_error = (500, {"detail": "upstream"})
    client = make_client(world)
    res = discover(client)
    assert res["search"]["discovered"] == 0 and res["search"]["status"] == "no_results"
    assert client.get("/api/providers").json()["providers"][0]["status"] == "Provider error"


# 3. Multiple chains ----------------------------------------------------------
def test_multiple_chains_only_verified_chains_exposed(world, make_client):
    client = make_client(world)
    assert client.get("/api/providers").json()["chains"] == []          # nothing verified yet
    discover(client, SOL_WALLET)
    discover(client, ALICE, chain="base")
    discover(client, "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")             # provider has no data -> not verified
    chains = [c["key"] for c in client.get("/api/providers").json()["chains"]]
    assert chains == ["base", "solana"]
    _, opps = all_leads(client)
    sol = by_wallet(opps)[SOL_WALLET]
    assert sol["chain"] == "solana" and sol["estimated_holdings_usd"] == 7500
    assert "Insufficient wallet attribution (None)" in sol["opportunity_reasons"]
    tron = by_wallet(opps)["TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"]
    assert tron["holdings_status"] == "Holdings unavailable"


# 4. Unknown holdings ---------------------------------------------------------
def test_unknown_holdings_never_zero(world, make_client):
    client = make_client(world)
    discover(client, NOPRICE)
    _, opps = all_leads(client)
    lead = by_wallet(opps)[NOPRICE]
    assert lead["estimated_holdings_usd"] is None
    assert lead["holdings_status"] == "Holdings unavailable"
    assert lead["holdings_display"] == "Holdings unavailable"
    detail = client.get(f"/api/leads/{lead['id']}").json()
    assert detail["wallet"]["estimated_portfolio_value"] is None
    assert detail["score_breakdown"]["holdings"] == 0
    # unknown holdings satisfy neither a minimum nor a maximum value filter
    assert NOPRICE not in by_wallet(client.get("/api/leads?category=opportunity&max_value=1000000000").json()["leads"])


# 5-6. Individual classification / entity rejection ---------------------------
def test_individual_vs_entity(world, make_client):
    client = make_client(world)
    discover(client)
    contactable, opps = all_leads(client)
    alice = by_wallet(contactable)[ALICE]
    assert alice["classification"] == "individual" and alice["name"] == "Alice Carter"
    acme = by_wallet(opps)[ACME]
    assert acme["classification"] == "entity"
    assert "Entity / company" in acme["opportunity_reasons"]
    detail = client.get(f"/api/leads/{acme['id']}").json()
    assert any("Organization" in r for r in detail["identity"]["classification_reasons"])
    # entities are never enriched, even though they published an email
    assert not any(c.get("verification_status") == "Verified" for c in detail.get("contacts", []))
    assert acme["email"] is None


# 7-8. Attribution and identity confidence ------------------------------------
def test_attribution_and_identity_confidence(world, make_client):
    client = make_client(world)
    discover(client)
    contactable, opps = all_leads(client)
    every = by_wallet(contactable + opps)
    assert every[ALICE]["wallet_attribution_confidence"] == "High"
    assert every[ALICE]["identity_confidence"] == "High"
    assert every[ERIN]["wallet_attribution_confidence"] == "Medium"
    assert every[ERIN]["identity_confidence"] == "Medium"
    assert every[WHALE]["wallet_attribution_confidence"] == "None"
    assert every[WHALE]["name"] is None                 # anonymous wallet is never de-anonymized
    detail = client.get(f"/api/leads/{every[ALICE]['id']}").json()
    kinds = {(s["kind"], s["provider"]) for s in detail["sources"]}
    assert ("attribution", "ENS") in kinds and ("attribution", "GitHub") in kinds
    assert detail["wallet_source"] == "ENS primary name + profile back-link"


def test_reverse_record_must_forward_verify(world, make_client):
    # Someone claims alice's address in a reverse record for a name that resolves elsewhere.
    world.ens[0].address = WHALE              # name now forward-resolves to another address
    world.ens[0].set_reverse = False
    from .fakes import EnsEntry
    world.ens.append(EnsEntry("alicecarter.eth", WHALE, {}, set_reverse=False))
    client = make_client(world)
    discover(client, ALICE)
    _, opps = all_leads(client)
    assert by_wallet(opps)[ALICE]["wallet_attribution_confidence"] == "None"


# 9, 12. Apollo enrichment + phone -------------------------------------------
def test_apollo_enrichment_and_phone_masking(world, make_client):
    client = make_client(world)
    discover(client)
    contactable, _ = all_leads(client)
    alice = by_wallet(contactable)[ALICE]
    assert alice["apollo_status"] == "Success"
    assert alice["title"] == "Founder & CEO" and alice["company"] == "Carter Analytics"
    assert alice["email"] == "alice@carteranalytics.com"
    assert alice["email_verification_status"] == "Verified"
    assert alice["phone"] == "(XXX) XXX-0123"           # masked in lists
    detail = client.get(f"/api/leads/{alice['id']}").json()
    assert detail["phone"] == "+15125550123"            # full value only in authorized detail view
    assert detail["identity"]["industry"] == "Information Technology"
    assert detail["identity"]["company_size"] == 12


def test_apollo_name_mismatch_is_rejected(world, make_client):
    world.apollo[("Alice", "Carter")]["last_name"] = "Someone-Else"
    client = make_client(world, hunter=False)
    discover(client, ALICE)
    _, opps = all_leads(client)
    alice = by_wallet(opps)[ALICE]
    assert alice["apollo_status"] == "No Match" and alice["email"] is None


def test_apollo_provider_error(world, make_client):
    world.apollo_error = (422, {"error": "insufficient credits"})
    client = make_client(world, hunter=False)
    discover(client, ALICE)
    lead = by_wallet(all_leads(client)[1])[ALICE]
    assert lead["apollo_status"] == "Provider Error"
    assert lead["hunter_status"] == "Not Configured"
    assert "No publicly associated email or phone" in lead["opportunity_reasons"]


# 10. Hunter fallback ----------------------------------------------------------
def test_hunter_fallback_when_apollo_not_configured(world, make_client):
    world.hunter_find[("Alice", "Carter", "alicecarter.dev")] = {
        "email": "alice@alicecarter.dev", "score": 94, "first_name": "Alice", "last_name": "Carter",
        "verification": {"status": "valid"}}
    client = make_client(world, apollo=False)
    discover(client, ALICE)
    contactable, _ = all_leads(client)
    alice = by_wallet(contactable)[ALICE]
    assert alice["apollo_status"] == "Not Configured"
    assert alice["hunter_status"] == "Found"
    assert alice["email"] == "alice@alicecarter.dev" and alice["contact_source"] == "Hunter"
    assert alice["phone"] is None


def test_hunter_low_confidence_and_error(world, make_client):
    world.hunter_find[("Alice", "Carter", "alicecarter.dev")] = {"email": "a@alicecarter.dev", "score": 30}
    client = make_client(world, apollo=False)
    discover(client, ALICE)
    assert by_wallet(all_leads(client)[1])[ALICE]["hunter_status"] == "Not Found"
    world.hunter_error = (401, {"errors": [{"details": "No user found for the API key supplied"}]})
    discover(client, ALICE)
    assert by_wallet(all_leads(client)[1])[ALICE]["hunter_status"] == "Provider Error"


# 11. Email verification ---------------------------------------------------------
def test_email_verification(world, make_client):
    client = make_client(world)
    discover(client, ERIN)
    erin = by_wallet(all_leads(client)[0])[ERIN]
    # self-published by the wallet owner (ENS) and confirmed deliverable by Hunter
    assert erin["email"] == "erin@erinlee.io" and erin["email_verification_status"] == "Verified"
    assert erin["apollo_status"] == "No Match"

    world.hunter_verify["erin@erinlee.io"] = "invalid"
    discover(client, ERIN)
    erin = by_wallet(all_leads(client)[1])[ERIN]
    assert erin["email"] is None
    assert "No publicly associated email or phone" in erin["opportunity_reasons"]


# 13. Duplicate detection ---------------------------------------------------------
def test_deduplication(world, make_client, settings):
    client = make_client(world)
    discover(client)
    discover(client)
    discover(client, ALICE.upper().replace("0X", "0x"))       # different case, same wallet
    conn = db(settings)
    assert conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0] == 6
    # same person on a second chain -> same identity, one card in the contactable list
    discover(client, ALICE, chain="base")
    rows = conn.execute("SELECT identity_id FROM leads WHERE LOWER(wallet_address)=?", (ALICE,)).fetchall()
    assert len(rows) == 2 and rows[0][0] == rows[1][0]
    assert conn.execute("SELECT COUNT(*) FROM identities WHERE full_name='Alice Carter'").fetchone()[0] == 1
    contactable, _ = all_leads(client)
    alice_cards = [l for l in contactable if l["name"] == "Alice Carter"]
    assert len(alice_cards) == 1 and len(alice_cards[0]["other_wallets"]) == 1


# 14. Lead scoring --------------------------------------------------------------
def test_lead_scoring_prefers_attribution_over_size(world, make_client):
    client = make_client(world)
    discover(client)
    every = by_wallet(sum(all_leads(client), []))
    alice, whale = every[ALICE], every[WHALE]
    assert alice["lead_score"] >= 80 and alice["score_class"] == "High"
    assert whale["estimated_holdings_usd"] == 6_000_000
    assert whale["lead_score"] < alice["lead_score"]
    assert whale["score_class"] in ("Low", "Moderate")
    detail = client.get(f"/api/leads/{alice['id']}").json()
    assert sum(detail["score_breakdown"].values()) == alice["lead_score"]


# 5b. Famous people are excluded ------------------------------------------------
def test_public_figure_excluded(world, make_client):
    client = make_client(world)
    discover(client)
    famous = by_wallet(all_leads(client)[1])[FAMOUS]
    assert famous["public_prominence"] == "High"
    assert "Prominent public figure (excluded)" in famous["opportunity_reasons"]
    assert famous["apollo_status"] is None                 # not enriched


# 15-17. Filters -----------------------------------------------------------------
def test_minimum_holdings_activity_and_contact_filters(world, make_client):
    client = make_client(world)
    discover(client)
    opps = lambda q: set(by_wallet(client.get(f"/api/leads?category=opportunity&{q}").json()["leads"]))  # noqa: E731
    cont = lambda q: set(by_wallet(client.get(f"/api/leads?category=contactable&{q}").json()["leads"]))  # noqa: E731
    assert opps("min_value=1000000") == {WHALE, ACME}
    assert NOPRICE not in opps("min_value=0")
    assert cont("min_value=35000") == {ALICE}            # net of DeFi debt: 42,500 - 5,000
    assert cont("min_value=40000") == set()
    assert ACME not in opps("min_activity=1")              # no trades in window
    assert WHALE in opps("min_activity=1")
    assert cont("phone_available=true") == {ALICE}
    assert cont("email_available=true") == {ALICE, ERIN}
    assert cont("email_verified=true") == {ALICE, ERIN}
    assert cont("min_score=95") == set()
    assert cont("funding_interest=true") == {ALICE}       # holds variableDebt (active DeFi borrowing)
    assert cont("state=texas") == {ALICE}
    assert cont("industry=information") == {ALICE}
    assert cont("job_title=founder") == {ALICE}
    assert cont("company_size_max=50") == {ALICE}
    assert cont("chain=solana") == set()


def test_min_value_filter_applies_at_qualification(world, make_client):
    client = make_client(world)
    res = discover(client, min_value=100000)
    s = res["search"]
    assert s["discovered"] == 6 and s["qualified"] == 3      # whale, acme, famous
    nop = by_wallet(res["opportunities"])[NOPRICE]
    assert "Holdings unavailable; cannot confirm minimum portfolio value" in nop["opportunity_reasons"]


# 18. Saved leads ---------------------------------------------------------------
def test_saved_leads_and_crm(world, make_client):
    client = make_client(world)
    discover(client)
    alice = by_wallet(all_leads(client)[0])[ALICE]
    client.post(f"/api/leads/{alice['id']}/notes", json={"body": "Intro call next week"}, headers=H)
    r = client.post(f"/api/leads/{alice['id']}/save", headers=H).json()
    assert r["created"] is True
    snap = r["saved"]["snapshot"]
    for key in ("name", "wallet_address", "chain", "estimated_holdings_usd", "last_active_at", "email", "phone",
                "identity", "sources", "lead_score", "notes", "created_at"):
        assert key in snap, key
    assert snap["phone"] == "+15125550123" and snap["notes"][0]["body"] == "Intro call next week"
    assert r["saved"]["saved_at"]
    again = client.post(f"/api/leads/{alice['id']}/save", headers=H).json()
    assert again["created"] is False                       # no duplicate
    saved = client.get("/api/saved").json()["saved"]
    assert len(saved) == 1
    upd = client.patch(f"/api/saved/{saved[0]['id']}", json={"crm_stage": "crm"}, headers=H).json()
    assert upd["crm_stage"] == "crm"
    pipe = client.get("/api/pipeline").json()
    assert pipe["saved"] == 1 and pipe["crm"] == 1
    # same person through another wallet does not create a second saved lead
    discover(client, ALICE, chain="base")
    base_lead = client.get("/api/leads?category=contactable&chain=base").json()["leads"]
    assert len(base_lead) == 1 and base_lead[0]["wallet_attribution_confidence"] == "High"  # EOA on mainnet
    assert client.post(f"/api/leads/{base_lead[0]['id']}/save", headers=H).json()["created"] is False
    assert len(client.get("/api/saved").json()["saved"]) == 1


# 19. Recent searches + cache reuse ----------------------------------------------
def test_recent_searches_and_rerun_prioritizes_untouched(world, make_client):
    client = make_client(world)
    first = discover(client, min_value=1000)
    erin = by_wallet(first["contactable"])[ERIN]
    alice = by_wallet(first["contactable"])[ALICE]
    client.post(f"/api/leads/{erin['id']}/notes", json={"body": "spoke already"}, headers=H)
    searches = client.get("/api/searches").json()["searches"]
    assert searches[0]["filters"] == {"min_value": 1000.0}
    assert searches[0]["discovered"] == 6 and searches[0]["contactable"] == 2 and searches[0]["created_at"]
    rerun = client.post(f"/api/searches/{first['search']['id']}/rerun", headers=H).json()
    s = rerun["search"]
    assert s["reused"] == 5                                 # all 6 minus Erin, who now has a note
    origin = {l["id"]: l["origin"] for l in rerun["contactable"] + rerun["opportunities"]}
    assert origin[alice["id"]] == "cached" and origin[erin["id"]] == "fresh"
    assert rerun["contactable"][0]["id"] == alice["id"]      # cached first
    assert len(client.get("/api/searches").json()["searches"]) == 2


# 20. Tenant isolation ------------------------------------------------------------
def test_tenant_isolation(world, make_client, settings):
    a = make_client(world)
    discover(a)
    alice = by_wallet(all_leads(a)[0])[ALICE]
    a.post(f"/api/leads/{alice['id']}/notes", json={"body": "private note"}, headers=H)
    a.post(f"/api/leads/{alice['id']}/save", headers=H)
    search_id = a.get("/api/searches").json()["searches"][0]["id"]

    b = make_client(world, email="b@firm-b.test")
    assert all_leads(b) == ([], [])
    assert b.get(f"/api/leads/{alice['id']}").status_code == 404
    assert b.get(f"/api/leads/{alice['id']}/notes").status_code == 404
    assert b.post(f"/api/leads/{alice['id']}/notes", json={"body": "x"}, headers=H).status_code == 404
    assert b.post(f"/api/leads/{alice['id']}/save", headers=H).status_code == 404
    assert b.patch(f"/api/leads/{alice['id']}", json={"status": "suppressed"}, headers=H).status_code == 404
    assert b.delete(f"/api/leads/{alice['id']}", headers=H).status_code == 404
    assert b.get(f"/api/searches/{search_id}").status_code == 404
    assert b.post(f"/api/searches/{search_id}/rerun", headers=H).status_code == 404
    assert b.get("/api/saved").json()["saved"] == []
    assert b.get("/api/searches").json()["searches"] == []
    assert b.get("/api/audit").json()["entries"] == []
    assert b.get("/api/pipeline").json()["discovered"] == 0
    saved_id = a.get("/api/saved").json()["saved"][0]["id"]
    assert b.patch(f"/api/saved/{saved_id}", json={"crm_stage": "crm"}, headers=H).status_code == 404
    # client-provided firm_id is rejected, never used
    assert b.get("/api/leads?firm_id=1").status_code == 422
    assert b.post("/api/searches", json={"query": "", "firm_id": 1}, headers=H).status_code == 422
    # firm B discovering the same wallet gets its own, independent record
    discover(b, ALICE)
    b_alice = by_wallet(sum(all_leads(b), []))[ALICE]
    assert b_alice["id"] != alice["id"] and b_alice["notes_count"] == 0 and b_alice["saved"] is False
    # database itself refuses cross-firm references (composite foreign keys)
    conn = db(settings)
    firm_b = conn.execute("SELECT firm_id FROM users WHERE email='b@firm-b.test'").fetchone()[0]
    user_b = conn.execute("SELECT id FROM users WHERE email='b@firm-b.test'").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO notes(firm_id, lead_id, user_id, body, created_at) VALUES (?,?,?,?,?)",
                     (firm_b, alice["id"], user_b, "x", "2026-01-01"))
    # unauthenticated access is refused
    from fastapi.testclient import TestClient
    anon = TestClient(a.app)
    assert anon.get("/api/leads").status_code == 401


# 21. Audit logging ---------------------------------------------------------------
def test_audit_log(world, make_client):
    client = make_client(world)
    discover(client)
    every = by_wallet(sum(all_leads(client), []))
    client.post(f"/api/leads/{every[ALICE]['id']}/save", headers=H)
    client.patch(f"/api/leads/{every[ERIN]['id']}", json={"status": "suppressed"}, headers=H)
    client.patch(f"/api/leads/{every[WHALE]['id']}", json={"status": "do_not_contact"}, headers=H)
    client.delete(f"/api/leads/{every[NOPRICE]['id']}", headers=H)
    discover(client, ALICE)
    entries = client.get("/api/audit").json()["entries"]
    actions = {e["action"] for e in entries}
    assert {"lead_discovered", "lead_enriched", "lead_saved", "lead_updated", "lead_suppressed",
            "lead_marked_do_not_contact", "lead_deleted"} <= actions
    for e in entries:
        assert e["user"] == "a@firm-a.test" and e["created_at"]
        assert "@" not in (e["detail"] or "") and "+1512" not in (e["detail"] or "")
    assert all(e["lead_id"] for e in entries if e["action"].startswith("lead_"))
    # suppressed / DNC leads leave the contactable list and are not re-enriched
    contactable, _ = all_leads(client)
    assert ERIN not in by_wallet(contactable)
    deleted = [l for l in sum(all_leads(client), []) if l["wallet_address"] == NOPRICE]
    assert deleted == []


# 22. No fabricated leads ---------------------------------------------------------
def test_no_fabricated_leads_without_providers(world, make_client, settings):
    client = make_client(world, nansen=False, rpc=False, apollo=False, hunter=False)
    res = discover(client)
    assert res["search"]["discovered"] == 0 and res["contactable"] == [] and res["opportunities"] == []
    res = discover(client, ALICE)
    lead = res["opportunities"][0]
    assert lead["name"] is None and lead["email"] is None and lead["phone"] is None
    assert lead["estimated_holdings_usd"] is None and lead["lead_score"] == 0
    conn = db(settings)
    assert conn.execute("SELECT COUNT(*) FROM identities").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 0
    status = {p["provider"]: p["status"] for p in client.get("/api/providers").json()["providers"]}
    assert status["Nansen"] == status["Apollo"] == status["Hunter"] == "Not Configured"


def test_every_contact_traces_to_provider_data(world, make_client, settings):
    client = make_client(world)
    discover(client)
    known = {"alice@carteranalytics.com", "+15125550123", "erin@erinlee.io"}
    conn = db(settings)
    for (value,) in conn.execute("SELECT value FROM contacts"):
        assert value in known, value


# 23. No automatic account switching from wallets ---------------------------------
def test_wallets_never_authenticate(world, make_client, settings):
    client = make_client(world)
    discover(client)
    me_before = client.get("/api/me").json()
    discover(client, ALICE)
    assert client.get("/api/me").json() == me_before
    conn = db(settings)
    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    assert not any("wallet" in c or "address" in c for c in user_cols)
    from fastapi.testclient import TestClient
    fresh = TestClient(client.app)
    assert fresh.post("/api/auth/login", json={"email": ALICE, "password": "x"}, headers=H).status_code == 401
    assert fresh.post("/api/auth/wallet", json={"address": ALICE}, headers=H).status_code in (404, 405)
    assert fresh.get("/api/me").status_code == 401
    routes = {getattr(r, "path", "") for r in client.app.routes}
    assert not any("wallet" in p for p in routes)


def test_csrf_header_required(world, make_client):
    client = make_client(world)
    assert client.post("/api/searches", json={"query": ""}).status_code == 403
