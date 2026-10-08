"""Firm-scoped data access.

``FirmRepository`` is constructed from an authenticated ``AuthContext``; its
``firm_id`` is never taken from request input. Every statement below filters or
writes by that firm_id, and the schema's composite foreign keys make
cross-firm references impossible even if a query were wrong.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .chains import mask_address
from .providers.enrichment import fold
from .security import AuthContext, iso

LEAD_STATUSES = {"new", "saved", "contacted", "suppressed", "do_not_contact", "deleted"}
STATUS_AUDIT = {"suppressed": "lead_suppressed", "do_not_contact": "lead_marked_do_not_contact",
                "deleted": "lead_deleted"}


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = [c for c in phone if c.isdigit()]
    if len(digits) < 4:
        return "(XXX) XXX-XXXX"
    return f"(XXX) XXX-{''.join(digits[-4:])}"


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except ValueError:
        return default


class FirmRepository:
    def __init__(self, conn: sqlite3.Connection, auth: AuthContext):
        self.conn = conn
        self.firm_id = auth.firm_id
        self.user_id = auth.user_id

    # ---------------------------------------------------------------- utils
    @contextmanager
    def tx(self) -> Iterator[None]:
        if self.conn.in_transaction:
            yield
            return
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def audit(self, action: str, lead_id: int | None = None, detail: str | None = None) -> None:
        """Audit entries carry ids and short non-sensitive details only (no emails/phones)."""
        self.conn.execute(
            "INSERT INTO audit_log(firm_id, user_id, action, lead_id, detail, created_at) VALUES (?,?,?,?,?,?)",
            (self.firm_id, self.user_id, action, lead_id, (detail or "")[:200] or None, iso()))

    def audit_log(self, limit: int = 200) -> list[dict]:
        rows = self.conn.execute(
            """SELECT a.id, a.action, a.lead_id, a.detail, a.created_at, u.email AS user
                 FROM audit_log a LEFT JOIN users u ON u.id = a.user_id AND u.firm_id = a.firm_id
                WHERE a.firm_id = ? ORDER BY a.id DESC LIMIT ?""", (self.firm_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------- wallets
    def upsert_wallet(self, w: dict) -> tuple[int, bool]:
        """Dedup key: (firm, chain, normalized address). Returns (id, created)."""
        now = iso()
        row = self.conn.execute("SELECT id FROM wallets WHERE firm_id=? AND chain=? AND address=?",
                                (self.firm_id, w["chain"], w["address"])).fetchone()
        cols = ["display_address", "estimated_portfolio_value", "holdings_status", "native_balance",
                "native_symbol", "asset_count", "token_holdings_json", "recent_activity_count",
                "last_active_at", "activity_json", "debt_positions_json", "provider_labels_json",
                "is_contract", "source", "provider_status"]
        if row:
            sets = ", ".join(f"{c}=?" for c in cols)
            self.conn.execute(f"UPDATE wallets SET {sets}, updated_at=? WHERE firm_id=? AND id=?",
                              [w.get(c) for c in cols] + [now, self.firm_id, row["id"]])
            return int(row["id"]), False
        cur = self.conn.execute(
            f"INSERT INTO wallets(firm_id, chain, address, {', '.join(cols)}, discovered_at, updated_at) "
            f"VALUES (?,?,?,{','.join('?' * len(cols))},?,?)",
            [self.firm_id, w["chain"], w["address"]] + [w.get(c) for c in cols] + [now, now])
        return int(cur.lastrowid), True

    def get_wallet(self, wallet_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM wallets WHERE firm_id=? AND id=?", (self.firm_id, wallet_id)).fetchone()
        return dict(row) if row else None

    def find_lead_by_wallet(self, chain: str, address: str) -> dict | None:
        row = self.conn.execute(
            """SELECT l.* FROM leads l JOIN wallets w ON w.firm_id=l.firm_id AND w.id=l.wallet_id
                WHERE l.firm_id=? AND w.chain=? AND w.address=?""", (self.firm_id, chain, address)).fetchone()
        return dict(row) if row else None

    # ----------------------------------------------------------- identities
    def upsert_identity(self, ident: dict, emails: list[str]) -> int:
        """Dedup people by email first, then by name + company."""
        now = iso()
        name_key = fold(ident.get("full_name")) or None
        company_key = fold(ident.get("company"))
        existing = None
        for email in emails:
            existing = self.conn.execute(
                "SELECT identity_id AS id FROM contacts WHERE firm_id=? AND kind='email' AND value=?",
                (self.firm_id, email.lower())).fetchone()
            if existing:
                break
        if not existing and name_key:
            existing = self.conn.execute(
                "SELECT id FROM identities WHERE firm_id=? AND name_key=? AND company_key=?",
                (self.firm_id, name_key, company_key)).fetchone()
        if not existing and ident.get("ens_name"):
            existing = self.conn.execute("SELECT id FROM identities WHERE firm_id=? AND ens_name=?",
                                         (self.firm_id, ident["ens_name"])).fetchone()
        cols = ["full_name", "company", "title", "linkedin", "city", "state", "country", "zip",
                "location_text", "industry", "company_size", "company_founded_year", "company_domain",
                "ens_name", "github_login", "website", "classification", "classification_reasons_json",
                "identity_confidence", "identity_source", "public_prominence", "prominence_reasons_json"]
        values = [ident.get(c) for c in cols]
        if existing:
            sets = ", ".join(f"{c}=COALESCE(?, {c})" for c in cols)
            self.conn.execute(
                f"UPDATE identities SET {sets}, name_key=COALESCE(?, name_key), company_key=?, updated_at=? "
                "WHERE firm_id=? AND id=?",
                values + [name_key, company_key, now, self.firm_id, existing["id"]])
            return int(existing["id"])
        cur = self.conn.execute(
            f"INSERT INTO identities(firm_id, {', '.join(cols)}, name_key, company_key, created_at, updated_at) "
            f"VALUES (?,{','.join('?' * len(cols))},?,?,?,?)",
            [self.firm_id] + values + [name_key, company_key, now, now])
        return int(cur.lastrowid)

    def upsert_contact(self, identity_id: int, kind: str, value: str, source: str,
                       self_published: bool, verification: str) -> None:
        now = iso()
        value = value.strip().lower() if kind == "email" else value.strip()
        self.conn.execute(
            """INSERT INTO contacts(firm_id, identity_id, kind, value, source, self_published,
                                    verification_status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(firm_id, kind, value) DO UPDATE SET
                   verification_status=excluded.verification_status,
                   self_published=MAX(contacts.self_published, excluded.self_published),
                   updated_at=excluded.updated_at""",
            (self.firm_id, identity_id, kind, value, source, int(self_published), verification, now, now))

    def contacts_for(self, identity_id: int) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM contacts WHERE firm_id=? AND identity_id=? ORDER BY id",
                                 (self.firm_id, identity_id)).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- leads
    LEAD_COLS = ["identity_id", "name", "title", "company", "email", "phone", "linkedin", "wallet_address",
                 "chain", "estimated_holdings_usd", "holdings_status", "recent_activity", "last_active_at",
                 "asset_count", "identity_confidence", "wallet_attribution_confidence", "identity_source",
                 "wallet_source", "contact_source", "email_verification_status", "public_prominence",
                 "classification", "funding_interest", "apollo_status", "hunter_status", "stage", "category",
                 "opportunity_reasons_json", "lead_score", "score_class"]

    def upsert_lead(self, wallet_id: int, fields: dict) -> tuple[int, bool]:
        """One lead per (firm, wallet). Re-discovery updates the existing lead."""
        now = iso()
        row = self.conn.execute("SELECT id, status FROM leads WHERE firm_id=? AND wallet_id=?",
                                (self.firm_id, wallet_id)).fetchone()
        values = [fields.get(c) for c in self.LEAD_COLS]
        if row:
            sets = ", ".join(f"{c}=?" for c in self.LEAD_COLS)
            self.conn.execute(f"UPDATE leads SET {sets}, updated_at=? WHERE firm_id=? AND id=?",
                              values + [now, self.firm_id, row["id"]])
            return int(row["id"]), False
        cur = self.conn.execute(
            f"INSERT INTO leads(firm_id, wallet_id, {', '.join(self.LEAD_COLS)}, status, created_at, updated_at) "
            f"VALUES (?,?,{','.join('?' * len(self.LEAD_COLS))},'new',?,?)",
            [self.firm_id, wallet_id] + values + [now, now])
        return int(cur.lastrowid), True

    def add_sources(self, lead_id: int, items: list[tuple[str, str, str, str]]) -> None:
        now = iso()
        for kind, provider, url, detail in items:
            self.conn.execute(
                """INSERT OR IGNORE INTO lead_sources(firm_id, lead_id, kind, provider, url, detail, observed_at)
                   VALUES (?,?,?,?,?,?,?)""", (self.firm_id, lead_id, kind, provider, url or "", detail or "", now))

    def record_score(self, lead_id: int, score: int, cls: str, breakdown: dict) -> None:
        self.conn.execute(
            "INSERT INTO lead_scores(firm_id, lead_id, score, score_class, breakdown_json, computed_at) VALUES (?,?,?,?,?,?)",
            (self.firm_id, lead_id, score, cls, json.dumps(breakdown), iso()))

    def _lead_row(self, lead_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM leads WHERE firm_id=? AND id=?", (self.firm_id, lead_id)).fetchone()

    def lead_exists(self, lead_id: int) -> bool:
        return self._lead_row(lead_id) is not None

    def note_count(self, lead_id: int) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM notes WHERE firm_id=? AND lead_id=?",
                                 (self.firm_id, lead_id)).fetchone()[0]

    def serialize_lead(self, row: sqlite3.Row | dict, *, reveal: bool = False) -> dict:
        d = dict(row)
        d["opportunity_reasons"] = _loads(d.pop("opportunity_reasons_json", None), [])
        d["wallet_display"] = mask_address(d["wallet_address"])
        d["holdings_display"] = (
            "Holdings unavailable" if d["estimated_holdings_usd"] is None
            else f"${d['estimated_holdings_usd']:,.0f}" + (" (partial)" if d["holdings_status"] == "Partial" else ""))
        if not reveal:
            d["phone"] = mask_phone(d.get("phone"))
        d["notes_count"] = self.note_count(d["id"])
        d["saved"] = bool(self.conn.execute("SELECT 1 FROM saved_leads WHERE firm_id=? AND lead_id=?",
                                            (self.firm_id, d["id"])).fetchone())
        d.pop("firm_id", None)
        return d

    def get_lead(self, lead_id: int, *, reveal: bool = False) -> dict | None:
        row = self._lead_row(lead_id)
        return self.serialize_lead(row, reveal=reveal) if row else None

    def lead_detail(self, lead_id: int) -> dict | None:
        lead = self.get_lead(lead_id, reveal=True)
        if not lead:
            return None
        wallet = self.get_wallet(lead["wallet_id"]) or {}
        lead["wallet"] = {
            "address": wallet.get("display_address"), "chain": wallet.get("chain"),
            "estimated_portfolio_value": wallet.get("estimated_portfolio_value"),
            "holdings_status": wallet.get("holdings_status"), "native_balance": wallet.get("native_balance"),
            "native_symbol": wallet.get("native_symbol"), "asset_count": wallet.get("asset_count"),
            "tokens": _loads(wallet.get("token_holdings_json"), []),
            "recent_activity_count": wallet.get("recent_activity_count"),
            "last_active_at": wallet.get("last_active_at"), "activity": _loads(wallet.get("activity_json"), {}),
            "debt_positions": _loads(wallet.get("debt_positions_json"), []),
            "provider_labels": _loads(wallet.get("provider_labels_json"), []),
            "is_contract": None if wallet.get("is_contract") is None else bool(wallet["is_contract"]),
            "source": wallet.get("source"), "provider_status": wallet.get("provider_status"),
            "discovered_at": wallet.get("discovered_at"),
        }
        lead["identity"] = None
        if lead.get("identity_id"):
            ident = self.conn.execute("SELECT * FROM identities WHERE firm_id=? AND id=?",
                                      (self.firm_id, lead["identity_id"])).fetchone()
            if ident:
                i = dict(ident)
                i.pop("firm_id", None)
                i["classification_reasons"] = _loads(i.pop("classification_reasons_json", None), [])
                i["prominence_reasons"] = _loads(i.pop("prominence_reasons_json", None), [])
                lead["identity"] = i
                lead["contacts"] = [{k: c[k] for k in ("kind", "value", "source", "self_published",
                                                       "verification_status")}
                                    for c in self.contacts_for(lead["identity_id"])]
                lead["other_wallets"] = [dict(r) for r in self.conn.execute(
                    "SELECT id, chain, wallet_address FROM leads WHERE firm_id=? AND identity_id=? AND id<>?",
                    (self.firm_id, lead["identity_id"], lead_id)).fetchall()]
        lead["sources"] = [dict(r) for r in self.conn.execute(
            "SELECT kind, provider, url, detail, observed_at FROM lead_sources WHERE firm_id=? AND lead_id=? ORDER BY id",
            (self.firm_id, lead_id)).fetchall()]
        score = self.conn.execute(
            "SELECT breakdown_json FROM lead_scores WHERE firm_id=? AND lead_id=? ORDER BY id DESC LIMIT 1",
            (self.firm_id, lead_id)).fetchone()
        lead["score_breakdown"] = _loads(score["breakdown_json"], {}) if score else {}
        lead["notes"] = self.list_notes(lead_id)
        return lead

    def list_leads(self, *, category: str | None = None, filters: dict | None = None,
                   lead_ids: list[int] | None = None, limit: int = 200) -> list[dict]:
        f = filters or {}
        where = ["l.firm_id = ?", "l.status NOT IN ('deleted')"]
        params: list[Any] = [self.firm_id]
        if category:
            where.append("l.category = ?")
            params.append(category)
        if lead_ids is not None:
            if not lead_ids:
                return []
            where.append(f"l.id IN ({','.join('?' * len(lead_ids))})")
            params.extend(lead_ids)

        def like(col: str, key: str) -> None:
            if f.get(key):
                where.append(f"LOWER(COALESCE({col}, '')) LIKE ?")
                params.append(f"%{str(f[key]).lower()}%")

        like("i.country", "country")
        like("i.state", "state")
        like("i.city", "city")
        like("i.zip", "zip")
        like("i.industry", "industry")
        like("l.title", "job_title")
        if f.get("chain"):
            where.append("l.chain = ?")
            params.append(f["chain"])
        # Unknown holdings never satisfy a value filter (neither min nor max): they are not $0.
        if f.get("min_value") is not None:
            where.append("l.estimated_holdings_usd IS NOT NULL AND l.estimated_holdings_usd >= ?")
            params.append(f["min_value"])
        if f.get("max_value") is not None:
            where.append("l.estimated_holdings_usd IS NOT NULL AND l.estimated_holdings_usd <= ?")
            params.append(f["max_value"])
        if f.get("min_activity") is not None:
            where.append("l.recent_activity IS NOT NULL AND l.recent_activity >= ?")
            params.append(f["min_activity"])
        if f.get("min_assets") is not None:
            where.append("l.asset_count IS NOT NULL AND l.asset_count >= ?")
            params.append(f["min_assets"])
        if f.get("company_size_min") is not None:
            where.append("i.company_size IS NOT NULL AND i.company_size >= ?")
            params.append(f["company_size_min"])
        if f.get("company_size_max") is not None:
            where.append("i.company_size IS NOT NULL AND i.company_size <= ?")
            params.append(f["company_size_max"])
        if f.get("min_years_in_business") is not None:
            where.append("i.company_founded_year IS NOT NULL AND (CAST(strftime('%Y','now') AS INTEGER) - i.company_founded_year) >= ?")
            params.append(f["min_years_in_business"])
        if f.get("funding_interest"):
            where.append("l.funding_interest LIKE 'Observed%'")
        if f.get("min_score") is not None:
            where.append("l.lead_score >= ?")
            params.append(f["min_score"])
        if f.get("email_available"):
            where.append("l.email IS NOT NULL")
        if f.get("phone_available"):
            where.append("l.phone IS NOT NULL")
        if f.get("email_verified"):
            where.append("l.email_verification_status = 'Verified'")
        if f.get("keywords"):
            for word in str(f["keywords"]).lower().split():
                where.append("""LOWER(COALESCE(l.name,'')||' '||COALESCE(l.title,'')||' '||COALESCE(l.company,'')||' '||
                                COALESCE(i.industry,'')||' '||COALESCE(i.location_text,'')||' '||COALESCE(i.city,'')||' '||
                                COALESCE(i.state,'')||' '||COALESCE(i.country,'')||' '||COALESCE(i.ens_name,'')||' '||
                                l.wallet_address||' '||l.chain) LIKE ?""")
                params.append(f"%{word}%")
        sql = (f"SELECT l.* FROM leads l LEFT JOIN identities i ON i.firm_id=l.firm_id AND i.id=l.identity_id "
               f"WHERE {' AND '.join(where)} ORDER BY l.lead_score DESC, l.id DESC LIMIT ?")
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self.serialize_lead(r) for r in rows]

    def group_by_person(self, leads: list[dict]) -> list[dict]:
        """Contactable list shows each person once; their other wallets ride along."""
        seen: dict[int, dict] = {}
        out = []
        for lead in leads:
            ident = lead.get("identity_id")
            if ident and ident in seen:
                seen[ident].setdefault("other_wallets", []).append(
                    {"id": lead["id"], "chain": lead["chain"], "wallet_display": lead["wallet_display"]})
                continue
            if ident:
                seen[ident] = lead
            out.append(lead)
        return out

    def set_status(self, lead_id: int, status: str) -> dict | None:
        if status not in LEAD_STATUSES:
            raise ValueError("Invalid status")
        row = self._lead_row(lead_id)
        if not row:
            return None
        with self.tx():
            self.conn.execute("UPDATE leads SET status=?, updated_at=?, last_contacted_at=CASE WHEN ?='contacted' "
                              "THEN ? ELSE last_contacted_at END WHERE firm_id=? AND id=?",
                              (status, iso(), status, iso(), self.firm_id, lead_id))
            if status in ("suppressed", "do_not_contact", "deleted") and row["category"] == "contactable":
                reasons = _loads(row["opportunity_reasons_json"], []) + [f"Lead status: {status}"]
                self.conn.execute("UPDATE leads SET category='opportunity', opportunity_reasons_json=? "
                                  "WHERE firm_id=? AND id=?", (json.dumps(reasons), self.firm_id, lead_id))
            self.audit(STATUS_AUDIT.get(status, "lead_updated"), lead_id, f"status={status}")
        return self.get_lead(lead_id)

    # ---------------------------------------------------------- saved / CRM
    def save_lead(self, lead_id: int) -> tuple[dict | None, bool]:
        """Returns (saved_record, created). Duplicates (same lead, or same person) are not re-created."""
        detail = self.lead_detail(lead_id)
        if not detail:
            return None, False
        existing = self.conn.execute("SELECT * FROM saved_leads WHERE firm_id=? AND lead_id=?",
                                     (self.firm_id, lead_id)).fetchone()
        if not existing and detail.get("identity_id"):
            existing = self.conn.execute("SELECT * FROM saved_leads WHERE firm_id=? AND identity_id=?",
                                         (self.firm_id, detail["identity_id"])).fetchone()
        if existing:
            return self._saved_dict(existing), False
        snapshot = {k: detail.get(k) for k in (
            "name", "title", "company", "email", "phone", "linkedin", "wallet_address", "chain",
            "estimated_holdings_usd", "holdings_status", "recent_activity", "last_active_at", "asset_count",
            "identity_confidence", "wallet_attribution_confidence", "identity_source", "wallet_source",
            "contact_source", "email_verification_status", "lead_score", "score_class", "created_at")}
        snapshot["identity"] = detail.get("identity")
        snapshot["sources"] = detail.get("sources")
        snapshot["notes"] = detail.get("notes")
        now = iso()
        with self.tx():
            cur = self.conn.execute(
                """INSERT INTO saved_leads(firm_id, lead_id, identity_id, saved_by, crm_stage, snapshot_json,
                                           created_at, saved_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (self.firm_id, lead_id, detail.get("identity_id"), self.user_id, "saved",
                 json.dumps(snapshot), detail["created_at"], now, now))
            self.conn.execute("UPDATE leads SET status='saved', updated_at=? WHERE firm_id=? AND id=? AND status='new'",
                              (now, self.firm_id, lead_id))
            self.audit("lead_saved", lead_id)
        row = self.conn.execute("SELECT * FROM saved_leads WHERE firm_id=? AND id=?",
                                (self.firm_id, cur.lastrowid)).fetchone()
        return self._saved_dict(row), True

    def _saved_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d.pop("firm_id", None)
        d["snapshot"] = _loads(d.pop("snapshot_json"), {})
        lead = self.get_lead(d["lead_id"])
        d["lead"] = lead
        d["notes"] = self.list_notes(d["lead_id"])
        return d

    def list_saved(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM saved_leads WHERE firm_id=? ORDER BY saved_at DESC, id DESC",
                                 (self.firm_id,)).fetchall()
        return [self._saved_dict(r) for r in rows]

    def set_crm_stage(self, saved_id: int, stage: str) -> dict | None:
        if stage not in ("saved", "crm"):
            raise ValueError("Invalid CRM stage")
        row = self.conn.execute("SELECT * FROM saved_leads WHERE firm_id=? AND id=?", (self.firm_id, saved_id)).fetchone()
        if not row:
            return None
        with self.tx():
            self.conn.execute("UPDATE saved_leads SET crm_stage=?, updated_at=? WHERE firm_id=? AND id=?",
                              (stage, iso(), self.firm_id, saved_id))
            self.audit("lead_updated", row["lead_id"], f"crm_stage={stage}")
        return self._saved_dict(self.conn.execute("SELECT * FROM saved_leads WHERE firm_id=? AND id=?",
                                                  (self.firm_id, saved_id)).fetchone())

    # ---------------------------------------------------------------- notes
    def add_note(self, lead_id: int, body: str) -> dict | None:
        if not self.lead_exists(lead_id):
            return None
        with self.tx():
            cur = self.conn.execute("INSERT INTO notes(firm_id, lead_id, user_id, body, created_at) VALUES (?,?,?,?,?)",
                                    (self.firm_id, lead_id, self.user_id, body.strip()[:5000], iso()))
            self.audit("lead_updated", lead_id, "note_added")
        return dict(self.conn.execute("SELECT id, lead_id, body, created_at FROM notes WHERE firm_id=? AND id=?",
                                      (self.firm_id, cur.lastrowid)).fetchone())

    def list_notes(self, lead_id: int) -> list[dict]:
        rows = self.conn.execute(
            """SELECT n.id, n.body, n.created_at, u.email AS author FROM notes n
                 JOIN users u ON u.firm_id=n.firm_id AND u.id=n.user_id
                WHERE n.firm_id=? AND n.lead_id=? ORDER BY n.id""", (self.firm_id, lead_id)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------- searches
    def create_search(self, query: str, filters: dict, cache_key: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO searches(firm_id, user_id, query, filters_json, cache_key, status, created_at) VALUES (?,?,?,?,?,?,?)",
            (self.firm_id, self.user_id, query, json.dumps(filters, sort_keys=True), cache_key, "running", iso()))
        return int(cur.lastrowid)

    def finish_search(self, search_id: int, counts: dict, report: dict, status: str = "completed") -> None:
        self.conn.execute(
            """UPDATE searches SET status=?, discovered=?, qualified=?, identified=?, contactable=?, unattributed=?,
                      failed=?, reused=?, provider_report_json=?, completed_at=? WHERE firm_id=? AND id=?""",
            (status, counts.get("discovered", 0), counts.get("qualified", 0), counts.get("identified", 0),
             counts.get("contactable", 0), counts.get("unattributed", 0), counts.get("failed", 0),
             counts.get("reused", 0), json.dumps(report), iso(), self.firm_id, search_id))

    def add_search_result(self, search_id: int, lead_id: int, origin: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO search_results(firm_id, search_id, lead_id, origin) VALUES (?,?,?,?)",
                          (self.firm_id, search_id, lead_id, origin))

    def search_lead_ids(self, search_id: int) -> list[int]:
        return [r[0] for r in self.conn.execute(
            "SELECT lead_id FROM search_results WHERE firm_id=? AND search_id=? ORDER BY origin, lead_id",
            (self.firm_id, search_id)).fetchall()]

    def get_search(self, search_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM searches WHERE firm_id=? AND id=?", (self.firm_id, search_id)).fetchone()
        return self._search_dict(row) if row else None

    def _search_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d.pop("firm_id", None)
        d["filters"] = _loads(d.pop("filters_json"), {})
        d["provider_report"] = _loads(d.pop("provider_report_json"), {})
        return d

    def list_searches(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM searches WHERE firm_id=? ORDER BY id DESC LIMIT ?",
                                 (self.firm_id, limit)).fetchall()
        return [self._search_dict(r) for r in rows]

    def reusable_leads(self, cache_key: str) -> list[int]:
        """Leads from earlier runs of the same search that are still untouched:
        status 'new', no notes, never contacted."""
        rows = self.conn.execute(
            """SELECT DISTINCT l.id, l.lead_score FROM leads l
                 JOIN search_results sr ON sr.firm_id=l.firm_id AND sr.lead_id=l.id
                 JOIN searches s ON s.firm_id=sr.firm_id AND s.id=sr.search_id
                WHERE l.firm_id=? AND s.cache_key=? AND l.status='new' AND l.last_contacted_at IS NULL
                  AND NOT EXISTS (SELECT 1 FROM notes n WHERE n.firm_id=l.firm_id AND n.lead_id=l.id)
                ORDER BY l.lead_score DESC""", (self.firm_id, cache_key)).fetchall()
        return [r["id"] for r in rows]

    # ------------------------------------------------------------- pipeline
    def pipeline_counts(self) -> dict:
        q = lambda sql: self.conn.execute(sql, (self.firm_id,)).fetchone()[0]  # noqa: E731
        live = "firm_id=? AND status<>'deleted'"
        return {
            "discovered": q(f"SELECT COUNT(*) FROM leads WHERE {live}"),
            "qualified": q(f"SELECT COUNT(*) FROM leads WHERE {live} AND stage IN ('qualified','identified','contactable')"),
            "identified": q(f"SELECT COUNT(*) FROM leads WHERE {live} AND stage IN ('identified','contactable')"),
            "contactable": q(f"SELECT COUNT(*) FROM leads WHERE {live} AND category='contactable'"),
            "unattributed": q(f"SELECT COUNT(*) FROM leads WHERE {live} AND stage IN ('qualified') "
                              "AND wallet_attribution_confidence IN ('None','Low')"),
            "opportunities": q(f"SELECT COUNT(*) FROM leads WHERE {live} AND category='opportunity'"),
            "saved": q("SELECT COUNT(*) FROM saved_leads WHERE firm_id=?"),
            "crm": q("SELECT COUNT(*) FROM saved_leads WHERE firm_id=? AND crm_stage='crm'"),
        }
