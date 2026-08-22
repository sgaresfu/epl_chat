"""Login, logout and identity."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status
from shared.models import ErrorOut, LoginIn, MeOut, PersonOut
from shared.timezones import BY_KEY, PLACES

from services.api.auth import (
    check_rate_limit,
    clear_failures,
    clear_session,
    client_ip,
    issue_session,
    record_failure,
    verify_code,
)
from services.api.deps import Config, CurrentSession, State

log = structlog.get_logger(__name__)
router = APIRouter(tags=["session"])


def person_out(key: str, fpl_entry_id: int | None = None) -> PersonOut:
    place = BY_KEY[key]
    return PersonOut(
        key=place.key,
        name=place.person,
        city=place.city,
        timezone=place.timezone,
        country=place.country,
        fpl_entry_id=fpl_entry_id,
    )


@router.post(
    "/api/session",
    response_model=MeOut,
    responses={401: {"model": ErrorOut}, 429: {"model": ErrorOut}},
)
async def sign_in(body: LoginIn, request: Request, response: Response, state: State) -> MeOut:
    """One field, one code word, compared constant-time."""
    ip = client_ip(request)
    await check_rate_limit(state.cache, ip)

    person = verify_code(body.code, state.settings)
    if person is None:
        await record_failure(state.cache, ip)
        log.info("auth.rejected", ip=ip)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="That code word is not one of the four. Check for a stray space.",
        )

    # A correct code word costs nothing, and clears anything that came before.
    await clear_failures(state.cache, ip)
    issue_session(response, person, state.settings)
    log.info("auth.signed_in", person=person)
    return _me(person, state.settings.season, state.settings.prediction_lock)


@router.delete("/api/session", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(response: Response, settings: Config) -> Response:
    clear_session(response, settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/me", response_model=MeOut, responses={401: {"model": ErrorOut}})
async def me(session: CurrentSession, settings: Config) -> MeOut:
    return _me(session.person, settings.season, settings.prediction_lock)


def _me(person: str, season: str, lock_iso: str) -> MeOut:
    lock = datetime.fromisoformat(lock_iso.replace("Z", "+00:00"))
    now = datetime.now(UTC)
    return MeOut(
        person=person_out(person),
        people=[person_out(p.key) for p in PLACES],
        season=season,
        prediction_lock=lock,
        locked=now >= lock,
        server_time=now,
    )
