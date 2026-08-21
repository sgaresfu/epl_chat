"""Deploy preflight.

Catches the deployment mistakes that are otherwise found by Render, ten minutes
into a build, or worse by a cron job at 06:00 on a Monday. Run it before every
deploy and in CI.

It checks configuration and wiring only -- it cannot verify that Render accepts
the blueprint, or that the Docker images build. Those need Render and Docker.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
problems: list[str] = []
warnings: list[str] = []


def ok(message: str) -> None:
    print(f"  ok    {message}")


def fail(message: str) -> None:
    print(f"  FAIL  {message}")
    problems.append(message)


def warn(message: str) -> None:
    print(f"  warn  {message}")
    warnings.append(message)


def check_blueprint() -> None:
    print("render.yaml")
    import yaml

    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text())
    services = {s["name"]: s for s in blueprint["services"]}

    # Every Dockerfile the blueprint names must exist.
    for name, service in services.items():
        path = service.get("dockerfilePath")
        if path and not (ROOT / path.lstrip("./")).exists():
            fail(f"{name}: dockerfilePath {path} does not exist")
        elif path:
            ok(f"{name}: {path}")

    # Every cron job must invoke a job the scheduler actually defines.
    from services.scheduler.main import JOBS

    for name, service in services.items():
        if service.get("type") != "cronjob":
            continue
        command = service.get("dockerCommand", "")
        match = re.search(r"services\.scheduler\.main (\w+)", command)
        if not match:
            warn(f"{name}: cron command does not name a scheduler job")
        elif match.group(1) not in JOBS:
            fail(f"{name}: schedules unknown job '{match.group(1)}'")
        else:
            ok(f"{name}: runs '{match.group(1)}' ({service.get('schedule')})")

    # The api must migrate before it serves traffic.
    api = services.get("league-api", {})
    if "alembic upgrade head" in str(api.get("preDeployCommand", "")):
        ok("league-api: migrations run before traffic")
    else:
        fail("league-api: no preDeployCommand running alembic; first deploy has no schema")

    # The static site must publish what the build produces.
    web = services.get("league-web", {})
    if web.get("staticPublishPath") == "apps/web/dist":
        ok("league-web: publishes apps/web/dist")
    else:
        fail(f"league-web: staticPublishPath is {web.get('staticPublishPath')!r}")
    if any(
        r.get("type") == "rewrite" and r.get("destination") == "/index.html" for r in web.get("routes", [])
    ):
        ok("league-web: SPA rewrite present, so deep links do not 404")
    else:
        fail("league-web: no SPA rewrite; /table would 404 on a hard refresh")

    # No secret may be committed.
    group = blueprint.get("envVarGroups", [{}])[0]
    leaked = [v["key"] for v in group.get("envVars", []) if "value" in v and v["key"] not in {"ENVIRONMENT"}]
    if leaked:
        fail(f"secrets carry literal values in render.yaml: {', '.join(leaked)}")
    else:
        ok("no secret values committed in the blueprint")


def check_env_example() -> None:
    print("\n.env.example")
    from shared.config import Settings

    example = (ROOT / ".env.example").read_text()
    documented = set(re.findall(r"^([A-Z0-9_]+)=", example, re.MULTILINE))

    required = {
        "SESSION_SECRET",
        "CODE_COYG",
        "CODE_AURE",
        "CODE_TWZT",
        "CODE_BULBA",
        "DATABASE_URL",
        "REDIS_URL",
        "FRONTEND_ORIGIN",
        "COOKIE_DOMAIN",
    }
    missing = required - documented
    if missing:
        fail(f".env.example is missing: {', '.join(sorted(missing))}")
    else:
        ok(f"all {len(required)} required variables documented")

    # Every settings field that is a credential should be documented.
    fields = set(Settings.model_fields)
    undocumented = {
        f.upper()
        for f in fields
        if any(t in f for t in ("key", "secret", "code_", "dsn")) and f.upper() not in documented
    }
    if undocumented:
        warn(f"settings fields not in .env.example: {', '.join(sorted(undocumented))}")
    else:
        ok("every credential field appears in .env.example")


def check_generated_types() -> None:
    print("\ngenerated API types")
    schema = ROOT / "apps" / "web" / "src" / "api" / "schema.d.ts"
    spec = ROOT / "openapi.json"
    if not schema.exists() or not spec.exists():
        fail("openapi.json or schema.d.ts is missing; run scripts/export_openapi.py")
        return

    from services.api.main import create_app

    live = create_app().openapi()
    committed = json.loads(spec.read_text())
    if live.get("paths", {}).keys() != committed.get("paths", {}).keys():
        fail("openapi.json is stale; re-run scripts/export_openapi.py and npm run gen:api")
    else:
        ok(f"openapi.json matches the app ({len(live['paths'])} paths)")


def check_database_drivers() -> None:
    """A driverless Postgres URL breaks both the app and its migrations."""
    print("\ndatabase drivers")
    from shared.config import Settings
    from sqlalchemy import create_engine
    from sqlalchemy.ext.asyncio import create_async_engine

    render_style = "postgresql://league:pw@dpg-abc.oregon-postgres.render.com/league"
    config = Settings(database_url=render_style, session_secret="preflight" * 4)

    try:
        create_async_engine(config.async_database_url)
        ok("Render's postgresql:// resolves to an async driver")
    except Exception as exc:
        fail(f"async engine cannot be built from Render's URL: {exc}")

    try:
        create_engine(config.sync_database_url)
        ok("the same URL resolves to a sync driver for Alembic")
    except Exception as exc:
        fail(f"alembic cannot build a sync engine from Render's URL: {exc}")

    dockerfile = (ROOT / "services" / "api" / "Dockerfile").read_text()
    if "psycopg" in dockerfile:
        ok("the api image installs a sync Postgres driver for preDeployCommand")
    else:
        fail("services/api/Dockerfile has no psycopg; `alembic upgrade head` will fail")


def check_data_files() -> None:
    print("\ncommitted data")
    for name in ("broadcasters.json", "seed_predictions.json", "season_2025_26.json", "fpl_mapping.json"):
        path = ROOT / "shared" / "data" / name
        if path.exists():
            ok(f"{name} present")
        else:
            fail(f"shared/data/{name} is missing")


def main() -> int:
    print("Deploy preflight\n" + "=" * 40)
    check_blueprint()
    check_env_example()
    check_generated_types()
    check_database_drivers()
    check_data_files()

    print("\n" + "=" * 40)
    if warnings:
        print(f"{len(warnings)} warning(s)")
    if problems:
        print(f"FAILED: {len(problems)} problem(s) would break the deploy")
        return 1
    print("Preflight passed. Note: this cannot verify that Docker builds or that")
    print("Render accepts the blueprint — both need those tools present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
