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
        # Deliberately far future. The real lock is 2026-08-21T19:00:00Z, and
        # pinning tests to it made every "before the lock" case pass only until
        # that instant and fail for ever after -- a test suite with an expiry
        # date. Post-lock behaviour is tested by constructing a past lock
        # explicitly, so both sides are covered without consulting the clock.
        prediction_lock="2099-01-01T00:00:00Z",
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
async def future_cache(
    bootstrap: dict[str, Any],
    fixtures_payload: list[dict[str, Any]],
    league_payload: dict[str, Any],
) -> MemoryCache:
    """A cache whose fixtures have not kicked off yet, whenever the tests run.

    The captured payload is real, so its kickoffs are real dates that stop being
    in the future the moment the season starts. Shifting them by a year keeps
    "before kick-off" tests meaningful for ever instead of turning them into
    failures the first time somebody runs the suite after 19:00 on 21 August.
    """
    from datetime import datetime, timedelta

    shifted: list[dict[str, Any]] = []
    for row in fixtures_payload:
        copy = dict(row)
        raw = copy.get("kickoff_time")
        if raw:
            moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            copy["kickoff_time"] = (moment + timedelta(days=365)).isoformat().replace("+00:00", "Z")
        copy["started"] = False
        copy["finished"] = False
        shifted.append(copy)

    store = MemoryCache()
    await store.set(keys.FPL_BOOTSTRAP, bootstrap, source="fpl")
    await store.set(keys.FPL_FIXTURES, shifted, source="fpl")
    await store.set(keys.FPL_LEAGUE, league_payload, source="fpl")
    return store


@pytest.fixture
async def future_client(
    settings: Settings, future_cache: MemoryCache, sessions: Any
) -> AsyncIterator[AsyncClient]:
    """A client whose fixtures are all still to come."""
    app = _build_app(settings, future_cache, sessions)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://api.test") as http:
        yield http


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
async def empty_db() -> AsyncIterator[Any]:
    """Schema, but no people and no predictions -- the pre-seed state."""
    from shared.db import Base
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite://", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


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
