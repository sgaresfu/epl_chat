"""Persistence for predictions and the watch log.

Until now predictions lived on app state, which is fine for a single process
reading seed data and fatal the moment somebody actually files one: a restart,
a redeploy or a second worker loses it. Render restarts services on every
deploy, so an in-memory prediction is a prediction that disappears.

The seed rows from BRIEF section 6 are written once on first start and then
left alone -- re-seeding on every boot would overwrite anything filed since.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from shared.db import MatchPick, OddsHistory, Person, Prediction
from shared.timezones import PLACES
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

SEED = Path(__file__).parents[2] / "shared" / "data" / "seed_predictions.json"


async def ensure_people(db: AsyncSession) -> dict[str, int]:
    """Create the four people if they are not there, and return key -> id."""
    existing = {p.key: p.id for p in (await db.scalars(select(Person))).all()}
    for place in PLACES:
        if place.key in existing:
            continue
        person = Person(
            key=place.key,
            display_name=place.person,
            city=place.city,
            timezone=place.timezone,
            country=place.country,
        )
        db.add(person)
        await db.flush()
        existing[place.key] = person.id
        log.info("repository.person_created", person=place.key)
    return existing


async def seed_predictions(db: AsyncSession) -> int:
    """Write the seeded predictions, but never overwrite an existing row."""
    if not SEED.exists():  # pragma: no cover
        return 0

    people = await ensure_people(db)
    payload = json.loads(SEED.read_text())
    written = 0

    for seed in payload.get("predictions", []):
        person_key = seed["person"]
        person_id = people.get(person_key)
        if person_id is None:  # pragma: no cover
            continue

        already = await db.scalar(
            select(Prediction).where(Prediction.person_id == person_id, Prediction.kind == "table")
        )
        if already is not None:
            continue

        submitted = seed.get("submitted_at")
        db.add(
            Prediction(
                person_id=person_id,
                kind="table",
                payload={
                    "table": seed["table"],
                    "awards": seed["awards"],
                    "champions_league": seed.get("champions_league", {}),
                },
                submitted_at=(
                    datetime.fromisoformat(str(submitted).replace("Z", "+00:00")) if submitted else None
                ),
                locked=False,
            )
        )
        written += 1
        log.info("repository.prediction_seeded", person=person_key)

    return written


async def load_predictions(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Every filed prediction, keyed by person, in the shape the routes expect."""
    rows = (
        await db.execute(
            select(Person.key, Prediction)
            .join(Prediction, Prediction.person_id == Person.id)
            .where(Prediction.kind == "table")
        )
    ).all()

    out: dict[str, dict[str, Any]] = {}
    for key, prediction in rows:
        payload = prediction.payload or {}
        out[key] = {
            "person": key,
            "table": payload.get("table", []),
            "awards": payload.get("awards", {}),
            "champions_league": payload.get("champions_league", {}),
            "submitted_at": (prediction.submitted_at.isoformat() if prediction.submitted_at else None),
        }
    return out


async def save_prediction(
    db: AsyncSession,
    person_key: str,
    table: list[str],
    awards: dict[str, Any],
    champions_league: dict[str, Any],
) -> dict[str, Any]:
    """Insert or update one person's prediction. The caller has checked the lock."""
    people = await ensure_people(db)
    person_id = people[person_key]

    existing = await db.scalar(
        select(Prediction).where(Prediction.person_id == person_id, Prediction.kind == "table")
    )
    now = datetime.now(UTC)
    payload = {"table": table, "awards": awards, "champions_league": champions_league}

    if existing is None:
        existing = Prediction(person_id=person_id, kind="table", payload=payload, submitted_at=now)
        db.add(existing)
    else:
        existing.payload = payload
        existing.submitted_at = now

    log.info("repository.prediction_saved", person=person_key)
    return {
        "person": person_key,
        "table": table,
        "awards": awards,
        "champions_league": champions_league,
        "submitted_at": now.isoformat(),
    }


async def odds_drift(db: AsyncSession, fixture_id: int) -> list[OddsHistory]:
    """Every recorded bet365 price for one fixture, oldest first."""
    rows = await db.scalars(
        select(OddsHistory).where(OddsHistory.fixture_id == fixture_id).order_by(OddsHistory.captured_at)
    )
    return list(rows.all())


async def odds_drift_bulk(db: AsyncSession, fixture_ids: Iterable[int]) -> dict[int, list[OddsHistory]]:
    """Recorded bet365 prices for several fixtures in one query, each oldest first.

    One query for a page of fixtures rather than one per row, the same shape
    as :func:`services.api.routes.football._watched_by`.
    """
    ids = list(fixture_ids)
    if not ids:
        return {}
    rows = await db.scalars(
        select(OddsHistory)
        .where(OddsHistory.fixture_id.in_(ids))
        .order_by(OddsHistory.fixture_id, OddsHistory.captured_at)
    )
    out: dict[int, list[OddsHistory]] = {}
    for row in rows.all():
        out.setdefault(row.fixture_id, []).append(row)
    return out


# --------------------------------------------------------------------------
# Match picks
# --------------------------------------------------------------------------


async def load_picks(
    db: AsyncSession, fixture_ids: Iterable[int] | None = None
) -> list[tuple[MatchPick, str]]:
    """Every pick with its owner's key, or only those for the fixtures named.

    Returns pairs rather than decorating the ORM object with an extra
    attribute: the person key is not part of the row, and pretending it is
    would be a lie the type checker cannot see through.
    """
    stmt = select(MatchPick, Person.key).join(Person, Person.id == MatchPick.person_id)
    if fixture_ids is not None:
        ids = list(fixture_ids)
        if not ids:
            return []
        stmt = stmt.where(MatchPick.fixture_id.in_(ids))
    rows = (await db.execute(stmt.order_by(MatchPick.fixture_id))).all()
    return [(pick, str(key)) for pick, key in rows]


async def save_pick(
    db: AsyncSession,
    person_key: str,
    fixture_id: int,
    home_goals: int,
    away_goals: int,
    odds: tuple[float | None, float | None, float | None] = (None, None, None),
) -> MatchPick:
    """Insert or update one pick. The caller has already checked the deadline.

    The odds snapshot is written only on insert. Changing a pick later should
    not silently re-baseline the market comparison against a price the person
    never saw when they first committed.
    """
    people = await ensure_people(db)
    person_id = people[person_key]
    now = datetime.now(UTC)

    existing = await db.scalar(
        select(MatchPick).where(MatchPick.person_id == person_id, MatchPick.fixture_id == fixture_id)
    )
    if existing is None:
        existing = MatchPick(
            person_id=person_id,
            fixture_id=fixture_id,
            home_goals=home_goals,
            away_goals=away_goals,
            odds_home=odds[0],
            odds_draw=odds[1],
            odds_away=odds[2],
            created_at=now,
            updated_at=now,
        )
        db.add(existing)
    else:
        existing.home_goals = home_goals
        existing.away_goals = away_goals
        existing.updated_at = now

    log.info("repository.pick_saved", person=person_key, fixture=fixture_id)
    return existing
