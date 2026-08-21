"""Test fixtures: the real app, wired to a cache pre-filled with real payloads.

The JSON under ``tests/data`` is genuine output captured from the FPL API on
2026-08-21, so the tests exercise the shapes production actually receives --
including the ones that only occur before a season starts, which is exactly the
state this app launches in.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from services.api.deps import AppState
from shared import keys
from shared.cache import MemoryCache
from shared.config import Settings

DATA = pathlib.Path(__file__).parent / "data"

CODES = {
    "coyg": "test-code-coyg",
    "aure": "test-code-aure",
    "twzt": "test-code-twzt",
    "bulba": "test-code-bulba",
}


def load(name: str) -> Any:
    return json.loads((DATA / name).read_text())


@pytest.fixture
def bootstrap() -> dict[str, Any]:
    data = load("fpl_bootstrap_slim.json")
    assert isinstance(data, dict)
    return data


@pytest.fixture
def fixtures_payload() -> list[dict[str, Any]]:
    data = load("fpl_fixtures.json")
    assert isinstance(data, list)
    return data


@pytest.fixture
def league_payload() -> dict[str, Any]:
    data = load("fpl_league.json")
    assert isinstance(data, dict)
    return data


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="local",
        session_secret="test-secret-long-enough-for-signing-abcdefghijk",
        code_coyg=CODES["coyg"],
        code_aure=CODES["aure"],
        code_twzt=CODES["twzt"],
        code_bulba=CODES["bulba"],
        frontend_origin="http://localhost:5173",
        prediction_lock="2026-08-21T19:00:00Z",
    )


@pytest.fixture
async def cache(
    bootstrap: dict[str, Any],
    fixtures_payload: list[dict[str, Any]],
    league_payload: dict[str, Any],
) -> MemoryCache:
    store = MemoryCache()
    await store.set(keys.FPL_BOOTSTRAP, bootstrap, source="fpl")
    await store.set(keys.FPL_FIXTURES, fixtures_payload, source="fpl")
    await store.set(keys.FPL_LEAGUE, league_payload, source="fpl")
    return store


@pytest.fixture
async def empty_cache() -> MemoryCache:
    """A cache the poller has never written to -- the cold-start state."""
    return MemoryCache()


def _build_app(settings: Settings, store: MemoryCache, sessions: Any = None) -> Any:
    from services.api.main import create_app

    app = create_app()
    # Replace the lifespan's state so tests need neither Redis nor network.
    app.router.lifespan_context = _noop_lifespan  # type: ignore[assignment]
    app.state.app_state = AppState(settings=settings, cache=store, sessions=sessions)
    return app


@pytest.fixture
async def sessions() -> AsyncIterator[Any]:
    """A real SQLite schema per test, so persistence is genuinely exercised.

    In-memory would be simpler but would not catch a migration-shaped bug; this
    creates the actual tables from the same metadata Alembic generates from.
    """
    from shared.db import Base
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite://", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)

    # Seed exactly as the api's lifespan does.
    from services.api.repository import seed_predictions

    async with factory() as db:
        await seed_predictions(db)
        await db.commit()

    yield factory
    await engine.dispose()


@asynccontextmanager
async def _noop_lifespan(app: Any) -> AsyncIterator[None]:
    """Skip the real lifespan: tests supply their own cache and need no network."""
    yield


@pytest.fixture
async def client(settings: Settings, cache: MemoryCache, sessions: Any) -> AsyncIterator[AsyncClient]:
    app = _build_app(settings, cache, sessions)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://api.test") as http:
        yield http


@pytest.fixture
async def cold_client(
    settings: Settings, empty_cache: MemoryCache, sessions: Any
) -> AsyncIterator[AsyncClient]:
    """A client whose cache the poller has never filled."""
    app = _build_app(settings, empty_cache, sessions)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://api.test") as http:
        yield http


async def sign_in(http: AsyncClient, person: str = "coyg") -> None:
    response = await http.post("/api/session", json={"code": CODES[person]})
    assert response.status_code == 200, response.text
