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
    def test_the_api_serves_the_frontend_itself(self) -> None:
        """One origin, so the session cookie is first-party.

        Two origins made it third-party, and every browser on iOS is WebKit —
        Safari's tracking prevention dropped it and nobody could sign in from a
        phone. Three of the four watch on one.
        """
        env = {e["key"]: e.get("value") for e in SERVICES["league-api"]["envVars"] if "key" in e}
        assert env.get("SERVE_FRONTEND") == "true"

    def test_there_is_no_separate_static_site(self) -> None:
        statics = [s for s in BLUEPRINT["services"] if s.get("runtime") == "static"]
        assert statics == []

    def test_no_cross_origin_variables_are_needed(self) -> None:
        raw = (ROOT / "render.yaml").read_text()
        for key in ("VITE_API_BASE",):
            assert f"key: {key}" not in raw

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


class TestFreeTierConstraints:
    """Render rejects paid-only fields on a free service at blueprint level."""

    PAID_ONLY = ("preDeployCommand", "autoDeployTrigger", "maxShutdownDelaySeconds")

    def test_no_free_service_uses_a_paid_only_field(self) -> None:
        for name, service in SERVICES.items():
            if service.get("plan") not in (None, "free"):
                continue
            for field in self.PAID_ONLY:
                assert field not in service, f"{name} uses paid-only {field!r}"

    def test_migrations_still_run_before_the_api_serves(self) -> None:
        """preDeployCommand is the proper hook, but it needs a paid plan.

        Without it the schema has to arrive some other way, or the first deploy
        comes up against an empty database.
        """
        entrypoint = ROOT / "services" / "api" / "entrypoint.sh"
        assert entrypoint.exists()
        assert "alembic upgrade head" in entrypoint.read_text()

    def test_the_image_actually_runs_the_entrypoint(self) -> None:
        dockerfile = (ROOT / "services" / "api" / "Dockerfile").read_text()
        assert "entrypoint.sh" in dockerfile

    def test_the_entrypoint_aborts_on_a_failed_migration(self) -> None:
        """`set -e` is what turns a bad migration into a failed deploy.

        Without it the script would carry on and serve traffic against a schema
        that never arrived.
        """
        body = (ROOT / "services" / "api" / "entrypoint.sh").read_text()
        assert "set -e" in body

    def test_the_entrypoint_execs_so_signals_reach_uvicorn(self) -> None:
        # Without exec, uvicorn is a child of the shell and never sees Render's
        # SIGTERM, so the lifespan cannot close the poller or the DB pool.
        body = (ROOT / "services" / "api" / "entrypoint.sh").read_text()
        assert "exec uvicorn" in body

    def test_the_entrypoint_honours_the_port_render_assigns(self) -> None:
        body = (ROOT / "services" / "api" / "entrypoint.sh").read_text()
        assert "PORT" in body

    def test_the_entrypoint_is_valid_shell(self) -> None:
        import subprocess

        result = subprocess.run(
            ["sh", "-n", str(ROOT / "services" / "api" / "entrypoint.sh")],
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr.decode()


class TestServiceReferencesThatDoNotWork:
    """`fromService … property: host` is a trap, twice over.

    For a *static site* it resolves to empty, which left the api with an empty
    CORS allow-list rejecting every browser request. For a *web service* it
    yields the service name rather than the hostname, so the frontend requested
    `https://league-api/api/me` and died with ERR_NAME_NOT_RESOLVED.

    Both failures are invisible to curl and to health checks — only a real
    browser sees them — so the values are set explicitly instead.
    """

    CROSS_REFERENCES = ("VITE_API_BASE", "FRONTEND_ORIGIN")

    def test_neither_url_is_wired_through_fromservice(self) -> None:
        for name, service in SERVICES.items():
            for entry in service.get("envVars", []):
                if entry.get("key") in self.CROSS_REFERENCES:
                    assert "fromService" not in entry, (
                        f"{name}: {entry['key']} uses fromService, which yields a "
                        "service name or an empty string, not a URL"
                    )

    def test_no_service_uses_property_host_at_all(self) -> None:
        for name, service in SERVICES.items():
            for entry in service.get("envVars", []):
                ref = entry.get("fromService", {})
                assert ref.get("property") != "host", (
                    f"{name}: {entry.get('key')} uses property 'host', which is "
                    "the service name, not a hostname"
                )

    def test_the_cross_origin_problem_is_gone_entirely(self) -> None:
        """Neither variable is needed once the api serves the app."""
        declared = {
            entry["key"]
            for service in SERVICES.values()
            for entry in service.get("envVars", [])
            if "key" in entry
        }
        assert "VITE_API_BASE" not in declared
