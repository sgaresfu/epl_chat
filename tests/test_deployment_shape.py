"""The deployed architecture must match what the code actually does.

The brief specifies three processes plus Redis plus Postgres, which costs about
$35/month — for four people checking a table. What drives that is process
separation: a worker that exists only to poll, and Redis that exists only so
that worker and the api can share a cache. Collapsing them saves $17 and
changes nothing observable at this size.

These tests guard the collapsed shape, and the seam that restores the briefed
one, so a blueprint and a code path cannot drift apart silently — which they
already did once: POLLER_IN_PROCESS existed as a setting that nothing read.
"""

from __future__ import annotations

import pathlib

import yaml
from shared.config import Settings

ROOT = pathlib.Path(__file__).parents[1]
BLUEPRINT = yaml.safe_load((ROOT / "render.yaml").read_text())
SERVICES = {s["name"]: s for s in BLUEPRINT["services"]}


class TestTheSettingIsActuallyRead:
    """A setting nothing reads is worse than no setting."""

    def test_the_api_reads_poller_in_process(self) -> None:
        source = (ROOT / "services" / "api" / "main.py").read_text()
        assert "settings.poller_in_process" in source

    def test_it_starts_a_task_when_enabled(self) -> None:
        source = (ROOT / "services" / "api" / "main.py").read_text()
        assert "asyncio.create_task" in source
        assert "api.poller_started_in_process" in source

    def test_the_task_is_cancelled_on_shutdown(self) -> None:
        # An orphaned poller task would keep an event loop alive on shutdown.
        source = (ROOT / "services" / "api" / "main.py").read_text()
        assert "poller_task.cancel()" in source

    def test_it_defaults_to_on(self) -> None:
        assert Settings(session_secret="x" * 32).poller_in_process is True

    def test_it_can_be_turned_off_to_restore_the_split(self) -> None:
        config = Settings(session_secret="x" * 32, poller_in_process=False)
        assert config.poller_in_process is False


class TestBlueprintMatchesTheCode:
    def test_the_api_enables_the_in_process_poller(self) -> None:
        env = {e["key"]: e.get("value") for e in SERVICES["league-api"]["envVars"] if "key" in e}
        assert env.get("POLLER_IN_PROCESS") == "true"

    def test_there_is_no_separate_worker(self) -> None:
        # A worker plus POLLER_IN_PROCESS=true would poll everything twice.
        assert [s for s in BLUEPRINT["services"] if s["type"] == "worker"] == []

    def test_there_is_no_redis(self) -> None:
        # One process needs no shared cache, and Redis was $10 of the bill.
        assert [s for s in BLUEPRINT["services"] if s["type"] == "keyvalue"] == []

    def test_no_service_is_given_a_redis_url(self) -> None:
        # Checked against parsed env vars, not raw text: the file mentions
        # REDIS_URL in a comment explaining how to restore the split.
        for name, service in SERVICES.items():
            keys = {e["key"] for e in service.get("envVars", []) if "key" in e}
            assert "REDIS_URL" not in keys, name
        group_keys = {e["key"] for e in BLUEPRINT["envVarGroups"][0]["envVars"]}
        assert "REDIS_URL" not in group_keys

    def test_the_database_is_external(self) -> None:
        """Render's free Postgres is deleted 30 days after creation.

        That falls mid-season, so DATABASE_URL is supplied rather than
        provisioned by the blueprint.
        """
        assert "databases" not in BLUEPRINT
        group = BLUEPRINT["envVarGroups"][0]
        keys = {e["key"] for e in group["envVars"]}
        assert "DATABASE_URL" in keys

    def test_nothing_is_on_a_paid_plan(self) -> None:
        paid = [s["name"] for s in BLUEPRINT["services"] if s.get("plan") not in (None, "free")]
        assert paid == [], f"unexpectedly on a paid plan: {paid}"


class TestCacheFallback:
    async def test_it_falls_back_to_memory_without_redis(self) -> None:
        """With no Redis configured the cache must still work, not crash."""
        from shared.cache import MemoryCache, build_cache

        cache = await build_cache("redis://127.0.0.1:6399/0")  # nothing listening
        assert isinstance(cache, MemoryCache)
        await cache.set("k", {"v": 1}, source="test")
        entry = await cache.get("k")
        assert entry is not None
        assert entry.value == {"v": 1}

    async def test_pubsub_still_works_in_memory(self) -> None:
        """SSE depends on publish reaching a subscriber in the same process."""
        import asyncio
        import contextlib

        from shared.cache import CHANNEL_SCORES, MemoryCache

        cache = MemoryCache()
        seen: list[object] = []

        async def listen() -> None:
            async with contextlib.aclosing(cache.subscribe(CHANNEL_SCORES)) as stream:
                async for _, payload in stream:
                    seen.append(payload)
                    return

        task = asyncio.create_task(listen())
        await asyncio.sleep(0.05)
        await cache.publish(CHANNEL_SCORES, {"goal": 1})
        await asyncio.wait_for(task, timeout=2.0)
        assert seen == [{"goal": 1}]


class TestCronStillWorksWhileTheApiSleeps:
    def test_cron_jobs_are_scheduled(self) -> None:
        crons = [s for s in BLUEPRINT["services"] if s["type"] == "cron"]
        assert len(crons) >= 2

    def test_every_scheduled_job_exists_in_the_code(self) -> None:
        import re

        from services.scheduler.main import JOBS

        raw = (ROOT / "render.yaml").read_text()
        scheduled = set(re.findall(r"services\.scheduler\.main (\w+)", raw))
        assert scheduled
        assert scheduled <= set(JOBS)

    def test_the_scheduler_can_fetch_its_own_data(self) -> None:
        """A cron container starts with an empty cache every time.

        With no shared Redis, a job that only read the cache would report
        "no data" on every run, for ever.
        """
        source = (ROOT / "services" / "scheduler" / "main.py").read_text()
        assert "ensure_fixtures" in source
