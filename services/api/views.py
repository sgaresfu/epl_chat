"""Turn cached upstream payloads into API responses.

This is where the brief's three states live. Every builder returns a
:class:`Freshness` saying where the data came from and how old it is, and an
``empty_message`` that explains what will appear and when rather than saying
"No data". A panel with no data is an instruction, not an apology.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from shared import broadcasters
from shared.cache import Entry
from shared.clubs import CLUBS, Club, by_fpl_id
from shared.db import OddsHistory
from shared.keys import TTL
from shared.models import (
    ClubOut,
    FixtureListOut,
    FixtureOut,
    Freshness,
    LocalTimeOut,
    OddsPrice,
    TableOut,
    TableRowOut,
)
from shared.timezones import PLACES, local_kickoff

from services.poller.fpl import TableRow, compute_table, is_over

# Fixtures worth a badge. Keyed by the pair of canonical short names.
DERBIES: dict[frozenset[str], str] = {
    frozenset({"ARS", "TOT"}): "North London derby",
    frozenset({"LIV", "EVE"}): "Merseyside derby",
    frozenset({"MUN", "MCI"}): "Manchester derby",
    frozenset({"CHE", "TOT"}): "London derby",
    frozenset({"ARS", "CHE"}): "London derby",
    frozenset({"LIV", "MUN"}): "North West derby",
    frozenset({"CRY", "BHA"}): "M23 derby",
    frozenset({"AVL", "NFO"}): "Midlands derby",
    frozenset({"COV", "AVL"}): "Midlands derby",
    frozenset({"FUL", "CHE"}): "West London derby",
    frozenset({"NEW", "SUN"}): "Tyne-Wear derby",
    frozenset({"LEE", "HUL"}): "Yorkshire derby",
}


def club_out(club: Club) -> ClubOut:
    return ClubOut(
        short_name=club.short_name,
        name=club.name,
        full_name=club.full_name,
        primary=club.primary,
        on_primary=club.on_primary,
        fpl_id=club.fpl_id,
    )


def freshness(entry: Entry | None, cache_key: str, reason: str | None = None) -> Freshness:
    """Describe a cache entry's age, or explain why there is none."""
    if entry is None:
        return Freshness(
            source="none",
            age_seconds=0.0,
            stale=True,
            available=False,
            reason=reason or "Waiting for the first update from the poller.",
        )
    ttl = TTL.get(cache_key, 300)
    return Freshness(
        source=entry.source,
        age_seconds=round(entry.age_seconds, 1),
        stale=entry.is_stale(ttl),
    )


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# --------------------------------------------------------------------------
# Table
# --------------------------------------------------------------------------


def build_table(
    fixtures: list[dict[str, Any]] | None,
    entry: Entry | None,
    cache_key: str,
    gameweek: int = 0,
) -> TableOut:
    """The live table, computed from finished fixtures.

    Before a ball is kicked this is 20 clubs on zero points, and it says so --
    the brief calls that out explicitly as a state to ship, not an edge case.
    """
    if fixtures is None:
        return TableOut(
            rows=[],
            gameweek=gameweek,
            matches_played=0,
            season_started=False,
            freshness=freshness(entry, cache_key),
            empty_message="The table appears once fixtures have loaded.",
        )

    rows = compute_table(fixtures)
    played = sum(r.played for r in rows) // 2
    started = played > 0

    return TableOut(
        rows=[_table_row(index + 1, row) for index, row in enumerate(rows)],
        gameweek=gameweek,
        matches_played=played,
        season_started=started,
        freshness=freshness(entry, cache_key),
        empty_message=(
            None
            if started
            else "Nobody has played yet. All 20 clubs start on zero points; "
            "the table orders itself the moment the first match finishes."
        ),
    )


def _table_row(position: int, row: TableRow, modelled: bool = False, note: str | None = None) -> TableRowOut:
    from shared.clubs import BY_SHORT_NAME

    return TableRowOut(
        position=position,
        club=club_out(BY_SHORT_NAME[row.club]),
        played=row.played,
        won=row.won,
        drawn=row.drawn,
        lost=row.lost,
        goals_for=row.goals_for,
        goals_against=row.goals_against,
        goal_difference=row.goal_difference,
        points=row.points,
        form=list(row.form),
        modelled=modelled,
        note=note,
    )


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def local_times(kickoff: datetime | None) -> list[LocalTimeOut]:
    """One kickoff rendered for all four cities, each with its broadcaster."""
    if kickoff is None:
        return []
    out: list[LocalTimeOut] = []
    for place in PLACES:
        k = local_kickoff(kickoff, place)
        listing = broadcasters.for_country(place.country)
        out.append(
            LocalTimeOut(
                place=k.place,
                person=k.person,
                city=k.city,
                timezone=k.timezone,
                iso=datetime.fromisoformat(k.iso),
                time=k.time,
                weekday=k.weekday,
                day=k.day,
                offset=k.offset,
                abbreviation=k.abbreviation,
                is_night=k.is_night,
                day_shift=k.day_shift,
                broadcaster=listing.provider if listing else None,
                broadcaster_url=listing.url if listing else None,
                verified_on=listing.verified_on if listing else None,
            )
        )
    return out


