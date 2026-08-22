"""Watch log tests.

The window is the rule: marking opens at kickoff and closes twelve hours after
full time, enforced on the server. A disabled button is a hint, not a
constraint, and the brief is explicit that the check belongs here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import ASGITransport, AsyncClient
from services.api.views import watch_window_open
from shared.cache import MemoryCache
from shared.config import Settings
from shared.timezones import is_night, local_hour

from tests.conftest import CODES, _build_app, sign_in

OPENER = 1  # Arsenal v Coventry, 2026-08-21T19:00:00Z


class TestWindow:
    def test_the_window_is_shut_before_kickoff(self) -> None:
        kickoff = datetime(2026, 8, 21, 19, tzinfo=UTC)
        assert watch_window_open(kickoff, False, kickoff - timedelta(minutes=1)) is False

    def test_it_opens_at_kickoff(self) -> None:
        kickoff = datetime(2026, 8, 21, 19, tzinfo=UTC)
        assert watch_window_open(kickoff, False, kickoff) is True

    def test_it_is_open_during_the_match(self) -> None:
        kickoff = datetime(2026, 8, 21, 19, tzinfo=UTC)
        assert watch_window_open(kickoff, False, kickoff + timedelta(hours=1)) is True

    def test_it_is_still_open_twelve_hours_after_full_time(self) -> None:
        # Full time is two hours after kickoff, so the window runs to +14h.
        kickoff = datetime(2026, 8, 21, 19, tzinfo=UTC)
        assert watch_window_open(kickoff, True, kickoff + timedelta(hours=13)) is True

    def test_it_closes_after_that(self) -> None:
        kickoff = datetime(2026, 8, 21, 19, tzinfo=UTC)
        assert watch_window_open(kickoff, True, kickoff + timedelta(hours=15)) is False

    def test_a_postponed_match_with_no_kickoff_is_never_open(self) -> None:
        assert watch_window_open(None, False, datetime.now(UTC)) is False


class TestToggleIsServerChecked:
    async def test_marking_before_kickoff_is_refused(self, future_client: AsyncClient) -> None:
        # Against fixtures that have not kicked off, whenever this is run.
        await sign_in(future_client, "coyg")
        response = await future_client.post(
            "/api/watch",
            json={"fixture_id": OPENER},
            headers={"X-CSRF-Token": future_client.cookies.get("pl_csrf") or ""},
        )
        assert response.status_code == 409
        assert "not kicked off" in response.json()["detail"]

    async def test_it_requires_a_csrf_token(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        response = await client.post("/api/watch", json={"fixture_id": OPENER})
        assert response.status_code == 403

    async def test_an_unknown_fixture_is_a_404(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        response = await client.post(
            "/api/watch",
            json={"fixture_id": 999999},
            headers={"X-CSRF-Token": client.cookies.get("pl_csrf") or ""},
        )
        assert response.status_code == 404

    async def test_an_anonymous_caller_is_refused(self, client: AsyncClient) -> None:
        assert (await client.get("/api/watch")).status_code == 401


class TestStats:
    async def test_nothing_watched_yet(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        body = (await client.get("/api/watch")).json()
        assert body["watched"] == 0
        assert body["night_medals"] == 0
        assert body["streak"] == 0

    async def test_the_denominator_is_the_real_fixture_count(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        body = (await client.get("/api/watch")).json()
        assert body["total_matches"] == 380

    async def test_hours_are_two_per_match(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        assert (await client.get("/api/watch")).json()["hours"] == 0.0


class TestMarkingOnceTheWindowIsOpen:
    """Drive a real toggle by moving the fixture's kickoff into the past."""

    async def _client(self, settings: Settings, fixtures: list[dict[str, Any]], sessions: Any) -> AsyncClient:
        cache = MemoryCache()
        moved = [dict(row) for row in fixtures]
        # Put the opener an hour ago so the window is open.
        for row in moved:
            if int(row["id"]) == OPENER:
                row["kickoff_time"] = (
                    (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
                )
                row["started"] = True
        from shared import keys

        await cache.set(keys.FPL_FIXTURES, moved, source="fpl")
        app = _build_app(settings, cache, sessions)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test")

    async def test_marking_a_live_match_counts_it(
        self, settings: Settings, fixtures_payload: list[dict[str, Any]], sessions: Any
    ) -> None:
        async with await self._client(settings, fixtures_payload, sessions) as http:
            await http.post("/api/session", json={"code": CODES["coyg"]})
            token = http.cookies.get("pl_csrf") or ""
            response = await http.post(
                "/api/watch", json={"fixture_id": OPENER}, headers={"X-CSRF-Token": token}
            )
            assert response.status_code == 200
            assert response.json()["watched"] == 1
            assert response.json()["hours"] == 2.0

    async def test_marking_twice_un_marks_it(
        self, settings: Settings, fixtures_payload: list[dict[str, Any]], sessions: Any
    ) -> None:
        async with await self._client(settings, fixtures_payload, sessions) as http:
            await http.post("/api/session", json={"code": CODES["coyg"]})
            token = http.cookies.get("pl_csrf") or ""
            await http.post("/api/watch", json={"fixture_id": OPENER}, headers={"X-CSRF-Token": token})
            second = await http.post(
                "/api/watch", json={"fixture_id": OPENER}, headers={"X-CSRF-Token": token}
            )
            assert second.json()["watched"] == 0

    async def test_two_people_watching_the_same_match_are_counted_separately(
        self, settings: Settings, fixtures_payload: list[dict[str, Any]], sessions: Any
    ) -> None:
        async with await self._client(settings, fixtures_payload, sessions) as http:
            for person in ("coyg", "bulba"):
                await http.post("/api/session", json={"code": CODES[person]})
                token = http.cookies.get("pl_csrf") or ""
                body = (
                    await http.post(
                        "/api/watch",
                        json={"fixture_id": OPENER},
                        headers={"X-CSRF-Token": token},
                    )
                ).json()
                assert body["watched"] == 1, person
                assert body["person"] == person


class TestNightMedal:
    """One match, four people, four different local hours."""

    def test_the_opener_is_not_a_night_match_for_anyone(self) -> None:
        kickoff = datetime(2026, 8, 21, 19, tzinfo=UTC)
        for tz in ("Europe/Kyiv", "America/Detroit", "America/Edmonton", "America/Anchorage"):
            assert is_night(kickoff, tz) is False, tz

    def test_a_late_kickoff_earns_the_medal_only_in_alaska(self) -> None:
        kickoff = datetime(2026, 11, 8, 10, tzinfo=UTC)
        assert is_night(kickoff, "America/Anchorage") is True
        assert is_night(kickoff, "Europe/Kyiv") is False

    def test_local_hour_is_recorded_per_person(self) -> None:
        kickoff = datetime(2026, 8, 22, 11, 30, tzinfo=UTC)
        assert local_hour(kickoff, "America/Anchorage") == 3
        assert local_hour(kickoff, "Europe/Kyiv") == 14


class TestWatchStateOnFixtures:
    """The fixtures list must say who watched what, or the button lies."""

    async def _open_client(
        self, settings: Settings, fixtures: list[dict[str, Any]], sessions: Any
    ) -> AsyncClient:
        cache = MemoryCache()
        now = datetime.now(UTC)
        moved = [dict(row) for row in fixtures]
        for row in moved:
            if int(row["id"]) == OPENER:
                # An hour ago: kicked off, window open.
                row["kickoff_time"] = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
                row["started"] = True
            else:
                # Everything else is pushed firmly into the future.
                #
                # These carried their captured real kickoffs, which were in the
                # future when the payload was recorded and are not any more --
                # so "the rest of the round has not kicked off" quietly became
                # false and the suite failed on a Saturday afternoon. Setting
                # them relative to now tests the rule rather than the calendar.
                row["kickoff_time"] = (now + timedelta(days=3)).isoformat().replace("+00:00", "Z")
                row["started"] = False
                row["finished"] = False
        from shared import keys

        await cache.set(keys.FPL_FIXTURES, moved, source="fpl")
        return AsyncClient(
            transport=ASGITransport(app=_build_app(settings, cache, sessions)),
            base_url="http://api.test",
        )

    async def test_nobody_has_watched_anything_yet(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        body = (await client.get("/api/fixtures?gameweek=1")).json()
        assert all(f["watched_by"] == [] for f in body["fixtures"])

    async def test_a_marked_match_reports_who_watched_it(
        self, settings: Settings, fixtures_payload: list[dict[str, Any]], sessions: Any
    ) -> None:
        async with await self._open_client(settings, fixtures_payload, sessions) as http:
            await http.post("/api/session", json={"code": CODES["bulba"]})
            await http.post(
                "/api/watch",
                json={"fixture_id": OPENER},
                headers={"X-CSRF-Token": http.cookies.get("pl_csrf") or ""},
            )
            body = (await http.get("/api/fixtures?gameweek=1")).json()
            opener = next(f for f in body["fixtures"] if f["id"] == OPENER)
            assert opener["watched_by"] == ["bulba"]

    async def test_everyone_who_watched_is_listed(
        self, settings: Settings, fixtures_payload: list[dict[str, Any]], sessions: Any
    ) -> None:
        async with await self._open_client(settings, fixtures_payload, sessions) as http:
            for person in ("coyg", "twzt"):
                await http.post("/api/session", json={"code": CODES[person]})
                await http.post(
                    "/api/watch",
                    json={"fixture_id": OPENER},
                    headers={"X-CSRF-Token": http.cookies.get("pl_csrf") or ""},
                )
            body = (await http.get("/api/fixtures?gameweek=1")).json()
            opener = next(f for f in body["fixtures"] if f["id"] == OPENER)
            assert sorted(opener["watched_by"]) == ["coyg", "twzt"]

    async def test_the_window_is_open_for_a_match_that_has_started(
        self, settings: Settings, fixtures_payload: list[dict[str, Any]], sessions: Any
    ) -> None:
        async with await self._open_client(settings, fixtures_payload, sessions) as http:
            await http.post("/api/session", json={"code": CODES["coyg"]})
            body = (await http.get("/api/fixtures?gameweek=1")).json()
            opener = next(f for f in body["fixtures"] if f["id"] == OPENER)
            assert opener["watch_open"] is True
            # The rest of the round has not kicked off.
            others = [f for f in body["fixtures"] if f["id"] != OPENER]
            assert all(f["watch_open"] is False for f in others)
