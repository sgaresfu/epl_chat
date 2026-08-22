"""Other sport: F1 weekends, boxing and UFC cards, big finals -- next 30 days."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from shared import calendar as calendar_data
from shared.models import CalendarEventOut, CalendarOut

from services.api import views
from services.api.deps import CurrentSession

router = APIRouter(tags=["calendar"])


@router.get("/api/calendar", response_model=CalendarOut)
async def calendar(_: CurrentSession) -> CalendarOut:
    events = calendar_data.upcoming(datetime.now(UTC))
    if not events:
        return CalendarOut(empty_message="Nothing else on in the next 30 days.")
    return CalendarOut(
        events=[
            CalendarEventOut(
                title=event.title,
                category=event.category,
                starts_at=event.starts_at,
                note=event.note,
                local_times=views.local_times(event.starts_at),
            )
            for event in events
        ]
    )