def derby_for(home: Club, away: Club) -> str | None:
    return DERBIES.get(frozenset({home.short_name, away.short_name}))


def build_fixture(
    row: dict[str, Any],
    odds: OddsPrice | None = None,
    watched_by: Iterable[str] = (),
    now: datetime | None = None,
) -> FixtureOut:
    now = now or datetime.now(UTC)
    home = by_fpl_id(int(row["team_h"]))
    away = by_fpl_id(int(row["team_a"]))
    kickoff = _parse(row.get("kickoff_time"))

    # Not row["finished"]: FPL leaves that false until bonus points are
    # confirmed, so a match that ended an hour ago still read as live.
    finished = is_over(row)
    started = bool(row.get("started"))
    # FPL flags a postponed match by clearing its kickoff while keeping the row.
    postponed = kickoff is None and not finished

    return FixtureOut(
        id=int(row["id"]),
        gameweek=int(row.get("event") or 0),
        kickoff=kickoff,
        home=club_out(home),
        away=club_out(away),
        home_score=row.get("team_h_score"),
        away_score=row.get("team_a_score"),
        started=started,
        finished=finished,
        postponed=postponed,
        minutes=int(row.get("minutes") or 0),
        local_times=local_times(kickoff),
        odds=odds,
        derby=derby_for(home, away),
        watched_by=list(watched_by),
        watch_open=watch_window_open(kickoff, finished, now),
    )


def build_odds_for_row(
    row: dict[str, Any],
    odds_cache: dict[str, Any] | None,
    history: Sequence[OddsHistory],
    now: datetime,
) -> OddsPrice:
    """The live bet365 price for one fixture, with a week's drift where there's history for it.

    ``drift`` carries each outcome's price from a week ago (or the earliest
    record, if the history is younger than that); the frontend pairs it with
    the live price above to render "1.40 → 1.65".
    """
    if odds_cache is None:
        return OddsPrice(available=False, reason="Odds have not been fetched yet.")

    home = by_fpl_id(int(row["team_h"]))
    away = by_fpl_id(int(row["team_a"]))
    match = odds_cache.get(f"{home.short_name}-{away.short_name}")
    if not isinstance(match, dict) or not match.get("available"):
        reason = match.get("reason") if isinstance(match, dict) else None
        return OddsPrice(available=False, reason=reason or "bet365 has no listed price for this match.")

    drift: dict[str, float] | None = None
    if len(history) >= 2:
        # SQLite (used in dev and tests) hands back a naive datetime for a
        # `DateTime(timezone=True)` column even though the value stored is
        # always UTC; Postgres does not have this quirk. Same fix as
        # services/api/routes/chat.py's poll open/close comparisons.
        week_ago = now - timedelta(days=7)
        captured_at = [
            h.captured_at if h.captured_at.tzinfo else h.captured_at.replace(tzinfo=UTC) for h in history
        ]
        baseline_index = next((i for i, c in enumerate(captured_at) if c >= week_ago), 0)
        baseline = history[baseline_index]
        if baseline is not history[-1]:
            drift = {"home": baseline.home, "draw": baseline.draw, "away": baseline.away}

    return OddsPrice(
        home=match.get("home"),
        draw=match.get("draw"),
        away=match.get("away"),
        bookmaker=str(match.get("bookmaker") or "bet365"),
        captured_at=history[-1].captured_at if history else None,
        drift=drift,
        market_max=match.get("market_max"),
        available=True,
    )


def watch_window_open(kickoff: datetime | None, finished: bool, now: datetime) -> bool:
    """ "I watched this" opens at kickoff and closes 12 hours after full time.

    Full time is approximated as two hours after kickoff, so the window is
    kickoff to kickoff + 14 hours. Enforced server-side on every toggle.
    """
    if kickoff is None:
        return False
    if now < kickoff:
        return False
    return (now - kickoff).total_seconds() <= 14 * 3600


def build_fixture_list(
    fixtures: list[dict[str, Any]] | None,
    entry: Entry | None,
    cache_key: str,
    watched_by_fixture: dict[int, list[str]] | None = None,
    odds_by_fixture: dict[int, OddsPrice] | None = None,
    **kwargs: Any,
) -> FixtureListOut:
    if not fixtures:
        return FixtureListOut(
            fixtures=[],
            freshness=freshness(entry, cache_key),
            empty_message="Fixtures appear as soon as the poller has loaded the schedule.",
        )
    watched = watched_by_fixture or {}
    odds_map = odds_by_fixture or {}
    return FixtureListOut(
        fixtures=[
            build_fixture(
                row,
                odds=odds_map.get(int(row["id"])),
                watched_by=watched.get(int(row["id"]), []),
                **kwargs,
            )
            for row in fixtures
        ],
        freshness=freshness(entry, cache_key),
    )


def all_clubs() -> list[ClubOut]:
    return [club_out(c) for c in CLUBS]
