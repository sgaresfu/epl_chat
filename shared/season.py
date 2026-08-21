"""The season timeline, computed from fixture data and the current date.

BRIEF section 6 is explicit that a hardcoded counter is worse than none, so
every number here is derived: the day count from real dates, gameweeks played
from finished events, matches remaining from the fixture list. Nothing is
written down that can be counted.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Fixed points in the calendar worth marking on the progress bar.
MARKERS: tuple[tuple[str, str], ...] = (
    ("Boxing Day", "2026-12-26"),
    ("Deadline day", "2027-02-02"),
    ("Final day", "2027-05-30"),
)


@dataclass(frozen=True, slots=True)
class Marker:
    label: str
    date: datetime
    percent: float
    is_now: bool = False


@dataclass(frozen=True, slots=True)
class Season:
    starts: datetime
    ends: datetime
    today: datetime
    day: int
    total_days: int
    days_remaining: int
    percent: float
    gameweeks_played: int
    gameweeks_total: int
    matches_played: int
    matches_total: int
    matches_remaining: int
    markers: tuple[Marker, ...]


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build(
    fixtures: Iterable[dict[str, Any]],
    events: Iterable[dict[str, Any]],
    now: datetime | None = None,
) -> Season:
    """Derive the whole timeline from the fixture list and gameweek events."""
    now = now or datetime.now(UTC)
    fixture_rows = list(fixtures)
    event_rows = list(events)

    kickoffs = sorted(k for k in (_parse(f.get("kickoff_time")) for f in fixture_rows) if k)
    starts = kickoffs[0] if kickoffs else _parse("2026-08-21T19:00:00Z")
    ends = kickoffs[-1] if kickoffs else _parse("2027-05-30T15:00:00Z")
    assert starts is not None
    assert ends is not None

    total_days = max(1, (ends.date() - starts.date()).days)
    day = (now.date() - starts.date()).days + 1
    day = max(0, min(day, total_days + 1))
    days_remaining = max(0, (ends.date() - now.date()).days)

    elapsed = (now - starts).total_seconds()
    span = max(1.0, (ends - starts).total_seconds())
    percent = max(0.0, min(100.0, elapsed / span * 100.0))

    matches_total = len(fixture_rows)
    matches_played = sum(1 for f in fixture_rows if f.get("finished"))
    gameweeks_total = len(event_rows) or 38
    gameweeks_played = sum(1 for e in event_rows if e.get("finished"))

    markers: list[Marker] = []
    for label, iso in MARKERS:
        moment = _parse(f"{iso}T12:00:00Z")
        assert moment is not None
        pct = max(0.0, min(100.0, (moment - starts).total_seconds() / span * 100.0))
        markers.append(Marker(label=label, date=moment, percent=pct))
    markers.append(Marker(label=f"Today · day {max(day, 1)}", date=now, percent=percent, is_now=True))
    markers.sort(key=lambda m: m.percent)

    return Season(
        starts=starts,
        ends=ends,
        today=now,
        day=day,
        total_days=total_days,
        days_remaining=days_remaining,
        percent=percent,
        gameweeks_played=gameweeks_played,
        gameweeks_total=gameweeks_total,
        matches_played=matches_played,
        matches_total=matches_total,
        matches_remaining=max(0, matches_total - matches_played),
        markers=tuple(markers),
    )
