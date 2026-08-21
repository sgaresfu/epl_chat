"""Table, fixtures and the home payload -- all served from cache."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Query
from shared import keys
from shared import season as season_mod
from shared.models import (
    ClubOut,
    FixtureListOut,
    FixtureOut,
    HomeOut,
    NextMatchOut,
    SeasonOut,
    TableOut,
    TimelineMarker,
)

from services.api import views
from services.api.deps import CurrentSession, Db, State
from services.poller.fpl import is_in_play, is_over

log = structlog.get_logger(__name__)
router = APIRouter(tags=["football"])


async def _fixtures(state: State) -> tuple[list[dict[str, Any]] | None, Any]:
    entry = await state.cache.get(keys.FPL_FIXTURES)
    rows = entry.value if entry else None
    return (rows if isinstance(rows, list) else None), entry


async def _watched_by(db: Db) -> dict[int, list[str]]:
    """fixture id -> the people who marked it watched.

    One query for the whole page rather than one per fixture; with four people
    and 380 rows the table is small enough to read whole.
    """
    from shared.db import Person, WatchLog
    from sqlalchemy import select

    rows = (
        await db.execute(
            select(WatchLog.fixture_id, Person.key).join(Person, Person.id == WatchLog.person_id)
        )
    ).all()
    out: dict[int, list[str]] = {}
    for fixture_id, key in rows:
        out.setdefault(int(fixture_id), []).append(str(key))
    return out


async def _gameweek(state: State) -> int:
    entry = await state.cache.get(keys.FPL_BOOTSTRAP)
    if not entry:
        return 0
    from services.poller.fpl import current_gameweek

    event = current_gameweek(entry.value)
    return int(event["id"]) if event else 0


@router.get("/api/clubs", response_model=list[ClubOut])
async def clubs(_: CurrentSession) -> list[ClubOut]:
    """The canonical club table, so the frontend never guesses a crest colour."""
    return views.all_clubs()


@router.get("/api/table", response_model=TableOut)
async def table(_: CurrentSession, state: State) -> TableOut:
    rows, entry = await _fixtures(state)
    return views.build_table(rows, entry, keys.FPL_FIXTURES, await _gameweek(state))


@router.get("/api/fixtures", response_model=FixtureListOut)
async def fixtures(
    _: CurrentSession,
    state: State,
    db: Db,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    gameweek: int | None = Query(None),
) -> FixtureListOut:
    rows, entry = await _fixtures(state)
    if rows is None:
        return views.build_fixture_list(None, entry, keys.FPL_FIXTURES)

    selected = rows
    if gameweek is not None:
        selected = [r for r in selected if r.get("event") == gameweek]
    if from_ or to:

        def in_range(row: dict[str, Any]) -> bool:
            kickoff = row.get("kickoff_time")
            if not kickoff:
                return False
            moment = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            if from_ and moment < from_:
                return False
            return not (to and moment > to)

        selected = [r for r in selected if in_range(r)]

    selected = sorted(selected, key=lambda r: (r.get("kickoff_time") or "9999", r.get("id", 0)))
    watched = await _watched_by(db)
    return views.build_fixture_list(selected, entry, keys.FPL_FIXTURES, watched_by_fixture=watched)


@router.get("/api/fixtures/{fixture_id}", response_model=FixtureOut)
async def fixture(fixture_id: int, _: CurrentSession, state: State, db: Db) -> FixtureOut:
    from fastapi import HTTPException, status

    rows, _entry = await _fixtures(state)
    row = next((r for r in (rows or []) if int(r["id"]) == fixture_id), None)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such fixture.")
    watched = await _watched_by(db)
    return views.build_fixture(row, watched_by=watched.get(fixture_id, []))


@router.get("/api/season", response_model=SeasonOut)
async def season(session: CurrentSession, state: State) -> SeasonOut:
    return await _season(state, session.person)


async def _season(state: State, person: str) -> SeasonOut:
    rows, _ = await _fixtures(state)
    boot = await state.cache.get(keys.FPL_BOOTSTRAP)
    events = (boot.value.get("events", []) if boot else []) or []
    built = season_mod.build(rows or [], events)

    watched = 0  # replaced by the watch-log count once the database is wired

    return SeasonOut(
        starts=built.starts,
        ends=built.ends,
        today=built.today,
        percent=round(built.percent, 3),
        day=built.day,
        total_days=built.total_days,
        days_remaining=built.days_remaining,
        gameweeks_played=built.gameweeks_played,
        gameweeks_total=built.gameweeks_total,
        matches_played=built.matches_played,
        matches_total=built.matches_total,
        matches_remaining=built.matches_remaining,
        watched=watched,
        markers=[
            TimelineMarker(label=m.label, date=m.date, percent=round(m.percent, 3), is_now=m.is_now)
            for m in built.markers
        ],
    )


@router.get("/api/home", response_model=HomeOut)
async def home(session: CurrentSession, state: State) -> HomeOut:
    """Everything the front page needs, in one request."""
    rows, _entry = await _fixtures(state)
    now = datetime.now(UTC)

    next_match = NextMatchOut(message="The fixture list has not loaded yet.")
    if rows:
        upcoming = sorted(
            (r for r in rows if r.get("kickoff_time") and not is_over(r)),
            key=lambda r: r["kickoff_time"],
        )
        in_play = [r for r in upcoming if is_in_play(r)]
        chosen = in_play[0] if in_play else (upcoming[0] if upcoming else None)
        if chosen is not None:
            kickoff = datetime.fromisoformat(chosen["kickoff_time"].replace("Z", "+00:00"))
            next_match = NextMatchOut(
                fixture=views.build_fixture(chosen, now=now),
                countdown_seconds=max(0.0, (kickoff - now).total_seconds()),
                in_play=is_in_play(chosen),
                message=None,
            )
        else:
            next_match = NextMatchOut(message="The season is over. See you in August.")

    return HomeOut(
        next_match=next_match,
        season=await _season(state, session.person),
        line_of_the_day=await _line_of_the_day(state, now),
    )


async def _line_of_the_day(state: State, now: datetime) -> str | None:
    """One generated sentence tying the table to someone's prediction.

    Before the season starts there is no table to tie anything to, so it says
    something true about the wait instead of inventing a narrative.
    """
    rows, _ = await _fixtures(state)
    if not rows:
        return None
    played = sum(1 for r in rows if is_over(r))
    if played == 0:
        upcoming = sorted((r for r in rows if r.get("kickoff_time")), key=lambda r: r["kickoff_time"])
        if not upcoming:
            return None
        kickoff = datetime.fromisoformat(upcoming[0]["kickoff_time"].replace("Z", "+00:00"))
        hours = (kickoff - now).total_seconds() / 3600
        if hours < 0:
            return "The first match is under way. Every prediction is now fixed."
        if hours < 24:
            return f"Nobody has a point yet, and in {int(hours)} hours nobody will have an excuse either."
        return f"{int(hours // 24)} days until the first ball. Two predictions still unfiled."
    return f"{played} matches played. The table is starting to disagree with everyone."
