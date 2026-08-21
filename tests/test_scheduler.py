"""Cron job tests.

The three jobs are referenced by ``render.yaml`` and by the scheduler
Dockerfile, so a missing or broken entrypoint deploys cleanly and only fails
the first time it is scheduled to run -- at 06:00 on a Monday, silently.
These tests are what stop that.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.scheduler.main import daily, hourly, main, weekly
from shared.cache import MemoryCache
from shared.config import Settings


class TestDispatch:
    def test_no_argument_is_a_usage_error(self) -> None:
        assert main([]) == 2

    def test_an_unknown_job_is_a_usage_error(self) -> None:
        assert main(["nightly"]) == 2

    @pytest.mark.parametrize("job", ["weekly", "daily", "hourly"])
    def test_every_job_named_in_render_yaml_is_dispatchable(self, job: str) -> None:
        from services.scheduler.main import JOBS

        assert job in JOBS

    def test_render_yaml_only_schedules_jobs_that_exist(self) -> None:
        # The cron entries and the code must not drift apart.
        import pathlib
        import re

        from services.scheduler.main import JOBS

        blueprint = (pathlib.Path(__file__).parents[1] / "render.yaml").read_text()
        scheduled = set(re.findall(r"services\.scheduler\.main (\w+)", blueprint))
        assert scheduled, "render.yaml should schedule at least one job"
        assert scheduled <= set(JOBS), f"render.yaml schedules unknown jobs: {scheduled - set(JOBS)}"


class TestHourly:
    async def test_it_reports_cache_and_quota_state(self) -> None:
        cache = MemoryCache()
        detail = await hourly(cache, Settings())
        assert "cache entries" in detail
        assert "the-odds-api" in detail

    async def test_it_counts_recorded_quota_spend(self) -> None:
        from shared.keys import quota

        cache = MemoryCache()
        window = datetime.now(UTC).strftime("%Y-%m")
        await cache.set(quota("the-odds-api", window), 37, source="quota")
        detail = await hourly(cache, Settings())
        assert "the-odds-api=37" in detail


class TestDailyAndWeekly:
    async def test_daily_fetches_for_itself_when_its_cache_is_cold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cron container starts with an empty cache every single time.

        With the poller inside the api and no shared Redis, a job that only read
        the cache would report "no data" on every run, for ever.
        """
        called: list[str] = []

        async def fake_ensure(cache: Any, settings: Any) -> list[dict[str, Any]]:
            called.append("fetched")
            return [{"finished": False, "kickoff_time": "2026-08-21T19:00:00Z"}]

        monkeypatch.setattr("services.scheduler.main.ensure_fixtures", fake_ensure)
        detail = await daily(MemoryCache(), Settings())
        assert called == ["fetched"]
        assert "1 to come" in detail

    async def test_daily_says_so_when_the_fetch_also_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_ensure(cache: Any, settings: Any) -> None:
            return None

        monkeypatch.setattr("services.scheduler.main.ensure_fixtures", fake_ensure)
        assert "no fixture data" in await daily(MemoryCache(), Settings())

    async def test_weekly_says_so_when_no_data_can_be_had(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_ensure(cache: Any, settings: Any) -> None:
            return None

        monkeypatch.setattr("services.scheduler.main.ensure_fixtures", fake_ensure)
        assert "nothing to snapshot" in await weekly(MemoryCache(), Settings())

    async def test_daily_counts_played_and_upcoming(
        self, cache: MemoryCache, fixtures_payload: list[dict[str, Any]]
    ) -> None:
        detail = await daily(cache, Settings())
        assert "380 to come" in detail

    async def test_weekly_snapshots_the_table(
        self, cache: MemoryCache, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        written: list[Any] = []

        class FakeSession:
            def add(self, row: Any) -> None:
                written.append(row)

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_session() -> Any:
            yield FakeSession()

        monkeypatch.setattr("services.scheduler.main.session", fake_session)

        detail = await weekly(cache, Settings())
        assert "snapshotted gameweek 1" in detail
        assert len(written) == 1

        snapshot = written[0]
        assert snapshot.gameweek == 1
        assert len(snapshot.payload["table"]) == 20
        assert snapshot.payload["matches_played"] == 0

    async def test_weekly_does_not_score_a_leaderboard_before_a_match_is_played(
        self, cache: MemoryCache, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A row of zeroes looks like a real result; saying nothing was scored is
        # the honest record.
        from contextlib import asynccontextmanager

        class FakeSession:
            def add(self, row: Any) -> None: ...

        @asynccontextmanager
        async def fake_session() -> Any:
            yield FakeSession()

        monkeypatch.setattr("services.scheduler.main.session", fake_session)
        detail = await weekly(cache, Settings())
        assert "no matches played yet" in detail
