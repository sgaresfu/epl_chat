"""Projected table and derived stats."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from shared import keys
from shared.clubs import BY_SHORT_NAME
from shared.models import ProjectedTableOut, TableRowOut
from shared.projection import project

from services.api import views
from services.api.deps import CurrentSession, State
from services.poller.fpl import compute_table

router = APIRouter(tags=["table"])


@router.get("/api/table/projected", response_model=ProjectedTableOut)
async def projected(_: CurrentSession, state: State) -> ProjectedTableOut:
    """Current points plus every remaining fixture resolved to last season."""
    entry = await state.cache.get(keys.FPL_FIXTURES)
    rows: list[dict[str, Any]] | None = entry.value if entry else None

    if not rows:
        return ProjectedTableOut(
            rows=[],
            gameweek=0,
            matches_played=0,
            season_started=False,
            freshness=views.freshness(entry, keys.FPL_FIXTURES),
            empty_message="The projection needs the fixture list before it can run.",
            modelled_rows=[],
            method="",
        )

    current = compute_table(rows)
    result = project(rows, current)

    out_rows: list[TableRowOut] = []
    for index, row in enumerate(result.rows, start=1):
        out_rows.append(
            TableRowOut(
                position=index,
                club=views.club_out(BY_SHORT_NAME[row.club]),
                played=row.played,
                won=row.won,
                drawn=row.drawn,
                lost=row.lost,
                goals_for=row.goals_for,
                goals_against=row.goals_against,
                goal_difference=row.goal_difference,
                points=row.points,
                form=list(row.form),
                modelled=result.is_modelled(row.club),
                note=result.note_for(row.club),
            )
        )

    played = sum(r.played for r in current) // 2
    return ProjectedTableOut(
        rows=out_rows,
        gameweek=0,
        matches_played=played,
        season_started=played > 0,
        freshness=views.freshness(entry, keys.FPL_FIXTURES),
        modelled_rows=sorted(result.modelled_clubs),
        method=result.method,
    )
