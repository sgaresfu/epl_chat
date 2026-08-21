"""The watch log.

"I watched this" opens at kickoff and closes twelve hours after full time, and
that window is enforced here rather than in the UI -- a disabled button is a
hint, not a rule.

``local_hour`` is written at insert time in the person's own zone, which is what
makes the night medal correct for ever. Alberta stops observing daylight saving
on 1 November 2026, mid-season; recomputing history against a changed rule would
silently rewrite who earned what.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from shared import keys
from shared.db import WatchLog
from shared.models import WatchStatsOut, WatchToggleIn
from shared.timezones import BY_KEY, is_night, local_hour
from sqlalchemy import select

from services.api import views
from services.api.auth import require_csrf
from services.api.deps import CurrentSession, Db, State
from services.api.repository import ensure_people
from services.api.views import watch_window_open
from services.poller.fpl import is_over

log = structlog.get_logger(__name__)
router = APIRouter(tags=["watch"])

HOURS_PER_MATCH = 2.0


async def _fixture(state: State, fixture_id: int) -> dict[str, Any] | None:
    entry = await state.cache.get(keys.FPL_FIXTURES)
    rows: list[dict[str, Any]] = entry.value if entry else []
    return next((r for r in rows if int(r["id"]) == fixture_id), None)


@router.post(
    "/api/watch",
    response_model=WatchStatsOut,
    dependencies=[Depends(require_csrf)],
)
async def toggle(body: WatchToggleIn, session: CurrentSession, state: State, db: Db) -> WatchStatsOut:
    """Mark a match watched, or un-mark it. Window checked server-side."""
    fixture = await _fixture(state, body.fixture_id)
    if fixture is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such fixture.")

    kickoff_raw = fixture.get("kickoff_time")
    kickoff = datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00")) if kickoff_raw else None
    now = datetime.now(UTC)

    if not watch_window_open(kickoff, is_over(fixture), now):
        detail = (
            "That match has not kicked off yet."
            if kickoff and now < kickoff
            else "The window for marking this match closed twelve hours after full time."
        )
        raise HTTPException(status.HTTP_409_CONFLICT, detail=detail)

    people = await ensure_people(db)
    person_id = people[session.person]
    place = BY_KEY[session.person]

    existing = await db.scalar(
        select(WatchLog).where(WatchLog.person_id == person_id, WatchLog.fixture_id == body.fixture_id)
    )
    if existing is not None:
        await db.delete(existing)
        log.info("watch.unmarked", person=session.person, fixture=body.fixture_id)
    else:
        moment = kickoff or now
        db.add(
            WatchLog(
                person_id=person_id,
                fixture_id=body.fixture_id,
                watched_at=now,
                gameweek=int(fixture.get("event") or 0),
                # Written in this person's zone now, never recomputed later.
                local_hour=local_hour(moment, place.timezone),
                night_medal=is_night(moment, place.timezone),
            )
        )
        log.info("watch.marked", person=session.person, fixture=body.fixture_id)

    await db.flush()
    return await _stats(session.person, state, db)


@router.get("/api/watch", response_model=WatchStatsOut)
async def stats(session: CurrentSession, state: State, db: Db) -> WatchStatsOut:
    return await _stats(session.person, state, db)


async def _stats(person: str, state: State, db: Db) -> WatchStatsOut:
    people = await ensure_people(db)
    person_id = people[person]

    rows = (await db.scalars(select(WatchLog).where(WatchLog.person_id == person_id))).all()

    entry = await state.cache.get(keys.FPL_FIXTURES)
    fixtures: list[dict[str, Any]] = entry.value if entry else []
    total_matches = len(fixtures) or 380

    watched = len(rows)
    medals = sum(1 for r in rows if r.night_medal)

    return WatchStatsOut(
        person=person,
        watched=watched,
        total_matches=total_matches,
        percent=round(watched / total_matches * 100, 1) if total_matches else 0.0,
        hours=round(watched * HOURS_PER_MATCH, 1),
        night_medals=medals,
        streak=_streak(rows),
        freshness=views.freshness(entry, keys.FPL_FIXTURES),
    )


def _streak(rows: Any) -> int:
    """Consecutive gameweeks with at least one match watched, most recent first."""
    weeks = sorted({r.gameweek for r in rows if r.gameweek}, reverse=True)
    if not weeks:
        return 0
    streak = 1
    for earlier, later in zip(weeks[1:], weeks, strict=False):
        if later - earlier == 1:
            streak += 1
        else:
            break
    return streak
