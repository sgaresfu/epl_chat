"""Predictions: seeded, redacted before the lock, frozen after it.

The lock is enforced here, server-side. A client-side check is not a lock, so
``PUT`` returns 403 the moment the deadline passes regardless of what the UI
believes, and the lock time comes from configuration rather than the request.

Before the lock, a prediction is visible only to its owner -- otherwise the
last person to file could simply copy the best table on the screen.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from shared.clubs import CLUBS
from shared.models import (
    AwardPicks,
    ChampionsLeaguePicks,
    ErrorOut,
    PredictionIn,
    PredictionOut,
    PredictionsOut,
    PreviewIn,
    PreviewOut,
)
from shared.scoring import Award, InvalidTableError, score_prediction, validate_table
from shared.timezones import PLACES

from services.api.auth import require_csrf
from services.api.deps import Config, CurrentSession, Db
from services.api.repository import load_predictions, save_prediction

log = structlog.get_logger(__name__)
router = APIRouter(tags=["predictions"])

LAST_SEASON = Path(__file__).parents[3] / "shared" / "data" / "season_2025_26.json"

ALL_CLUBS = [c.short_name for c in CLUBS]


def lock_at(settings: Any) -> datetime:
    return datetime.fromisoformat(str(settings.prediction_lock).replace("Z", "+00:00"))


def is_locked(settings: Any, now: datetime | None = None) -> bool:
    return (now or datetime.now(UTC)) >= lock_at(settings)


def _awards_of(raw: dict[str, Any]) -> AwardPicks:
    awards = raw.get("awards", {}) or {}

    def name(field: str) -> str:
        value = awards.get(field)
        if isinstance(value, dict):
            return str(value.get("name", ""))
        return str(value or "")

    return AwardPicks(
        golden_boot=name("golden_boot"),
        golden_glove=name("golden_glove"),
        defender=name("defender"),
        playmaker=name("playmaker"),
        player_of_the_season=name("player_of_the_season"),
    )


def _cl_of(raw: dict[str, Any]) -> ChampionsLeaguePicks:
    cl = raw.get("champions_league", {}) or {}
    return ChampionsLeaguePicks(
        winner=str(cl.get("winner", "")),
        finalist_a=str(cl.get("finalist_a", "")),
        finalist_b=str(cl.get("finalist_b", "")),
        top_scorer=str(cl.get("top_scorer", "")),
        draft=bool(cl.get("draft")),
    )


def _to_out(person: str, raw: dict[str, Any] | None, locked: bool, viewer: str) -> PredictionOut:
    """Render one prediction, redacting it from anyone but its owner pre-lock."""
    if raw is None:
        return PredictionOut(
            person=person,
            filed=False,
            locked=locked,
            status="did-not-file" if locked else "open",
        )

    own = person == viewer
    submitted = raw.get("submitted_at")
    submitted_at = datetime.fromisoformat(str(submitted).replace("Z", "+00:00")) if submitted else None

    if not locked and not own:
        # Filed, but nobody else sees the picks until the deadline passes.
        return PredictionOut(
            person=person,
            filed=True,
            redacted=True,
            submitted_at=submitted_at,
            locked=False,
            status="filed",
        )

    return PredictionOut(
        person=person,
        filed=True,
        redacted=False,
        table=list(raw.get("table", [])),
        awards=_awards_of(raw),
        champions_league=_cl_of(raw),
        submitted_at=submitted_at,
        locked=locked,
        status="filed",
    )


@router.get("/api/predictions", response_model=PredictionsOut)
async def list_predictions(session: CurrentSession, settings: Config, db: Db) -> PredictionsOut:
    now = datetime.now(UTC)
    locked = is_locked(settings, now)
    data = await load_predictions(db)
    return PredictionsOut(
        predictions=[_to_out(place.key, data.get(place.key), locked, session.person) for place in PLACES],
        locked=locked,
        lock_at=lock_at(settings),
        seconds_remaining=max(0.0, (lock_at(settings) - now).total_seconds()),
    )


@router.put(
    "/api/predictions",
    response_model=PredictionOut,
    dependencies=[Depends(require_csrf)],
    responses={403: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
async def put_prediction(
    body: PredictionIn, session: CurrentSession, settings: Config, db: Db
) -> PredictionOut:
    """Owner only, and only before the lock."""
    if is_locked(settings):
        log.info("predictions.rejected_after_lock", person=session.person)
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Predictions locked when the season kicked off. This one is read-only now.",
        )

    try:
        validate_table(body.table, ALL_CLUBS)
    except InvalidTableError as exc:
        detail = exc.reason + (f": {', '.join(exc.detail)}" if exc.detail else "")
        raise HTTPException(422, detail=detail) from exc

    # The person always comes from the session, never from the body.
    person = session.person
    saved = await save_prediction(
        db,
        person,
        list(body.table),
        body.awards.model_dump(),
        body.champions_league.model_dump(),
    )
    log.info("predictions.filed", person=person)
    return _to_out(person, saved, False, person)


@router.post("/api/predictions/preview", response_model=PreviewOut)
async def preview(body: PreviewIn, _: CurrentSession) -> PreviewOut:
    """Score a draft table against a finished season.

    The picker calls this rather than reimplementing the rules in TypeScript --
    two implementations of the scoring rules is a bug waiting to happen.
    """
    if not LAST_SEASON.exists():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=("Last season's final table is not loaded, so a preview score cannot be calculated yet."),
        )

    payload = json.loads(LAST_SEASON.read_text())
    actual = [row["club"] for row in payload["table"]]

    picks: dict[Award | str, str] = {}
    if body.awards:
        picks = {k: v for k, v in body.awards.model_dump().items() if v}
    winners = payload.get("awards", {})

    result = score_prediction(body.table, actual, picks, winners)
    return PreviewOut(
        total=result.total,
        table_points=result.table_points,
        award_points=result.award_points,
        exact_hits=result.exact_hits,
        near_hits=result.near_hits,
        top_four_bonus=result.bonuses.top_four,
        champion_bonus=result.bonuses.champion_and_relegated,
        against_season=payload.get("season", body.against_season),
        per_club=[
            {
                "club": c.club,
                "predicted": c.predicted_position,
                "actual": c.actual_position,
                "points": c.points,
            }
            for c in result.clubs
        ],
    )
