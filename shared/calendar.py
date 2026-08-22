"""The other-sport calendar: everything worth clearing an evening for, bar football.

Read from ``shared/data/calendar.json`` and ``shared/data/sport_broadcasters.json``
-- maintained files rather than a live API, because no free sports-calendar API
covers this many disciplines and the ones that come close are community-run with
no stability guarantee. See each file's ``$comment`` for provenance.

Two things here are deliberate rather than incidental:

**Not every event has a start time.** A Grand Prix does; a four-day golf major
does not, and the Ashes runs for five days. Inventing a kickoff for those would
be a lie the four-city clock block then renders very precisely, so
``time_known`` gates the conversion and the UI shows a date range instead.

**Broadcast rights are per-sport, with per-event overrides.** F1 is on one
provider all season; the Super Bowl rotates networks. Every listing carries the
confidence it was recorded with, so an unverified guess is labelled rather than
presented as fact -- the same rule ``shared/broadcasters.py`` follows for
football.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).parent / "data" / "calendar.json"
BROADCAST_FILE = Path(__file__).parent / "data" / "sport_broadcasters.json"

# Display names for the sport slugs used in the data files.
SPORT_LABELS: dict[str, str] = {
    "f1": "Formula 1",
    "motorsport": "Motorsport",
    "motogp": "MotoGP",
    "tennis": "Tennis",
    "golf": "Golf",
    "boxing": "Boxing",
    "ufc": "UFC",
    "nfl": "NFL",
    "nba": "NBA",
    "basketball": "Basketball",
    "nhl": "NHL",
    "mlb": "Baseball",
    "rugby": "Rugby",
    "cricket": "Cricket",
    "cycling": "Cycling",
    "athletics": "Athletics",
    "darts": "Darts",
    "snooker": "Snooker",
    "horse-racing": "Horse racing",
}


def sport_label(sport: str) -> str:
    return SPORT_LABELS.get(sport, sport.replace("-", " ").title())


@dataclass(frozen=True, slots=True)
class Watch:
    """Where one market can watch one event."""

    country: str
    provider: str
    url: str
    confidence: str


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    title: str
    sport: str
    starts_at: datetime
    ends_at: datetime | None
    time_known: bool
    venue: str
    tier: str
    note: str

    @property
    def multi_day(self) -> bool:
        return self.ends_at is not None and self.ends_at.date() > self.starts_at.date()

    def is_live(self, now: datetime) -> bool:
        """Whether a multi-day event is currently under way."""
        if self.ends_at is None:
            return False
        return self.starts_at <= now <= self.ends_at + timedelta(days=1)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    if not DATA_FILE.exists():  # pragma: no cover - shipped with the repo
        return {"events": []}
    data = json.loads(DATA_FILE.read_text())
    assert isinstance(data, dict)
    return data


@lru_cache(maxsize=1)
def _broadcast() -> dict[str, Any]:
    if not BROADCAST_FILE.exists():  # pragma: no cover - shipped with the repo
        return {"sports": {}, "event_overrides": {}}
    data = json.loads(BROADCAST_FILE.read_text())
    assert isinstance(data, dict)
    return data


def reload() -> None:
    """Drop the cached files. Tests repoint the paths, so they need this."""
    _raw.cache_clear()
    _broadcast.cache_clear()


def all_events() -> list[CalendarEvent]:
    events = [
        CalendarEvent(
            title=row["title"],
            sport=row.get("sport", "other"),
            starts_at=_parse(row["starts_at"]),
            ends_at=_parse(row["ends_at"]) if row.get("ends_at") else None,
            time_known=bool(row.get("time_known")),
            venue=row.get("venue", ""),
            tier=row.get("tier", "notable"),
            note=row.get("note", ""),
        )
        for row in _raw().get("events", [])
    ]
    return sorted(events, key=lambda e: (e.starts_at, e.title))


def upcoming(now: datetime, days: int = 120) -> list[CalendarEvent]:
    """Everything still to come inside the window.

    A multi-day event already under way still counts as upcoming -- the Ashes
    in its third day has not finished, and dropping it the moment it started
    would be the wrong answer.
    """
    cutoff = now + timedelta(days=days)
    out: list[CalendarEvent] = []
    for event in all_events():
        end = event.ends_at or event.starts_at
        if end + timedelta(days=1) < now:
            continue
        if event.starts_at > cutoff:
            continue
        out.append(event)
    return out


def watch_for(event: CalendarEvent, countries: tuple[str, ...]) -> list[Watch]:
    """Where each market can watch this event, with per-event overrides applied."""
    table = _broadcast()
    per_sport = table.get("sports", {}).get(event.sport, {})
    override = table.get("event_overrides", {}).get(event.title, {})

    out: list[Watch] = []
    for country in countries:
        listing = override.get(country) or per_sport.get(country)
        if not listing:
            continue
        provider = str(listing.get("provider", "")).strip()
        if not provider:
            continue
        out.append(
            Watch(
                country=country,
                provider=provider,
                url=str(listing.get("url", "")),
                confidence=str(listing.get("confidence", "unverified")),
            )
        )
    return out


def checked_on() -> str:
    return str(_raw().get("checked_on", ""))
