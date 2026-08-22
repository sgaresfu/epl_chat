"""Calendar tests.

The calendar reads maintained JSON files, not a live API, so these tests write
their own fixture files and repoint ``shared.calendar``'s paths at them.
Assertions must never depend on where real wall-clock "now" sits relative to
the real dates in ``shared/data/calendar.json``, or the suite would start
failing the day those events pass.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from shared import calendar as cal

from tests.conftest import sign_in

EVENTS = {
    "checked_on": "2026-08-22",
    "events": [
        {
            "title": "Far Future Grand Prix",
            "sport": "f1",
            "starts_at": "2027-12-01T13:00:00Z",
            "ends_at": None,
            "time_known": True,
            "venue": "Nowhere",
            "tier": "notable",
            "note": "too far out",
        },
        {
            "title": "Next Weekend Grand Prix",
            "sport": "f1",
            "starts_at": "2026-09-05T13:00:00Z",
            "ends_at": None,
            "time_known": True,
            "venue": "Monza",
            "tier": "major",
            "note": "",
        },
        {
            "title": "Already Happened Fight",
            "sport": "boxing",
            "starts_at": "2026-08-01T03:00:00Z",
            "ends_at": None,
            "time_known": True,
            "venue": "Vegas",
            "tier": "notable",
            "note": "in the past",
        },
        {
            "title": "A Long Major",
            "sport": "golf",
            "starts_at": "2026-08-30T00:00:00Z",
            "ends_at": "2026-09-20T00:00:00Z",
            "time_known": False,
            "venue": "Augusta",
            "tier": "major",
            "note": "",
        },
    ],
}

BROADCAST = {
    "sports": {
        "f1": {
            "UA": {"provider": "Setanta Sports", "url": "https://s.example", "confidence": "verified"},
            "US": {"provider": "Apple TV", "url": "https://a.example", "confidence": "verified"},
            "CA": {"provider": "TSN", "url": "", "confidence": "unverified"},
        },
        "golf": {"US": {"provider": "NBC", "url": "", "confidence": "unverified"}},
        "boxing": {"US": {"provider": "", "url": "", "confidence": "unverified"}},
    },
    "event_overrides": {
        "Next Weekend Grand Prix": {"US": {"provider": "Sky Override", "url": "", "confidence": "verified"}}
    },
}


@pytest.fixture
def calendar_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    events = tmp_path / "calendar.json"
    events.write_text(json.dumps(EVENTS))
    broadcast = tmp_path / "sport_broadcasters.json"
    broadcast.write_text(json.dumps(BROADCAST))
    monkeypatch.setattr(cal, "DATA_FILE", events)
    monkeypatch.setattr(cal, "BROADCAST_FILE", broadcast)
    cal.reload()
    yield events
    cal.reload()


class TestAllEvents:
    def test_events_are_parsed_and_sorted_by_start(self, calendar_files: Path) -> None:
        assert [e.title for e in cal.all_events()] == [
            "Already Happened Fight",
            "A Long Major",
            "Next Weekend Grand Prix",
            "Far Future Grand Prix",
        ]

    def test_a_missing_file_yields_nothing_rather_than_raising(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cal, "DATA_FILE", tmp_path / "missing.json")
        cal.reload()
        assert cal.all_events() == []
        cal.reload()

    def test_multi_day_is_derived_not_stored(self, calendar_files: Path) -> None:
        major = next(e for e in cal.all_events() if e.title == "A Long Major")
        single = next(e for e in cal.all_events() if e.title == "Next Weekend Grand Prix")
        assert major.multi_day is True
        assert single.multi_day is False


class TestUpcoming:
    NOW = datetime(2026, 9, 1, tzinfo=UTC)

    def test_a_finished_event_is_excluded(self, calendar_files: Path) -> None:
        assert "Already Happened Fight" not in [e.title for e in cal.upcoming(self.NOW, days=30)]

    def test_beyond_the_window_is_excluded(self, calendar_files: Path) -> None:
        assert "Far Future Grand Prix" not in [e.title for e in cal.upcoming(self.NOW, days=30)]

    def test_inside_the_window_is_included(self, calendar_files: Path) -> None:
        assert "Next Weekend Grand Prix" in [e.title for e in cal.upcoming(self.NOW, days=30)]

    def test_a_multi_day_event_already_under_way_still_counts_as_upcoming(self, calendar_files: Path) -> None:
        """Dropping the Ashes on its third day would be the wrong answer."""
        names = [e.title for e in cal.upcoming(self.NOW, days=30)]
        assert "A Long Major" in names, "started 30 Aug, ends 20 Sep, so on 1 Sep it is live"

    def test_is_live_is_true_only_inside_the_run(self, calendar_files: Path) -> None:
        major = next(e for e in cal.all_events() if e.title == "A Long Major")
        assert major.is_live(self.NOW) is True
        assert major.is_live(datetime(2026, 8, 1, tzinfo=UTC)) is False
        assert major.is_live(datetime(2026, 10, 1, tzinfo=UTC)) is False

    def test_a_wider_window_admits_the_far_future_event(self, calendar_files: Path) -> None:
        assert "Far Future Grand Prix" in [e.title for e in cal.upcoming(self.NOW, days=600)]


class TestWatch:
    def test_each_market_resolves_its_own_provider(self, calendar_files: Path) -> None:
        gp = next(e for e in cal.all_events() if e.title == "Far Future Grand Prix")
        got = {w.country: w.provider for w in cal.watch_for(gp, ("UA", "US", "CA"))}
        assert got == {"UA": "Setanta Sports", "US": "Apple TV", "CA": "TSN"}

    def test_an_event_override_beats_the_sport_default(self, calendar_files: Path) -> None:
        gp = next(e for e in cal.all_events() if e.title == "Next Weekend Grand Prix")
        got = {w.country: w.provider for w in cal.watch_for(gp, ("UA", "US", "CA"))}
        assert got["US"] == "Sky Override", "the per-event override must win"
        assert got["UA"] == "Setanta Sports", "and must not disturb the other markets"

    def test_confidence_is_carried_through(self, calendar_files: Path) -> None:
        gp = next(e for e in cal.all_events() if e.title == "Far Future Grand Prix")
        got = {w.country: w.confidence for w in cal.watch_for(gp, ("UA", "US", "CA"))}
        assert got == {"UA": "verified", "US": "verified", "CA": "unverified"}

    def test_a_market_with_no_listing_is_omitted_not_blank(self, calendar_files: Path) -> None:
        major = next(e for e in cal.all_events() if e.title == "A Long Major")
        assert [w.country for w in cal.watch_for(major, ("UA", "US", "CA"))] == ["US"]

    def test_an_empty_provider_string_is_omitted(self, calendar_files: Path) -> None:
        fight = next(e for e in cal.all_events() if e.title == "Already Happened Fight")
        assert cal.watch_for(fight, ("UA", "US", "CA")) == []

    def test_a_sport_with_no_broadcast_row_yields_nothing(self, calendar_files: Path) -> None:
        from shared.calendar import CalendarEvent

        unknown = CalendarEvent(
            title="x",
            sport="kabaddi",
            starts_at=datetime.now(UTC),
            ends_at=None,
            time_known=True,
            venue="",
            tier="notable",
            note="",
        )
        assert cal.watch_for(unknown, ("UA", "US", "CA")) == []


class TestSportLabels:
    def test_known_slugs_get_a_real_name(self) -> None:
        assert cal.sport_label("f1") == "Formula 1"
        assert cal.sport_label("horse-racing") == "Horse racing"

    def test_an_unknown_slug_is_humanised_rather_than_shown_raw(self) -> None:
        assert cal.sport_label("beach-volleyball") == "Beach Volleyball"


class TestShippedData:
    """The real file, not a fixture — it is the product, so it gets checked."""

    def test_it_parses(self) -> None:
        assert len(cal.all_events()) > 30

    def test_every_event_has_a_known_sport_label(self) -> None:
        unknown = {e.sport for e in cal.all_events() if e.sport not in cal.SPORT_LABELS}
        assert unknown == set(), f"sports missing a display label: {unknown}"

    def test_no_football(self) -> None:
        """The brief gives football the rest of the site; this page is everything else."""
        banned = {"football", "soccer"}
        assert not [e for e in cal.all_events() if e.sport in banned]
        for event in cal.all_events():
            assert "premier league" not in event.title.lower()
            assert "champions league" not in event.title.lower()

    def test_multi_day_events_end_after_they_start(self) -> None:
        for e in cal.all_events():
            if e.ends_at is not None:
                assert e.ends_at >= e.starts_at, f"{e.title} ends before it starts"

    def test_every_tier_is_one_of_the_two_the_ui_styles(self) -> None:
        assert {e.tier for e in cal.all_events()} <= {"major", "notable"}

    def test_every_sport_has_at_least_one_market_listed(self) -> None:
        """A sport nobody can watch anywhere is a gap in the broadcast table."""
        missing = {e.sport for e in cal.all_events() if not cal.watch_for(e, ("UA", "US", "CA"))}
        assert missing == set(), f"no where-to-watch for: {missing}"


class TestEndpoint:
    """These hit the route's own ``datetime.now(UTC)``, so the fixture dates are
    computed relative to real now rather than a fixed literal.
    """

    @pytest.fixture
    def near_future(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        soon = datetime.now(UTC) + timedelta(days=5)
        events = tmp_path / "calendar.json"
        events.write_text(
            json.dumps(
                {
                    "checked_on": "2026-08-22",
                    "events": [
                        {
                            "title": "Imminent Grand Prix",
                            "sport": "f1",
                            "starts_at": soon.isoformat().replace("+00:00", "Z"),
                            "ends_at": None,
                            "time_known": True,
                            "venue": "Monza",
                            "tier": "major",
                            "note": "",
                        }
                    ],
                }
            )
        )
        broadcast = tmp_path / "sport_broadcasters.json"
        broadcast.write_text(json.dumps(BROADCAST))
        monkeypatch.setattr(cal, "DATA_FILE", events)
        monkeypatch.setattr(cal, "BROADCAST_FILE", broadcast)
        cal.reload()
        yield events
        cal.reload()

    async def test_it_needs_a_session(self, client: AsyncClient) -> None:
        assert (await client.get("/api/calendar")).status_code == 401

    async def test_a_timed_event_carries_four_city_times(
        self, client: AsyncClient, near_future: Path
    ) -> None:
        await sign_in(client)
        body = (await client.get("/api/calendar")).json()
        assert body["events"]
        assert len(body["events"][0]["local_times"]) == 4

    async def test_it_carries_where_to_watch_per_market(self, client: AsyncClient, near_future: Path) -> None:
        await sign_in(client)
        event = (await client.get("/api/calendar")).json()["events"][0]
        cities = {w["city"] for w in event["watch"]}
        assert cities == {"Lviv", "Michigan", "Alberta", "Alaska"}, (
            "all four people get a listing — two of them share the US market, and "
            "keying this by country silently dropped one of them"
        )

    async def test_watch_rows_carry_the_key_the_ui_compares_against(
        self, client: AsyncClient, near_future: Path
    ) -> None:
        """A regression test. ``WatchOn`` originally carried only the display
        name ("COYG"), but every component compares against ``me.person.key``
        ("coyg") -- so no city was ever marked as yours, and worse, the "your
        time" lookup fell through to ``local_times[0]``, labelling Lviv's clock
        as Michigan's for AURE. Both halves are checked here.
        """
        await sign_in(client, "aure")
        event = (await client.get("/api/calendar")).json()["events"][0]

        mine = [w for w in event["watch"] if w["place"] == "aure"]
        assert len(mine) == 1, "AURE's own row must be findable by key"
        assert mine[0]["city"] == "Michigan"
        assert mine[0]["person"] == "AURE", "the display name is still carried, just not used for matching"

        slot = next(t for t in event["local_times"] if t["place"] == "aure")
        assert slot["city"] == "Michigan"
        assert slot["timezone"] == "America/Detroit"

    async def test_a_dateless_event_gets_no_invented_clock_times(self, client: AsyncClient) -> None:
        """A four-day major has no kickoff; converting one would invent precision."""
        await sign_in(client)
        body = (await client.get("/api/calendar")).json()
        for event in body["events"]:
            if not event["time_known"]:
                assert event["local_times"] == [], event["title"]

    async def test_the_sport_filter_narrows_the_list(self, client: AsyncClient) -> None:
        await sign_in(client)
        everything = (await client.get("/api/calendar?days=400")).json()
        f1_only = (await client.get("/api/calendar?days=400&sport=f1")).json()
        assert len(f1_only["events"]) < len(everything["events"])
        assert {e["sport"] for e in f1_only["events"]} == {"f1"}

    async def test_the_filter_list_survives_filtering(self, client: AsyncClient) -> None:
        """Choosing a sport must not make the other chips vanish."""
        await sign_in(client)
        body = (await client.get("/api/calendar?days=400&sport=f1")).json()
        assert len(body["sports"]) > 1

    async def test_an_unknown_sport_explains_itself(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/calendar?sport=kabaddi")).json()
        assert body["events"] == []
        assert body["empty_message"]

    async def test_an_empty_window_explains_itself(
        self, client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cal, "DATA_FILE", tmp_path / "missing.json")
        cal.reload()
        try:
            await sign_in(client)
            body = (await client.get("/api/calendar")).json()
            assert body["events"] == []
            assert body["empty_message"]
        finally:
            cal.reload()

    async def test_days_is_bounded(self, client: AsyncClient) -> None:
        await sign_in(client)
        assert (await client.get("/api/calendar?days=0")).status_code == 422
        assert (await client.get("/api/calendar?days=99999")).status_code == 422
