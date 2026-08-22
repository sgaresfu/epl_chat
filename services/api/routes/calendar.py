"""Other sport: everything worth clearing an evening for, bar football."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query
from shared import calendar as calendar_data
from shared.models import CalendarEventOut, CalendarOut, WatchOn
from shared.timezones import PLACES

from services.api import views
from services.api.deps import CurrentSession

router = APIRouter(tags=["calendar"])

# The three markets the four people actually live in.
COUNTRIES: tuple[str, ...] = ("UA", "US", "CA")


@router.get("/api/calendar", response_model=CalendarOut)
async def calendar(
    _: CurrentSession,
    days: int = Query(120, ge=1, le=730),
    sport: str | None = Query(None),
) -> CalendarOut:
    now = datetime.now(UTC)
    events = calendar_data.upcoming(now, days=days)

    # The filter list is built before filtering, so choosing a sport does not
    # make the other chips disappear from under the cursor.
    sports = sorted({e.sport for e in events})
    if sport:
        events = [e for e in events if e.sport == sport]

    if not events:
        return CalendarOut(
            sports=sports,
            checked_on=calendar_data.checked_on(),
            empty_message=(
                f"Nothing else on in the next {days} days."
                if not sport
                else f"No {calendar_data.sport_label(sport)} in the next {days} days."
            ),
        )

    out: list[CalendarEventOut] = []
    for event in events:
        # One row per person, not per country. Two of the four live in the US,
        # so keying this by country drops whichever of Michigan and Alaska is
        # not last in the dict -- and that person never sees where to watch.
        by_country = {w.country: w for w in calendar_data.watch_for(event, COUNTRIES)}
        watch: list[WatchOn] = []
        for place in PLACES:
            listing = by_country.get(place.country)
            if listing is None:
                continue
            watch.append(
                WatchOn(
                    place=place.key,
                    country=listing.country,
                    city=place.city,
                    person=place.person,
                    provider=listing.provider,
                    url=listing.url,
                    confidence=listing.confidence,
                )
            )

        out.append(
            CalendarEventOut(
                title=event.title,
                sport=event.sport,
                sport_label=calendar_data.sport_label(event.sport),
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                time_known=event.time_known,
                multi_day=event.multi_day,
                in_progress=event.is_live(now),
                days_until=max(0, (event.starts_at.date() - now.date()).days),
                venue=event.venue,
                tier=event.tier,  # type: ignore[arg-type]
                note=event.note,
                # A four-day major has no single kickoff, so converting one into
                # four city clocks would be inventing precision that isn't there.
                local_times=views.local_times(event.starts_at) if event.time_known else [],
                watch=watch,
            )
        )

    return CalendarOut(events=out, sports=sports, checked_on=calendar_data.checked_on())
