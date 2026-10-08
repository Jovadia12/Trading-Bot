"""HTTP API + static UI for the Lead Finder."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import security
from .chains import CHAINS
from .config import Settings
from .db import connect, init_db
from .pipeline import LeadPipeline, ProviderStatusStore, Providers, parse_query
from .providers.base import CONFIGURED_UNCHECKED, CONNECTED, NOT_CONFIGURED, ProviderError
from .providers.enrichment import ApolloClient, HunterClient
from .providers.ens import EnsResolver
from .providers.nansen import NansenClient
from .providers.profiles import GithubClient, WebsiteChecker
from .tenancy import FirmRepository

STATIC = Path(__file__).parent / "static"
COOKIE = "lf_session"
CSRF_HEADER = "x-requested-with"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")   # a client-sent firm_id is rejected, never trusted


class LoginIn(Strict):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class Filters(Strict):
    country: str | None = Field(None, max_length=80)
    state: str | None = Field(None, max_length=80)
    city: str | None = Field(None, max_length=80)
    zip: str | None = Field(None, max_length=20)
    chain: str | None = Field(None, max_length=20)
    min_value: float | None = Field(None, ge=0)
    max_value: float | None = Field(None, ge=0)
    min_activity: int | None = Field(None, ge=0)
    min_assets: int | None = Field(None, ge=0)
    industry: str | None = Field(None, max_length=80)
    job_title: str | None = Field(None, max_length=80)
    company_size_min: int | None = Field(None, ge=0)
    company_size_max: int | None = Field(None, ge=0)
    min_years_in_business: int | None = Field(None, ge=0)
    funding_interest: bool | None = None
    min_score: int | None = Field(None, ge=0, le=100)
    email_available: bool | None = None
    phone_available: bool | None = None
    email_verified: bool | None = None
    keywords: str | None = Field(None, max_length=200)
    max_candidates: int | None = Field(None, ge=1, le=200)

    def clean(self) -> dict:
        d = {k: v for k, v in self.model_dump().items() if v is not None and v != "" and v is not False}
        if d.get("chain") and d["chain"] not in CHAINS:
            raise HTTPException(422, "Unknown chain")
        return d


class SearchIn(Strict):
    query: str = Field("", max_length=500)
    filters: Filters = Field(default_factory=Filters)


class StatusIn(Strict):
    status: Literal["new", "contacted", "suppressed", "do_not_contact"]


class NoteIn(Strict):
    body: str = Field(min_length=1, max_length=5000)


class CrmIn(Strict):
    crm_stage: Literal["saved", "crm"]


def build_providers(settings: Settings, http: httpx.Client) -> Providers:
    return Providers(
        wallet=NansenClient(settings.nansen_api_key, settings.nansen_base_url, http),
        ens=EnsResolver(settings.eth_rpc_url, http),
        github=GithubClient(settings.github_base_url, settings.github_token, http),
        website=WebsiteChecker(settings.fetch_websites, http),
        apollo=ApolloClient(settings.apollo_api_key, settings.apollo_base_url, http),
        hunter=HunterClient(settings.hunter_api_key, settings.hunter_base_url, http),
    )


def create_app(settings: Settings | None = None, http: httpx.Client | None = None,
               providers: Providers | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    http = http or httpx.Client(timeout=settings.http_timeout, headers={"User-Agent": "LeadFinder/1.0"})
    providers = providers or build_providers(settings, http)
    boot = connect(settings.db_path)
    init_db(boot)
    boot.close()

    app = FastAPI(title="Lead Finder", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.providers = providers

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # CSRF: state-changing API calls must come from our own JS (custom header + SameSite cookie).
        if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get(CSRF_HEADER) != "LeadFinder":
                return JSONResponse({"detail": "Missing CSRF header"}, status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' data:; frame-ancestors 'none'")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def db() -> Iterator[sqlite3.Connection]:
        conn = connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def auth(request: Request, conn: sqlite3.Connection = Depends(db)) -> security.AuthContext:
        ctx = security.resolve_session(conn, request.cookies.get(COOKIE))
        if ctx is None:
            raise HTTPException(401, "Not authenticated")
        return ctx

    def repo(ctx: security.AuthContext = Depends(auth), conn: sqlite3.Connection = Depends(db)) -> FirmRepository:
        return FirmRepository(conn, ctx)

    # ------------------------------------------------------------------ auth
    @app.post("/api/auth/login")
    def login(body: LoginIn, response: Response, conn: sqlite3.Connection = Depends(db)):
        user_id = security.authenticate(conn, body.email, body.password)
        if user_id is None:
            raise HTTPException(401, "Invalid email or password")
        token = security.create_session(conn, user_id, settings.session_ttl_hours)
        response.set_cookie(COOKIE, token, httponly=True, secure=settings.cookie_secure, samesite="strict",
                            max_age=settings.session_ttl_hours * 3600, path="/")
        return {"ok": True}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, conn: sqlite3.Connection = Depends(db)):
        if token := request.cookies.get(COOKIE):
            security.destroy_session(conn, token)
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/me")
    def me(ctx: security.AuthContext = Depends(auth)):
        return {"email": ctx.email, "name": ctx.name, "firm": ctx.firm_name}

    # ------------------------------------------------------------- providers
    def provider_view(conn: sqlite3.Connection) -> dict:
        store = ProviderStatusStore(conn)
        recorded = store.all()
        out = []
        for p in providers.all():
            rec = recorded.get(p.name)
            if not p.configured:
                status, message, checked = NOT_CONFIGURED, None, None
            elif rec:
                status, message, checked = rec["status"], rec["message"], rec["checked_at"]
                if status == NOT_CONFIGURED:      # key was added since the last run
                    status, message, checked = CONFIGURED_UNCHECKED, None, None
            else:
                status, message, checked = CONFIGURED_UNCHECKED, None, None
            out.append({"provider": p.name, "status": status, "message": message, "checked_at": checked,
                        "configured": p.configured})
        verified = store.verified_chains(providers.wallet.name)
        return {"providers": out,
                "chains": [{"key": c, "name": CHAINS[c].name} for c in verified],
                "provider_chains": [{"key": c.key, "name": c.name} for c in CHAINS.values()]}

    @app.get("/api/providers")
    def get_providers(_: security.AuthContext = Depends(auth), conn: sqlite3.Connection = Depends(db)):
        return provider_view(conn)

    @app.post("/api/providers/check")
    def check_providers(_: security.AuthContext = Depends(auth), conn: sqlite3.Connection = Depends(db)):
        """Free health checks only. Nansen has no free endpoint, so its status is the last real call's outcome."""
        store = ProviderStatusStore(conn)
        if providers.hunter.configured:
            try:
                providers.hunter.account()
                store.record(providers.hunter.name, CONNECTED)
            except ProviderError as exc:
                store.record(providers.hunter.name, exc.status, exc.message)
        if providers.ens.configured:
            try:
                providers.ens._rpc("eth_blockNumber", [])
                store.record(providers.ens.name, CONNECTED)
            except ProviderError as exc:
                store.record(providers.ens.name, exc.status, exc.message)
        return provider_view(conn)

    # ---------------------------------------------------------------- search
    def results_for(r: FirmRepository, search_id: int, filters: dict, query: str) -> dict:
        ids = r.search_lead_ids(search_id)
        origin = {row["lead_id"]: row["origin"] for row in r.conn.execute(
            "SELECT lead_id, origin FROM search_results WHERE firm_id=? AND search_id=?", (r.firm_id, search_id))}
        list_filters = dict(filters)
        kw = parse_query(query, filters.get("chain")).keywords
        if kw:
            list_filters["keywords"] = " ".join(kw + ([filters["keywords"]] if filters.get("keywords") else []))
        # Crypto qualification filters were applied during the run; wallets that failed them
        # are shown as opportunities with the reason instead of disappearing.
        for k in ("max_candidates", "min_value", "max_value", "min_activity", "min_assets"):
            list_filters.pop(k, None)
        rank = lambda l: (origin.get(l["id"]) != "cached", -l["lead_score"])  # noqa: E731
        contactable = sorted(r.list_leads(category="contactable", filters=list_filters, lead_ids=ids), key=rank)
        opportunities = sorted(r.list_leads(category="opportunity", filters=list_filters, lead_ids=ids), key=rank)
        for l in contactable + opportunities:
            l["origin"] = origin.get(l["id"])
        return {"contactable": r.group_by_person(contactable), "opportunities": opportunities}

    @app.post("/api/searches")
    def run_search(body: SearchIn, r: FirmRepository = Depends(repo)):
        filters = body.filters.clean()
        pipeline = LeadPipeline(r, providers, ProviderStatusStore(r.conn), settings)
        outcome = pipeline.run_search(body.query.strip(), filters)
        search = r.get_search(outcome["search_id"])
        return {"search": search, **results_for(r, search["id"], filters, body.query)}

    @app.get("/api/searches")
    def list_searches(r: FirmRepository = Depends(repo)):
        return {"searches": r.list_searches()}

    @app.get("/api/searches/{search_id}")
    def get_search(search_id: int, r: FirmRepository = Depends(repo)):
        search = r.get_search(search_id)
        if not search:
            raise HTTPException(404, "Search not found")
        return {"search": search, **results_for(r, search_id, search["filters"], search["query"])}

    @app.post("/api/searches/{search_id}/rerun")
    def rerun_search(search_id: int, r: FirmRepository = Depends(repo)):
        prev = r.get_search(search_id)
        if not prev:
            raise HTTPException(404, "Search not found")
        pipeline = LeadPipeline(r, providers, ProviderStatusStore(r.conn), settings)
        outcome = pipeline.run_search(prev["query"], prev["filters"])
        search = r.get_search(outcome["search_id"])
        return {"search": search, **results_for(r, search["id"], prev["filters"], prev["query"])}

    # ----------------------------------------------------------------- leads
    @app.get("/api/leads")
    def list_leads(request: Request, category: Literal["contactable", "opportunity"] = "contactable",
                   r: FirmRepository = Depends(repo)):
        raw = dict(request.query_params)
        raw.pop("category", None)
        if "firm_id" in raw:
            raise HTTPException(422, "firm_id is not accepted")
        try:
            filters = Filters(**{k: v for k, v in raw.items() if v != ""}).clean()
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        leads = r.list_leads(category=category, filters=filters)
        return {"leads": r.group_by_person(leads) if category == "contactable" else leads}

    @app.get("/api/leads/{lead_id}")
    def lead_detail(lead_id: int, r: FirmRepository = Depends(repo)):
        detail = r.lead_detail(lead_id)
        if not detail:
            raise HTTPException(404, "Lead not found")
        r.audit("lead_viewed", lead_id)
        return detail

    @app.post("/api/leads/{lead_id}/save")
    def save_lead(lead_id: int, r: FirmRepository = Depends(repo)):
        lead = r.get_lead(lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        if lead["status"] in ("suppressed", "do_not_contact", "deleted"):
            raise HTTPException(409, f"Lead is {lead['status']}")
        saved, created = r.save_lead(lead_id)
        return {"saved": saved, "created": created}

    @app.patch("/api/leads/{lead_id}")
    def update_lead(lead_id: int, body: StatusIn, r: FirmRepository = Depends(repo)):
        lead = r.set_status(lead_id, body.status)
        if not lead:
            raise HTTPException(404, "Lead not found")
        return lead

    @app.delete("/api/leads/{lead_id}")
    def delete_lead(lead_id: int, r: FirmRepository = Depends(repo)):
        if not r.set_status(lead_id, "deleted"):
            raise HTTPException(404, "Lead not found")
        return {"ok": True}

    @app.get("/api/leads/{lead_id}/notes")
    def list_notes(lead_id: int, r: FirmRepository = Depends(repo)):
        if not r.lead_exists(lead_id):
            raise HTTPException(404, "Lead not found")
        return {"notes": r.list_notes(lead_id)}

    @app.post("/api/leads/{lead_id}/notes")
    def add_note(lead_id: int, body: NoteIn, r: FirmRepository = Depends(repo)):
        note = r.add_note(lead_id, body.body)
        if not note:
            raise HTTPException(404, "Lead not found")
        return note

    # ------------------------------------------------------------ saved / CRM
    @app.get("/api/saved")
    def list_saved(r: FirmRepository = Depends(repo)):
        return {"saved": r.list_saved()}

    @app.patch("/api/saved/{saved_id}")
    def update_saved(saved_id: int, body: CrmIn, r: FirmRepository = Depends(repo)):
        saved = r.set_crm_stage(saved_id, body.crm_stage)
        if not saved:
            raise HTTPException(404, "Saved lead not found")
        return saved

    @app.get("/api/pipeline")
    def pipeline_counts(r: FirmRepository = Depends(repo)):
        return r.pipeline_counts()

    @app.get("/api/audit")
    def audit(r: FirmRepository = Depends(repo)):
        return {"entries": r.audit_log()}

    # -------------------------------------------------------------------- UI
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app
