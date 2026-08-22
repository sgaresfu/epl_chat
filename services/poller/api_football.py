"""Confirmed line-ups from API-Football, fetched on demand only.

BRIEF quota discipline: 100 calls a day. Live events are **not** polled from
here -- match minutes and scores come from FPL, which is free and unmetered
-- so the whole budget is reserved for line-ups. Resolving API-Football's own
fixture id costs one call per matchday (every Premier League match on that
date comes back in a single response), never one call per match; the id is
then cached for that fixture's whole life, since it never changes once
assigned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.clubs import find

from services.poller.http import Upstream

API_FOOTBALL = "https://v3.football.api-sports.io"
PREMIER_LEAGUE_ID = 39  # API-Football's own id for the Premier League


def api_football_client(api_key: str) -> Upstream:
    return Upstream(name="api-football", base_url=API_FOOTBALL, headers={"x-apisports-key": api_key})


async def resolve_fixture_ids(up: Upstream, date: str, season: int) -> dict[str, int]:
    """Every Premier League fixture on one date, keyed by ``"HOME-AWAY"``.

    One call resolves the whole day's fixtures, so a matchday with several
    kick-offs costs one call regardless of how many people open a match.
    """
    payload = await up.get_json(
        "/fixtures", params={"date": date, "league": PREMIER_LEAGUE_ID, "season": season}
    )
    out: dict[str, int] = {}
    for row in payload.get("response", []):
        teams = row.get("teams", {})
        home = find(str(teams.get("home", {}).get("name", "")))
        away = find(str(teams.get("away", {}).get("name", "")))
        fixture_id = row.get("fixture", {}).get("id")
        if home and away and fixture_id is not None:
            out[f"{home.short_name}-{away.short_name}"] = int(fixture_id)
    return out


async def fetch_lineups(up: Upstream, af_fixture_id: int) -> dict[str, Any]:
    payload = await up.get_json("/fixtures/lineups", params={"fixture": af_fixture_id})
    return payload if isinstance(payload, dict) else {}


@dataclass(frozen=True, slots=True)
class LineupPlayer:
    name: str
    number: int | None
    position: str


@dataclass(frozen=True, slots=True)
class LineupSide:
    formation: str
    starting: list[LineupPlayer]
    bench: list[LineupPlayer]


def _players(rows: list[dict[str, Any]]) -> list[LineupPlayer]:
    out: list[LineupPlayer] = []
    for row in rows:
        player = row.get("player", {})
        name = player.get("name")
        if not name:
            continue
        out.append(
            LineupPlayer(name=str(name), number=player.get("number"), position=str(player.get("pos") or ""))
        )
    return out


def normalise(
    payload: dict[str, Any], home_short: str, away_short: str
) -> tuple[LineupSide | None, LineupSide | None]:
    """The home and away sides, matched by club rather than array order --
    API-Football does not promise a side's position in the response.

    Both come back ``None`` until roughly an hour before kickoff, when both
    managers have submitted their teams -- that is the ordinary "not out yet"
    state, not a failure.
    """
    home_side: LineupSide | None = None
    away_side: LineupSide | None = None
    for row in payload.get("response", []):
        club = find(str(row.get("team", {}).get("name", "")))
        if club is None:
            continue
        side = LineupSide(
            formation=str(row.get("formation") or ""),
            starting=_players(row.get("startXI", [])),
            bench=_players(row.get("substitutes", [])),
        )
        if club.short_name == home_short:
            home_side = side
        elif club.short_name == away_short:
            away_side = side
    return home_side, away_side
