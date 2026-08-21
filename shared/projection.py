"""The projected table.

Every remaining fixture is resolved to last season's result for the identical
match-up and added to the points already earned. Where last season has no such
match-up -- because one of the clubs was in the Championship -- the fixture is
treated as a draw and every affected club is labelled *modelled* rather than
derived, which is the default the brief left to me.

That labelling matters more than it sounds: Coventry, Hull and Ipswich have no
Premier League record at all, so 108 of the 380 fixtures (28%) are modelled
rather than derived. A projection that hid that would be presenting a guess as
a calculation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from services.poller.fpl import TableRow, is_over, order_table

from shared.clubs import CLUBS, by_fpl_id

DATA = Path(__file__).parent / "data" / "season_2025_26.json"


# A row is called "modelled" once this share of its projected matches had to be
# guessed. Every club plays the promoted three, so a flag that trips on a single
# modelled fixture would mark all 20 rows and tell the reader nothing; the
# promoted clubs themselves are modelled end to end, and that is the real
# distinction worth surfacing.
MODELLED_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class Projection:
    rows: list[TableRow]
    modelled_per_club: dict[str, int]
    projected_per_club: dict[str, int]
    derived_fixtures: int
    modelled_fixtures: int

    def modelled_share(self, club: str) -> float:
        total = self.projected_per_club.get(club, 0)
        return self.modelled_per_club.get(club, 0) / total if total else 0.0

    def is_modelled(self, club: str) -> bool:
        return self.modelled_share(club) >= MODELLED_THRESHOLD

    @property
    def modelled_clubs(self) -> frozenset[str]:
        """Only the rows where guesswork dominates -- the promoted three."""
        return frozenset(c for c in self.projected_per_club if self.is_modelled(c))

    def note_for(self, club: str) -> str | None:
        modelled = self.modelled_per_club.get(club, 0)
        total = self.projected_per_club.get(club, 0)
        if not modelled or not total:
            return None
        if modelled == total:
            return f"No Premier League record: all {total} projected matches modelled as draws."
        return f"{modelled} of {total} projected matches modelled as draws."

    @property
    def method(self) -> str:
        total = self.derived_fixtures + self.modelled_fixtures
        if not total:
            return "No fixtures left to project."
        return (
            f"{self.derived_fixtures} of {total} remaining fixtures resolved to last "
            f"season's result for the same match-up. The other {self.modelled_fixtures} "
            "involve a promoted club with no Premier League record and are modelled as draws."
        )


@lru_cache(maxsize=1)
def last_season() -> dict[str, Any]:
    if not DATA.exists():  # pragma: no cover
        return {"head_to_head": {}, "table": []}
    data = json.loads(DATA.read_text())
    assert isinstance(data, dict)
    return data


def head_to_head(home: str, away: str) -> tuple[int, int] | None:
    """Last season's score for this exact match-up, if both clubs were in it."""
    raw = last_season().get("head_to_head", {}).get(f"{home}|{away}")
    if isinstance(raw, list) and len(raw) == 2:
        return int(raw[0]), int(raw[1])
    return None


def project(
    fixtures: list[dict[str, Any]],
    current: list[TableRow] | None = None,
) -> Projection:
    """Add every unplayed fixture's projected result to the current table."""
    tallies: dict[str, dict[str, int]] = {
        c.short_name: {"p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0} for c in CLUBS
    }
    for row in current or []:
        t = tallies[row.club]
        t.update(
            p=row.played,
            w=row.won,
            d=row.drawn,
            l=row.lost,
            gf=row.goals_for,
            ga=row.goals_against,
        )

    modelled_per_club: dict[str, int] = {c.short_name: 0 for c in CLUBS}
    projected_per_club: dict[str, int] = {c.short_name: 0 for c in CLUBS}
    derived_count = 0
    modelled_count = 0

    for fixture in fixtures:
        if is_over(fixture):
            continue
        if not fixture.get("kickoff_time"):
            # A postponed match has no date; it is excluded from projections
            # rather than assumed, per BRIEF section 11.
            continue
        try:
            home = by_fpl_id(int(fixture["team_h"])).short_name
            away = by_fpl_id(int(fixture["team_a"])).short_name
        except LookupError:
            continue

        result = head_to_head(home, away)
        if result is None:
            # A draw, and scored 1-1 rather than 0-0 so goal difference is not
            # quietly flattered by every modelled match.
            home_goals = away_goals = 1
            modelled_per_club[home] += 1
            modelled_per_club[away] += 1
            modelled_count += 1
        else:
            home_goals, away_goals = result
            derived_count += 1

        for club in (home, away):
            tallies[club]["p"] += 1
            projected_per_club[club] += 1
        tallies[home]["gf"] += home_goals
        tallies[home]["ga"] += away_goals
        tallies[away]["gf"] += away_goals
        tallies[away]["ga"] += home_goals

        if home_goals > away_goals:
            tallies[home]["w"] += 1
            tallies[away]["l"] += 1
        elif away_goals > home_goals:
            tallies[away]["w"] += 1
            tallies[home]["l"] += 1
        else:
            tallies[home]["d"] += 1
            tallies[away]["d"] += 1

    rows = [
        TableRow(
            club=club,
            played=t["p"],
            won=t["w"],
            drawn=t["d"],
            lost=t["l"],
            goals_for=t["gf"],
            goals_against=t["ga"],
        )
        for club, t in tallies.items()
    ]
    return Projection(
        rows=order_table(rows),
        modelled_per_club=modelled_per_club,
        projected_per_club=projected_per_club,
        derived_fixtures=derived_count,
        modelled_fixtures=modelled_count,
    )


def final_table() -> list[str]:
    """Last season's finishing order, canonical clubs only.

    Used by the prediction preview. The three relegated clubs are dropped, so a
    preview scores against the 17 clubs that appear in both seasons and says so.
    """
    rows = sorted(last_season().get("table", []), key=lambda r: r["position"])
    return [r["club"] for r in rows if r.get("club")]


def comparable_clubs() -> int:
    return len(final_table())
