"""The fantasy mini-league.

Standings are read from the cache the poller fills, then attributed to people
through the stored mapping in :mod:`shared.fpl_people`.

Two states matter here and both are live right now:

* Before the first deadline FPL keeps members in ``new_entries`` and leaves
  ``standings.results`` empty, so every row is ``pending`` and there are no
  points to show yet. That is reported as a real state, not as an error.
* An entry with no mapping is listed as unattributed rather than dropped, so a
  new manager joining is visible instead of silently missing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from shared import keys
from shared.fpl_people import person_for
from shared.models import FplStandingRow, FplStandingsOut

from services.api import views
from services.api.deps import Config, CurrentSession, State
from services.poller.fpl import current_gameweek, parse_league

router = APIRouter(tags=["fpl"])


@router.get("/api/fpl/standings", response_model=FplStandingsOut)
async def standings(_: CurrentSession, state: State, settings: Config) -> FplStandingsOut:
    entry = await state.cache.get(keys.FPL_LEAGUE)
    payload: dict[str, Any] = entry.value if entry else {}

    boot = await state.cache.get(keys.FPL_BOOTSTRAP)
    event = current_gameweek(boot.value) if boot else None
    gameweek = int(event["id"]) if event else 0

    if not payload:
        return FplStandingsOut(
            league_id=settings.fpl_league_id,
            league_name="",
            rows=[],
            gameweek=gameweek,
            freshness=views.freshness(entry, keys.FPL_LEAGUE),
            empty_message="The mini-league appears once the poller has fetched it.",
        )

    members = parse_league(payload)
    rows: list[FplStandingRow] = []
    unmapped: list[int] = []

    for member in members:
        person = person_for(member.entry_id)
        if person is None:
            unmapped.append(member.entry_id)
        rows.append(
            FplStandingRow(
                entry_id=member.entry_id,
                entry_name=member.entry_name,
                player_name=member.player_name,
                person=person,
                rank=member.rank,
                total=member.total,
                event_total=member.event_total,
                pending=member.pending,
            )
        )

    # Pending entries have no rank yet, so order them by person for a stable
    # list rather than by a rank that does not exist.
    rows.sort(key=lambda r: (r.rank is None, r.rank or 0, r.person or "zz"))

    all_pending = bool(rows) and all(r.pending for r in rows)
    return FplStandingsOut(
        league_id=settings.fpl_league_id,
        league_name=str(payload.get("league", {}).get("name", "")),
        rows=rows,
        gameweek=gameweek,
        freshness=views.freshness(entry, keys.FPL_LEAGUE),
        empty_message=(
            "All four managers are registered. FPL keeps new entries out of the "
            "scored standings until gameweek one is settled, so points appear "
            "after the first round."
            if all_pending
            else None
        ),
        unmapped=unmapped,
    )
