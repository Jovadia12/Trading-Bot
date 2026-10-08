"""SQLite schema.

Tenant isolation is enforced in the schema, not only in queries: every
firm-owned table carries ``firm_id`` and references its parents through
composite ``(firm_id, id)`` foreign keys, so a row of one firm can never point
at a row of another firm. All reads/writes go through ``tenancy.FirmRepository``
which binds ``firm_id`` from the authenticated session.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS firms (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

-- Users authenticate with email + password only. There is deliberately no
-- wallet column: wallets are lead data and never an identity for login.
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    firm_id       INTEGER NOT NULL REFERENCES firms(id),
    email         TEXT NOT NULL UNIQUE,
    name          TEXT,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'member',
    created_at    TEXT NOT NULL,
    UNIQUE (firm_id, id)
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wallets (
    id                        INTEGER PRIMARY KEY,
    firm_id                   INTEGER NOT NULL REFERENCES firms(id),
    chain                     TEXT NOT NULL,
    address                   TEXT NOT NULL,          -- normalized for dedup
    display_address           TEXT NOT NULL,
    estimated_portfolio_value REAL,                   -- NULL = unknown, never 0
    holdings_status           TEXT NOT NULL,          -- 'known' | 'Holdings unavailable'
    native_balance            REAL,
    native_symbol             TEXT,
    asset_count               INTEGER,
    token_holdings_json       TEXT,
    recent_activity_count     INTEGER,                -- trades in activity window; NULL = unknown
    last_active_at            TEXT,
    activity_json             TEXT,
    debt_positions_json       TEXT,
    provider_labels_json      TEXT,
    is_contract               INTEGER,                -- NULL = unknown
    source                    TEXT NOT NULL,
    provider_status           TEXT,
    discovered_at             TEXT NOT NULL,
    updated_at                TEXT NOT NULL,
    UNIQUE (firm_id, chain, address),
    UNIQUE (firm_id, id)
);

CREATE TABLE IF NOT EXISTS identities (
    id                    INTEGER PRIMARY KEY,
    firm_id               INTEGER NOT NULL REFERENCES firms(id),
    full_name             TEXT,
    name_key              TEXT,                       -- normalized name for dedup
    company               TEXT,
    company_key           TEXT,
    title                 TEXT,
    linkedin              TEXT,
    city                  TEXT,
    state                 TEXT,
    country               TEXT,
    zip                   TEXT,
    location_text         TEXT,
    industry              TEXT,
    company_size          INTEGER,
    company_founded_year  INTEGER,
    company_domain        TEXT,
    ens_name              TEXT,
    github_login          TEXT,
    website               TEXT,
    classification        TEXT NOT NULL,              -- individual | entity | uncertain
    classification_reasons_json TEXT,
    identity_confidence   TEXT NOT NULL,              -- High | Medium | Low | None
    identity_source       TEXT,
    public_prominence     TEXT NOT NULL,              -- High | Medium | Low | Unknown
    prominence_reasons_json TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    UNIQUE (firm_id, id)
);
CREATE INDEX IF NOT EXISTS ix_identities_name_company ON identities(firm_id, name_key, company_key);

CREATE TABLE IF NOT EXISTS contacts (
    id                  INTEGER PRIMARY KEY,
    firm_id             INTEGER NOT NULL,
    identity_id         INTEGER NOT NULL,
    kind                TEXT NOT NULL CHECK (kind IN ('email','phone','linkedin')),
    value               TEXT NOT NULL,
    source              TEXT NOT NULL,
    self_published      INTEGER NOT NULL DEFAULT 0,  -- published by the wallet owner
    verification_status TEXT NOT NULL,               -- Verified | Risky | Invalid | Unverified | Self-published
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE (firm_id, kind, value),
    FOREIGN KEY (firm_id, identity_id) REFERENCES identities(firm_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS leads (
    id                            INTEGER PRIMARY KEY,
    firm_id                       INTEGER NOT NULL,
    wallet_id                     INTEGER NOT NULL,
    identity_id                   INTEGER,
    name                          TEXT,
    title                         TEXT,
    company                       TEXT,
    email                         TEXT,
    phone                         TEXT,
    linkedin                      TEXT,
    wallet_address                TEXT NOT NULL,
    chain                         TEXT NOT NULL,
    estimated_holdings_usd        REAL,
    holdings_status               TEXT NOT NULL,
    recent_activity               INTEGER,
    last_active_at                TEXT,
    asset_count                   INTEGER,
    identity_confidence           TEXT NOT NULL DEFAULT 'None',
    wallet_attribution_confidence TEXT NOT NULL DEFAULT 'None',
    identity_source               TEXT,
    wallet_source                 TEXT,
    contact_source                TEXT,
    email_verification_status     TEXT,
    public_prominence             TEXT NOT NULL DEFAULT 'Unknown',
    classification                TEXT NOT NULL DEFAULT 'uncertain',
    funding_interest              TEXT NOT NULL DEFAULT 'Unknown',
    apollo_status                 TEXT,
    hunter_status                 TEXT,
    stage                         TEXT NOT NULL,      -- discovered|qualified|identified|contactable
    category                      TEXT NOT NULL,      -- contactable | opportunity
    opportunity_reasons_json      TEXT,
    lead_score                    INTEGER NOT NULL DEFAULT 0,
    score_class                   TEXT NOT NULL DEFAULT 'Low',
    status                        TEXT NOT NULL DEFAULT 'new',  -- new|saved|contacted|suppressed|do_not_contact|deleted
    last_contacted_at             TEXT,
    created_at                    TEXT NOT NULL,
    updated_at                    TEXT NOT NULL,
    UNIQUE (firm_id, wallet_id),
    UNIQUE (firm_id, id),
    FOREIGN KEY (firm_id, wallet_id) REFERENCES wallets(firm_id, id),
    FOREIGN KEY (firm_id, identity_id) REFERENCES identities(firm_id, id)
);
CREATE INDEX IF NOT EXISTS ix_leads_firm_cat ON leads(firm_id, category, lead_score DESC);

CREATE TABLE IF NOT EXISTS lead_scores (
    id             INTEGER PRIMARY KEY,
    firm_id        INTEGER NOT NULL,
    lead_id        INTEGER NOT NULL,
    score          INTEGER NOT NULL,
    score_class    TEXT NOT NULL,
    breakdown_json TEXT NOT NULL,
    computed_at    TEXT NOT NULL,
    FOREIGN KEY (firm_id, lead_id) REFERENCES leads(firm_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lead_sources (
    id          INTEGER PRIMARY KEY,
    firm_id     INTEGER NOT NULL,
    lead_id     INTEGER NOT NULL,
    kind        TEXT NOT NULL,     -- wallet | attribution | identity | contact | classification
    provider    TEXT NOT NULL,
    url         TEXT,
    detail      TEXT,
    observed_at TEXT NOT NULL,
    UNIQUE (firm_id, lead_id, kind, provider, url, detail),
    FOREIGN KEY (firm_id, lead_id) REFERENCES leads(firm_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS searches (
    id                INTEGER PRIMARY KEY,
    firm_id           INTEGER NOT NULL,
    user_id           INTEGER NOT NULL,
    query             TEXT NOT NULL,
    filters_json      TEXT NOT NULL,
    cache_key         TEXT NOT NULL,
    status            TEXT NOT NULL,
    discovered        INTEGER NOT NULL DEFAULT 0,
    qualified         INTEGER NOT NULL DEFAULT 0,
    identified        INTEGER NOT NULL DEFAULT 0,
    contactable       INTEGER NOT NULL DEFAULT 0,
    unattributed      INTEGER NOT NULL DEFAULT 0,
    failed            INTEGER NOT NULL DEFAULT 0,
    reused            INTEGER NOT NULL DEFAULT 0,
    provider_report_json TEXT,
    created_at        TEXT NOT NULL,
    completed_at      TEXT,
    UNIQUE (firm_id, id),
    FOREIGN KEY (firm_id, user_id) REFERENCES users(firm_id, id)
);

CREATE TABLE IF NOT EXISTS search_results (
    firm_id    INTEGER NOT NULL,
    search_id  INTEGER NOT NULL,
    lead_id    INTEGER NOT NULL,
    origin     TEXT NOT NULL,   -- 'cached' | 'fresh'
    PRIMARY KEY (firm_id, search_id, lead_id),
    FOREIGN KEY (firm_id, search_id) REFERENCES searches(firm_id, id) ON DELETE CASCADE,
    FOREIGN KEY (firm_id, lead_id) REFERENCES leads(firm_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS saved_leads (
    id            INTEGER PRIMARY KEY,
    firm_id       INTEGER NOT NULL,
    lead_id       INTEGER NOT NULL,
    identity_id   INTEGER,
    saved_by      INTEGER NOT NULL,
    crm_stage     TEXT NOT NULL DEFAULT 'saved',   -- saved | crm
    snapshot_json TEXT NOT NULL,
    created_at    TEXT NOT NULL,                   -- when the lead was first created
    saved_at      TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (firm_id, lead_id),
    FOREIGN KEY (firm_id, lead_id) REFERENCES leads(firm_id, id),
    FOREIGN KEY (firm_id, saved_by) REFERENCES users(firm_id, id)
);

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY,
    firm_id    INTEGER NOT NULL,
    lead_id    INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (firm_id, lead_id) REFERENCES leads(firm_id, id) ON DELETE CASCADE,
    FOREIGN KEY (firm_id, user_id) REFERENCES users(firm_id, id)
);

-- Provider health is server configuration, not tenant data; it contains no lead data.
CREATE TABLE IF NOT EXISTS provider_status (
    provider   TEXT PRIMARY KEY,
    status     TEXT NOT NULL,
    message    TEXT,
    checked_at TEXT NOT NULL
);

-- Chains the wallet provider has actually returned valid data for.
CREATE TABLE IF NOT EXISTS provider_chain_support (
    provider        TEXT NOT NULL,
    chain           TEXT NOT NULL,
    last_success_at TEXT,
    last_error      TEXT,
    last_error_at   TEXT,
    PRIMARY KEY (provider, chain)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY,
    firm_id    INTEGER NOT NULL REFERENCES firms(id),
    user_id    INTEGER,
    action     TEXT NOT NULL,
    lead_id    INTEGER,
    detail     TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_firm ON audit_log(firm_id, created_at);
"""


def connect(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL") if db_path != ":memory:" else None
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
