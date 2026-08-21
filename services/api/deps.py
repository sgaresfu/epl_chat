"""Application state and FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Annotated, Any

import structlog
from fastapi import Depends, HTTPException, Request, status
from shared.cache import Cache, Entry
from shared.config import Settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.api.auth import Session, read_session

log = structlog.get_logger(__name__)


@dataclass
class AppState:
    """Everything the api holds for its lifetime."""

    settings: Settings
    cache: Cache
    # Set in the lifespan. Predictions and the watch log persist here rather
    # than in memory, because Render restarts a service on every deploy and an
    # in-memory prediction is one that disappears.
    sessions: async_sessionmaker[AsyncSession] | None = None
    # Presence heartbeats: person -> (fixture_id, last_seen_epoch)
    presence: dict[str, tuple[int, float]] = field(default_factory=dict)
    # Live SSE connections per person, for the concurrency cap.
    streams: dict[str, int] = field(default_factory=dict)


def get_state(request: Request) -> AppState:
    state = getattr(request.app.state, "app_state", None)
    if state is None:  # pragma: no cover - set in the lifespan
        raise RuntimeError("app state not initialised")
    assert isinstance(state, AppState)
    return state


State = Annotated[AppState, Depends(get_state)]


def get_config(state: State) -> Settings:
    return state.settings


Config = Annotated[Settings, Depends(get_config)]


def current_session(request: Request, state: State) -> Session:
    """Resolve the logged-in person, or 401.

    Every route except login depends on this, and every mutation resolves the
    person from here rather than from anything the client sent.
    """
    session = read_session(request, state.settings)
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sign in with your code word.")
    return session


CurrentSession = Annotated[Session, Depends(current_session)]


def optional_session(request: Request, state: State) -> Session | None:
    return read_session(request, state.settings)


OptionalSession = Annotated[Session | None, Depends(optional_session)]


async def get_db(state: State) -> AsyncIterator[AsyncSession]:
    """A transactional database session for one request.

    Commits when the handler returns, rolls back if it raises, so a failed
    mutation never leaves a half-written prediction behind.
    """
    factory = state.sessions
    if factory is None:  # pragma: no cover - set in the lifespan
        raise RuntimeError("database not initialised")
    async with factory() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


Db = Annotated[AsyncSession, Depends(get_db)]


async def cached(state: AppState, name: str) -> Entry | None:
    return await state.cache.get(name)


async def cached_value(state: AppState, name: str, default: Any = None) -> Any:
    entry = await state.cache.get(name)
    return entry.value if entry is not None else default
