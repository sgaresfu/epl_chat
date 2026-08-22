"""Player and team statistics.

Everything here comes from FPL's bootstrap, which carries more than points:
expected goals and assists, ICT, per-90 rates, minutes and starts. That is the
closest thing to a modelled dataset available without a paid feed, and it is
what lets the tables show whether a striker is finishing above or below what
their chances were worth rather than just counting goals.

The whole player list is returned once and sorted in the browser. Six hundred
players trimmed to the fields on screen is a small payload, and sorting a
column then costs nothing -- which is the difference between a table that feels
alive and one that reloads.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from shared import keys
from shared.clubs import BY_FPL_ID, BY_SHORT_NAME
from shared.models import (
    PlayerStatOut,
    PlayerStatsOut,
    TeamStatOut,
    TeamStatsOut,
)

from services.api import views
from services.api.deps import CurrentSession, State
from services.poller.fpl import POSITIONS, compute_table, current_gameweek, has_result

router = APIRouter(tags=["stats"])

# Below this, per-90 rates are noise rather than signal.
MIN_MINUTES_FOR_RATES = 90


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


def _player(row: dict[str, Any]) -> PlayerStatOut | None:
    club = BY_FPL_ID.get(int(row.get("team", 0)))
    if club is None:
        return None

    minutes = int(row.get("minutes") or 0)
    goals = int(row.get("goals_scored") or 0)
    assists = int(row.get("assists") or 0)
    xg = _f(row.get("expected_goals"))
    xa = _f(row.get("expected_assists"))

    def per_90(total: float) -> float:
        # Rates from a handful of minutes are noise, so they read zero until
        # there is a full match to divide by.
        if minutes < MIN_MINUTES_FOR_RATES:
            return 0.0
        return round(total * 90 / minutes, 2)

    first = str(row.get("first_name", "")).strip()
    second = str(row.get("second_name", "")).strip()

    return PlayerStatOut(
        id=int(row["id"]),
        name=str(row.get("web_name", "")),
        full_name=" ".join(p for p in (first, second) if p),
        club=club.short_name,
        club_name=club.name,
        position=POSITIONS.get(int(row.get("element_type", 0)), "?"),
        minutes=minutes,
        starts=int(row.get("starts") or 0),
        goals=goals,
        assists=assists,
        goal_involvements=goals + assists,
        clean_sheets=int(row.get("clean_sheets") or 0),
        saves=int(row.get("saves") or 0),
        yellow_cards=int(row.get("yellow_cards") or 0),
        red_cards=int(row.get("red_cards") or 0),
        bonus=int(row.get("bonus") or 0),
        xg=xg,
        xa=xa,
        xgi=_f(row.get("expected_goal_involvements")),
        # Positive means finishing above what the chances were worth.
        goals_minus_xg=round(goals - xg, 2),
        per_90_goals=per_90(goals),
        per_90_assists=per_90(assists),
        ict=_f(row.get("ict_index")),
        form=_f(row.get("form")),
        points=_f(row.get("total_points")),
        points_per_game=_f(row.get("points_per_game")),
        price=round(int(row.get("now_cost") or 0) / 10, 1),
        selected_by=_f(row.get("selected_by_percent")),
        status=str(row.get("status", "a")),
        news=str(row.get("news", "")),
    )


@router.get("/api/stats/players", response_model=PlayerStatsOut)
async def players(_: CurrentSession, state: State) -> PlayerStatsOut:
    boot = await state.cache.get(keys.FPL_BOOTSTRAP)
    fixtures = await state.cache.get(keys.FPL_FIXTURES)
    played = sum(1 for f in (fixtures.value if fixtures else []) if has_result(f))

    if boot is None:
        return PlayerStatsOut(
            freshness=views.freshness(boot, keys.FPL_BOOTSTRAP),
            empty_message="Player statistics appear once the squad list has loaded.",
        )

    event = current_gameweek(boot.value)
    rows = [_player(row) for row in boot.value.get("elements", [])]
    people = [p for p in rows if p is not None]

    return PlayerStatsOut(
        players=people,
        gameweek=int(event["id"]) if event else 0,
        matches_played=played,
        freshness=views.freshness(boot, keys.FPL_BOOTSTRAP),
        empty_message=(
            None
            if played
            else "Nobody has played yet, so every column reads zero. The table "
            "fills in from the first whistle."
        ),
    )


@router.get("/api/stats/teams", response_model=TeamStatsOut)
async def teams(_: CurrentSession, state: State) -> TeamStatsOut:
    fixtures_entry = await state.cache.get(keys.FPL_FIXTURES)
    boot = await state.cache.get(keys.FPL_BOOTSTRAP)
    rows: list[dict[str, Any]] = fixtures_entry.value if fixtures_entry else []

    if not rows:
        return TeamStatsOut(
            freshness=views.freshness(fixtures_entry, keys.FPL_FIXTURES),
            empty_message="Team statistics appear once the fixture list has loaded.",
        )

    table = compute_table(rows)
    played_total = sum(r.played for r in table) // 2

    # Clean sheets and blanks are not in the table, so count them from results.
    clean: dict[str, int] = {r.club: 0 for r in table}
    blank: dict[str, int] = {r.club: 0 for r in table}
    for fixture in rows:
        if not has_result(fixture):
            continue
        try:
            home = BY_FPL_ID[int(fixture["team_h"])].short_name
            away = BY_FPL_ID[int(fixture["team_a"])].short_name
        except KeyError:
            continue
        hs, as_ = int(fixture["team_h_score"]), int(fixture["team_a_score"])
        if as_ == 0:
            clean[home] += 1
        if hs == 0:
            clean[away] += 1
            blank[home] += 1
        if as_ == 0:
            blank[away] += 1

    # Squad-level expected numbers, which say more than the scoreline this early.
    squad_xg: dict[str, float] = {r.club: 0.0 for r in table}
    squad_xga: dict[str, float] = {r.club: 0.0 for r in table}
    if boot is not None:
        for element in boot.value.get("elements", []):
            club = BY_FPL_ID.get(int(element.get("team", 0)))
            if club is None:
                continue
            squad_xg[club.short_name] += _f(element.get("expected_goals"))
            squad_xga[club.short_name] += _f(element.get("expected_goals_conceded"))

    out = [
        TeamStatOut(
            club=views.club_out(BY_SHORT_NAME[row.club]),
            position=index,
            played=row.played,
            won=row.won,
            drawn=row.drawn,
            lost=row.lost,
            goals_for=row.goals_for,
            goals_against=row.goals_against,
            goal_difference=row.goal_difference,
            points=row.points,
            clean_sheets=clean.get(row.club, 0),
            failed_to_score=blank.get(row.club, 0),
            goals_per_game=round(row.goals_for / row.played, 2) if row.played else 0.0,
            conceded_per_game=round(row.goals_against / row.played, 2) if row.played else 0.0,
            form=list(row.form),
            squad_xg=round(squad_xg.get(row.club, 0.0), 2),
            squad_xga=round(squad_xga.get(row.club, 0.0), 2),
        )
        for index, row in enumerate(table, start=1)
    ]

    return TeamStatsOut(
        teams=out,
        matches_played=played_total,
        freshness=views.freshness(fixtures_entry, keys.FPL_FIXTURES),
        empty_message=(None if played_total else "Nobody has played yet, so every column reads zero."),
    )
