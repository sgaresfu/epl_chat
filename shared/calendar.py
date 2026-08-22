"""The other-sport calendar: F1 weekends, boxing and UFC cards, big finals.

Read from :data:`shared/data/calendar.json`, a maintained file rather than a
live API -- F1's only free calendar API is community-run with no stability
guarantee, and boxing/UFC have no free API at all. See that file's
``$comment`` for provenance and how stale it might be.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

DATA_FILE = Path(__file__).parent / "data" / "calendar.json"

Category = Literal["f1", "boxing", "ufc", "other"]


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    title: str
    category: Category
    starts_at: datetime
    note: str = ""


def all_events() -> list[CalendarEvent]:
    if not DATA_FILE.exists():  # pragma: no cover - shipped with the repo
        return []
    data = json.loads(DATA_FILE.read_text())
    events = [
        CalendarEvent(
            title=row["title"],
            category=row["category"],
            starts_at=datetime.fromisoformat(row["starts_at"].replace("Z", "+00:00")),
            note=row.get("note", ""),
        )
        for row in data.get("events", [])
    ]
    return sorted(events, key=lambda e: e.starts_at)


def upcoming(now: datetime, days: int = 30) -> list[CalendarEvent]:
    """Everything starting between now and ``days`` from now."""
    cutoff = now + timedelta(days=days)
    return [e for e in all_events() if now <= e.starts_at <= cutoff]
