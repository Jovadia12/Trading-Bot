import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from lead_finder import security
from lead_finder.api import create_app
from lead_finder.config import Settings
from lead_finder.db import connect, init_db
from lead_finder.pipeline import Providers
from lead_finder.providers.enrichment import ApolloClient, HunterClient
from lead_finder.providers.ens import EnsResolver
from lead_finder.providers.nansen import NansenClient
from lead_finder.providers.profiles import GithubClient, WebsiteChecker

from .fakes import WETH, build_world

H = {"X-Requested-With": "LeadFinder"}
PASSWORD = "correct-horse-battery"


def make_providers(world, *, nansen=True, rpc=True, apollo=True, hunter=True) -> Providers:
    http = httpx.Client(transport=httpx.MockTransport(world.handler))
    return Providers(
        wallet=NansenClient("test-nansen-key" if nansen else None, "https://api.nansen.test", http),
        ens=EnsResolver("https://rpc.test" if rpc else None, http),
        github=GithubClient("https://api.github.test", None, http),
        website=WebsiteChecker(True, http, resolver=lambda host: True),
        apollo=ApolloClient("test-apollo" if apollo else None, "https://api.apollo.test", http),
        hunter=HunterClient("test-hunter" if hunter else None, "https://api.hunter.test", http),
    )


@pytest.fixture
def world():
    return build_world()


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.db_path = str(tmp_path / "lf.db")
    s.cookie_secure = False
    s.seed_tokens = {"ethereum": [WETH]}
    return s


@pytest.fixture
def firms(settings):
    conn = connect(settings.db_path)
    init_db(conn)
    a = security.create_firm(conn, "Firm A")
    b = security.create_firm(conn, "Firm B")
    security.create_user(conn, a, "a@firm-a.test", PASSWORD, "Analyst A")
    security.create_user(conn, b, "b@firm-b.test", PASSWORD, "Analyst B")
    conn.close()
    return {"a": a, "b": b}


def login(client: TestClient, email: str) -> TestClient:
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}, headers=H)
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def make_client(settings, firms):
    def _make(world, email="a@firm-a.test", **flags):
        app = create_app(settings, providers=make_providers(world, **flags))
        return login(TestClient(app), email)
    return _make


def db(settings) -> sqlite3.Connection:
    return connect(settings.db_path)
