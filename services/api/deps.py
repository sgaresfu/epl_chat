"""Application state and FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any

import structlog
from fastapi import Depends, HTTPException, Request, status
from shared.cache import Cache, Entry
from shared.config import Settings

from services.api.auth import Session, read_session

log = structlog.get_logger(__name__)


def _seed_predictions() -> dict[str, dict[str, Any]]:
    """Load the seeded predictions from BRIEF section 6."""
    import json
    from pathlib import Path

    seed = Path(__file__).parents[2] / "shared" / "data" / "seed_predictions.json"
    if not seed.exists():  # pragma: no cover
        return {}
    data = json.loads(seed.read_text())
    return {p["person"]: p for p in data.get("predictions", [])}


@dataclass
class AppState:
    """Everything the api holds for its lifetime."""

    settings: Settings
    cache: Cache
    # Predictions live here rather than in a module global so each app instance
    # owns its own state. Backed by the predictions table once the database
    # session is wired in; the shape is identical, so the routes do not change.
    predictions: dict[str, dict[str, Any]] = field(default_factory=_seed_predictions)
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


async def cached(state: AppState, name: str) -> Entry | None:
    return await state.cache.get(name)


async def cached_value(state: AppState, name: str, default: Any = None) -> Any:
    entry = await state.cache.get(name)
    return entry.value if entry is not None else default
