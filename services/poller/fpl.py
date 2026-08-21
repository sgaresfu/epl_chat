"""Fantasy Premier League client.

FPL is the backbone: no key, no quota, and it carries the table, fixtures,
player stats, live points and the mini-league. Everything derived from it is
normalised through :mod:`shared.clubs` here, in the poller, so the api and the
browser never see a raw upstream shape.

Two behaviours are deliberate:

* The league sync reads ``new_entries`` as well as ``standings``. Before the
  first deadline FPL returns members only in ``new_entries`` and leaves
  ``standings.results`` empty -- which is the state league 412955 is in right
  now. Reading only standings would render an empty /fpl on launch day.
* The live table is computed from finished fixtures rather than read from FPL's
  own table, so the order is right the moment a match ends instead of whenever
  FPL recomputes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from shared.clubs import CLUBS, Club, by_fpl_id

from services.poller.http import Upstream

log = structlog.get_logger(__name__)

BASE = "https://fantasy.premierleague.com/api"


def client() -> Upstream:
    return Upstream(name="fpl", base_url=BASE)


# --------------------------------------------------------------------------
# Raw fetches
# --------------------------------------------------------------------------


async def bootstrap(up: Upstream) -> dict[str, Any]:
    """Teams, players, gameweeks. The 10-minute static payload."""
    data = await up.get_json("/bootstrap-static/")
    assert isinstance(data, dict)
    return data


async def fixtures(up: Upstream) -> list[dict[str, Any]]:
    data = await up.get_json("/fixtures/")
    assert isinstance(data, list)
    return data


async def live_gameweek(up: Upstream, gameweek: int) -> dict[str, Any]:
    """Per-player live points for a gameweek. Polled every 30s only while in play."""
    data = await up.get_json(f"/event/{gameweek}/live/")
    assert isinstance(data, dict)
    return data


async def league_standings(up: Upstream, league_id: int) -> dict[str, Any]:
    data = await up.get_json(f"/leagues-classic/{league_id}/standings/")
    assert isinstance(data, dict)
    return data


async def entry_picks(up: Upstream, entry_id: int, gameweek: int) -> dict[str, Any]:
    data = await up.get_json(f"/entry/{entry_id}/event/{gameweek}/picks/")
    assert isinstance(data, dict)
    return data


async def entry_history(up: Upstream, entry_id: int) -> dict[str, Any]:
    data = await up.get_json(f"/entry/{entry_id}/history/")
    assert isinstance(data, dict)
    return data


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LeagueMember:
    """One mini-league entry, wherever FPL happened to file it."""

    entry_id: int
    entry_name: str
    player_name: str
    rank: int | None
    total: int
    event_total: int
    # True when FPL has not yet moved this entry into scored standings.
    pending: bool


def parse_league(payload: dict[str, Any]) -> list[LeagueMember]:
    """Read mini-league members from *both* places FPL puts them.

    Before the season's first deadline every member sits in ``new_entries`` and
    ``standings.results`` is empty. After GW1 is scored they migrate. A sync
    that reads only ``standings`` shows an empty league for the entire opening
    week, which is precisely when four people are most likely to look at it.
    """
    members: dict[int, LeagueMember] = {}

    for row in payload.get("standings", {}).get("results", []) or []:
        members[int(row["entry"])] = LeagueMember(
            entry_id=int(row["entry"]),
            entry_name=str(row.get("entry_name", "")),
            player_name=str(row.get("player_name", "")),
            rank=row.get("rank"),
            total=int(row.get("total", 0)),
            event_total=int(row.get("event_total", 0)),
            pending=False,
        )

    for row in payload.get("new_entries", {}).get("results", []) or []:
        entry_id = int(row["entry"])
        if entry_id in members:
            continue
        first = str(row.get("player_first_name", "")).strip()
        last = str(row.get("player_last_name", "")).strip()
        members[entry_id] = LeagueMember(
            entry_id=entry_id,
            entry_name=str(row.get("entry_name", "")),
            player_name=" ".join(p for p in (first, last) if p),
            rank=None,
            total=0,
            event_total=0,
            pending=True,
        )

    return sorted(members.values(), key=lambda m: (m.rank is None, m.rank or 0, m.entry_name))


@dataclass(frozen=True, slots=True)
class TableRow:
    """One row of the live table, computed from finished fixtures."""

    club: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    form: tuple[str, ...] = ()

    @property
    def points(self) -> int:
        return self.won * 3 + self.drawn

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


def compute_table(fixture_rows: list[dict[str, Any]]) -> list[TableRow]:
    """Build the league table from finished fixtures only.

    Before a ball is kicked this correctly returns all 20 clubs on zero points,
    which is the state the site launches in and a first-class screen rather than
    an empty one.
    """
    tallies: dict[str, dict[str, Any]] = {
        c.short_name: {"w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "form": []} for c in CLUBS
    }

    played = [f for f in fixture_rows if f.get("finished") and f.get("team_h_score") is not None]
    played.sort(key=lambda f: f.get("kickoff_time") or "")

    for fixture in played:
        try:
            home = by_fpl_id(int(fixture["team_h"])).short_name
            away = by_fpl_id(int(fixture["team_a"])).short_name
        except LookupError:
            log.warning("fpl.unknown_team_in_fixture", fixture_id=fixture.get("id"))
            continue

        hs, as_ = int(fixture["team_h_score"]), int(fixture["team_a_score"])
        tallies[home]["gf"] += hs
        tallies[home]["ga"] += as_
        tallies[away]["gf"] += as_
        tallies[away]["ga"] += hs

        if hs > as_:
            tallies[home]["w"] += 1
            tallies[away]["l"] += 1
            tallies[home]["form"].append("W")
            tallies[away]["form"].append("L")
        elif hs < as_:
            tallies[away]["w"] += 1
            tallies[home]["l"] += 1
            tallies[away]["form"].append("W")
            tallies[home]["form"].append("L")
        else:
            tallies[home]["d"] += 1
            tallies[away]["d"] += 1
            tallies[home]["form"].append("D")
            tallies[away]["form"].append("D")

    rows = [
        TableRow(
            club=club,
            played=t["w"] + t["d"] + t["l"],
            won=t["w"],
            drawn=t["d"],
            lost=t["l"],
            goals_for=t["gf"],
            goals_against=t["ga"],
            form=tuple(t["form"][-5:]),
        )
        for club, t in tallies.items()
    ]
    return order_table(rows)


def order_table(rows: list[TableRow]) -> list[TableRow]:
    """Premier League ordering: points, then goal difference, then goals scored.

    Clubs still level are ranked alphabetically, which is what the league itself
    does until a play-off would be required.
    """
    return sorted(
        rows,
        key=lambda r: (-r.points, -r.goal_difference, -r.goals_for, r.club),
    )


def club_of(fpl_id: int) -> Club:
    return by_fpl_id(fpl_id)


def current_gameweek(boot: dict[str, Any]) -> dict[str, Any] | None:
    """The gameweek in progress, else the next one, else None once the season ends."""
    events = boot.get("events", []) or []
    for event in events:
        if event.get("is_current"):
            return dict(event)
    for event in events:
        if event.get("is_next"):
            return dict(event)
    return None


def parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
