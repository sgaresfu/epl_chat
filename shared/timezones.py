"""Timezone helpers for the four cities.

Timezones are IANA strings, never fixed offsets. Ukraine, the United States and
Canada change their clocks on different dates, so a stored offset is silently
wrong for a couple of weeks every spring and autumn -- and match day is exactly
when that matters. Every conversion here goes through :mod:`zoneinfo`, which
carries the real DST rules, and formatting goes through the person's own zone.

``local_hour`` is written at insert time on ``watch_log`` for the same reason:
it records the hour as it actually was for that person, so the night medal stays
correct even if a government later changes the rules for that zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class Place:
    """One person's city and the IANA zone it actually keeps time in."""

    key: str
    person: str
    city: str
    region: str
    timezone: str
    country: str

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


PLACES: Final[tuple[Place, ...]] = (
    Place("coyg", "COYG", "Lviv", "Lviv", "Europe/Kyiv", "UA"),
    Place("aure", "AURE", "Michigan", "Michigan", "America/Detroit", "US"),
    Place("twzt", "TWZT", "Alberta", "Alberta", "America/Edmonton", "CA"),
    Place("bulba", "BULBA", "Alaska", "Alaska", "America/Anchorage", "US"),
)

BY_KEY: Final[dict[str, Place]] = {p.key: p for p in PLACES}

NIGHT_MEDAL_START: Final = 0  # midnight, inclusive
NIGHT_MEDAL_END: Final = 5  # 05:00, exclusive


def to_zone(moment: datetime, tz: str) -> datetime:
    """Convert an instant to a named IANA zone.

    A naive datetime is treated as UTC rather than as local machine time -- the
    servers run in UTC and guessing the host's zone is how a one-hour bug gets in.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(ZoneInfo(tz))


def local_hour(moment: datetime, tz: str) -> int:
    """The hour of the day, 0-23, as that person experienced it."""
    return to_zone(moment, tz).hour


def is_night(moment: datetime, tz: str) -> bool:
    """Whether a kickoff falls between midnight and 05:00 in that person's zone.

    This is what earns the night medal on the watch log, and it is why BULBA in
    Alaska and COYG in Lviv can watch the identical match and only one of them
    collect it.
    """
    hour = local_hour(moment, tz)
    return NIGHT_MEDAL_START <= hour < NIGHT_MEDAL_END


def offset_label(moment: datetime, tz: str) -> str:
    """The zone's UTC offset at that instant, e.g. ``UTC+3``.

    Computed per instant, never stored, because the answer changes across a DST
    boundary.
    """
    local = to_zone(moment, tz)
    delta = local.utcoffset()
    if delta is None:  # pragma: no cover - a named zone always has an offset
        return "UTC"
    total_minutes = int(delta.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours}" if not minutes else f"UTC{sign}{hours}:{minutes:02d}"


def abbreviation(moment: datetime, tz: str) -> str:
    """The zone's short name at that instant, e.g. ``EDT`` in summer, ``EST`` in winter."""
    return to_zone(moment, tz).tzname() or offset_label(moment, tz)


@dataclass(frozen=True, slots=True)
class LocalKickoff:
    """A kickoff rendered for one city, ready for the four-city block."""

    place: str
    person: str
    city: str
    timezone: str
    iso: str
    time: str
    weekday: str
    day: str
    offset: str
    abbreviation: str
    is_night: bool
    day_shift: int


def _shift(utc_moment: datetime, local: datetime) -> int:
    """How many calendar days the local date differs from the UTC date.

    A 19:00 UTC kickoff is still the same day in Lviv but the previous
    afternoon in Anchorage; a late kickoff can land on tomorrow's date in Kyiv.
    The UI uses this to print "Sat" against one city and "Sun" against another.
    """
    return (local.date() - utc_moment.astimezone(UTC).date()).days


def local_kickoff(moment: datetime, place: Place) -> LocalKickoff:
    """Render one kickoff for one place, with everything the UI needs."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    local = to_zone(moment, place.timezone)
    return LocalKickoff(
        place=place.key,
        person=place.person,
        city=place.city,
        timezone=place.timezone,
        iso=local.isoformat(),
        time=f"{local.hour:02d}:{local.minute:02d}",
        weekday=local.strftime("%a"),
        day=local.strftime("%-d %b"),
        offset=offset_label(moment, place.timezone),
        abbreviation=abbreviation(moment, place.timezone),
        is_night=is_night(moment, place.timezone),
        day_shift=_shift(moment, local),
    )


def all_kickoffs(moment: datetime) -> tuple[LocalKickoff, ...]:
    """One kickoff rendered for all four cities, in brief order."""
    return tuple(local_kickoff(moment, place) for place in PLACES)
