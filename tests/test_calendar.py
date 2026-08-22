"""Calendar tests.

The calendar reads a maintained JSON file, not a live API, so these tests
write their own fixture file and point ``shared.calendar.DATA_FILE`` at it --
assertions must never depend on where real wall-clock "now" sits relative to
the actual F1/boxing dates in ``shared/data/calendar.json``, or the suite
would start failing the day those events pass.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.conftest import sign_in

EVENTS = {
    "events": [
        {
            "title": "Far Future Grand Prix",
            "category": "f1",
            "starts_at": "2026-12-01T13:00:00Z",
            "note": "too far out",
        },
        {
            "title": "Next Weekend Grand Prix",
            "category": "f1",
            "starts_at": "2026-09-05T13:00:00Z",
            "note": "",
        },
        {
            "title": "Already Happened Fight Night",
            "category": "boxing",
            "starts_at": "2026-08-01T03:00:00Z",
            "note": "in the past",
        },
        {
            "title": "UFC Somewhere",
            "category": "ufc",
            "starts_at": "2026-09-10T22:00:00Z",
            "note": "",
        },
    ]
}


@pytest.fixture
def calendar_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps(EVENTS))
    monkeypatch.setattr("shared.calendar.DATA_FILE", path)
    return path


class TestAllEvents:
    def test_events_are_parsed(self, calendar_file: Path) -> None:
        from shared.calendar import all_events

        events = all_events()
        assert len(events) == 4

    def test_events_come_back_sorted_by_start(self, calendar_file: Path) -> None:
        from shared.calendar import all_events

        events = all_events()
        assert [e.title for e in events] == [
            "Already Happened Fight Night",
            "Next Weekend Grand Prix",
            "UFC Somewhere",
            "Far Future Grand Prix",
        ]

    def test_a_missing_file_yields_nothing_rather_than_raising(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from shared.calendar import all_events

        monkeypatch.setattr("shared.calendar.DATA_FILE", tmp_path / "missing.json")
        assert all_events() == []


class TestUpcoming:
    NOW = datetime(2026, 9, 1, tzinfo=UTC)

    def test_the_past_is_excluded(self, calendar_file: Path) -> None:
        from shared.calendar import upcoming

        titles = [e.title for e in upcoming(self.NOW)]
        assert "Already Happened Fight Night" not in titles

    def test_far_future_beyond_the_window_is_excluded(self, calendar_file: Path) -> None:
        from shared.calendar import upcoming

        titles = [e.title for e in upcoming(self.NOW, days=30)]
        assert "Far Future Grand Prix" not in titles

    def test_events_inside_the_window_are_included(self, calendar_file: Path) -> None:
        from shared.calendar import upcoming

        titles = [e.title for e in upcoming(self.NOW, days=30)]
        assert "Next Weekend Grand Prix" in titles
        assert "UFC Somewhere" in titles

    def test_a_wider_window_admits_the_far_future_event(self, calendar_file: Path) -> None:
        from shared.calendar import upcoming

        titles = [e.title for e in upcoming(self.NOW, days=120)]
        assert "Far Future Grand Prix" in titles


class TestEndpoint:
    """These hit the route's own ``datetime.now(UTC)``, so unlike the tests
    above the fixture dates are computed relative to *real* now rather than a
    fixed literal -- otherwise the suite would start failing the day real
    wall-clock time passed the literal dates.
    """

    @pytest.fixture
    def near_future_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        soon = datetime.now(UTC) + timedelta(days=5)
        path = tmp_path / "calendar.json"
        path.write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "title": "Imminent Grand Prix",
                            "category": "f1",
                            "starts_at": soon.isoformat().replace("+00:00", "Z"),
                            "note": "",
                        }
                    ]
                }
            )
        )
        monkeypatch.setattr("shared.calendar.DATA_FILE", path)
        return path

    async def test_it_needs_a_session(self, client: AsyncClient) -> None:
        assert (await client.get("/api/calendar")).status_code == 401

    async def test_events_carry_four_city_local_times(
        self, client: AsyncClient, near_future_file: Path
    ) -> None:
        await sign_in(client)
        body = (await client.get("/api/calendar")).json()
        assert body["events"], "the fixture file has an event inside the default 30-day window"
        assert len(body["events"][0]["local_times"]) == 4

    async def test_an_empty_window_explains_itself(
        self, client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("shared.calendar.DATA_FILE", tmp_path / "missing.json")
        await sign_in(client)
        body = (await client.get("/api/calendar")).json()
        assert body["events"] == []
        assert body["empty_message"]
