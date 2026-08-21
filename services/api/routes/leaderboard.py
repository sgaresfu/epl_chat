"""The prediction leaderboard.

Every number here comes from :func:`shared.scoring.score_prediction` -- the same
function the picker preview and the "if the season ended today" panel call.
There is one implementation of the rules and this is not a second one.

Before a match is played the live table is 20 clubs on zero points, so every
score is legitimately zero and the panel says so rather than implying a real
standing. Head-to-head, however, works from the moment two people have filed:
comparing two predictions needs no results at all.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from shared import keys
from shared.clubs import BY_SHORT_NAME
from shared.models import (
    H2HAgreement,
    H2HGap,
    H2HOut,
    LeaderboardOut,
    LeaderboardRowOut,
)
from shared.scoring import Standing, rank_standings, score_prediction
from shared.timezones import BY_KEY, PLACES

from services.api import views
from services.api.deps import CurrentSession, Db, State
from services.api.repository import load_predictions
from services.api.routes.session import person_out
from services.poller.fpl import compute_table

router = APIRouter(tags=["leaderboard"])

RELEGATION_FROM = 18


async def _live_table(state: State) -> tuple[list[str], int, Any]:
    """The current finishing order, and how many matches it is built from.

    With nothing played there is no order to return. ``compute_table`` still
    yields all 20 clubs on zero points, but their sequence is the alphabetical
    tie-break, not a standing -- and scoring a prediction against an alphabetical
    list manufactures points out of nothing. One person came out six points
    ahead before a ball was kicked.

    So an unplayed season returns an empty order, which scores every club as
    unplaced and therefore zero. That is the honest answer, and the panel says
    why.
    """
    entry = await state.cache.get(keys.FPL_FIXTURES)
    rows: list[dict[str, Any]] | None = entry.value if entry else None
    if not rows:
        return [], 0, entry
    table = compute_table(rows)
    played = sum(r.played for r in table) // 2
    if played == 0:
        return [], 0, entry
    return [r.club for r in table], played, entry


@router.get("/api/leaderboard", response_model=LeaderboardOut)
async def leaderboard(_: CurrentSession, state: State, db: Db) -> LeaderboardOut:
    order, played, entry = await _live_table(state)
    stored = await load_predictions(db)

    standings: list[Standing] = []
    for place in PLACES:
        record = stored.get(place.key)
        if record is None:
            standings.append(
                Standing(
                    person=place.key,
                    breakdown=score_prediction([], []),
                    submitted_at=None,
                    filed=False,
                )
            )
            continue
        standings.append(
            Standing(
                person=place.key,
                breakdown=score_prediction(record["table"], order),
                submitted_at=record.get("submitted_at"),
                filed=True,
            )
        )

    ranked = rank_standings(standings)

    rows: list[LeaderboardRowOut] = []
    for standing in ranked:
        record = stored.get(standing.person)
        rows.append(
            LeaderboardRowOut(
                rank=standing.rank,
                person=person_out(standing.person),
                total=standing.total,
                table_points=standing.breakdown.table_points if standing.filed else 0,
                award_points=standing.breakdown.award_points if standing.filed else 0,
                exact_hits=standing.breakdown.exact_hits if standing.filed else 0,
                filed=standing.filed,
                status="filed" if standing.filed else "did not file",
                cursed_pick=_cursed_pick(record, order) if record else None,
            )
        )

    leader = rows[0].person.key if rows and rows[0].filed and played else None

    return LeaderboardOut(
        rows=rows,
        leader=leader,
        flop_of_the_week=None,
        if_season_ended_today=(f"{BY_KEY[leader].person} would win it." if leader else None),
        freshness=views.freshness(entry, keys.FPL_FIXTURES),
        empty_message=(
            None
            if played
            else "Nobody has scored yet. Every prediction is worth zero until the "
            "first match finishes, and the order below is not a standing."
        ),
    )


def _cursed_pick(record: dict[str, Any], order: list[str]) -> str | None:
    """The highest-placed club in this person's table currently in the drop zone."""
    if not order:
        return None
    positions = {club: index + 1 for index, club in enumerate(order)}
    for club in record.get("table", []):
        if positions.get(str(club), 0) >= RELEGATION_FROM:
            return str(club)
    return None


@router.get("/api/h2h", response_model=H2HOut)
async def head_to_head(
    _: CurrentSession,
    db: Db,
    a: str = Query(...),
    b: str = Query(...),
) -> H2HOut:
    """Where two people agree, and where they disagree most.

    Needs no results, so it works from the moment both have filed -- which is
    the whole of the season's opening night.
    """
    if a not in BY_KEY or b not in BY_KEY:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such person.")
    if a == b:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Pick two different people.")

    stored = await load_predictions(db)
    left, right = stored.get(a), stored.get(b)
    if left is None or right is None:
        missing = a if left is None else b
        return H2HOut(
            a=person_out(a),
            b=person_out(b),
            agreements=[],
            gaps=[],
            agreement_count=0,
            empty_message=f"{BY_KEY[missing].person} has not filed a table.",
        )

    left_pos = {club: i + 1 for i, club in enumerate(left["table"])}
    right_pos = {club: i + 1 for i, club in enumerate(right["table"])}

    agreements: list[H2HAgreement] = []
    gaps: list[H2HGap] = []

    for club, position in left_pos.items():
        other = right_pos.get(club)
        if other is None:
            continue
        club_out = views.club_out(BY_SHORT_NAME[club])
        if other == position:
            agreements.append(H2HAgreement(club=club_out, position=position))
        else:
            gaps.append(
                H2HGap(
                    club=club_out,
                    a_position=position,
                    b_position=other,
                    distance=abs(position - other),
                )
            )

    agreements.sort(key=lambda row: row.position)
    gaps.sort(key=lambda row: -row.distance)

    return H2HOut(
        a=person_out(a),
        b=person_out(b),
        agreements=agreements,
        gaps=gaps[:8],
        agreement_count=len(agreements),
    )
