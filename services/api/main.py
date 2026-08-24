"""The api service: REST and SSE, served entirely from cache.

No route here calls an upstream. The poller fills Redis and this process reads
it, which is what keeps a user request off the critical path of somebody else's
slow API and keeps four browsers on match day from becoming four times the
upstream traffic.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from shared.cache import build_cache
from shared.config import get_settings, validate_for_deployment

from services.api.deps import AppState
from services.api.routes import (
    admin,
    calendar,
    chat,
    football,
    fpl,
    leaderboard,
    news,
    picks,
    predictions,
    session,
    stats,
    stream,
    tables,
    watch,
)


def configure_logging(level: str) -> None:
    """JSON logs, so Render's log search is useful rather than decorative."""
    logging.basicConfig(format="%(message)s", level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), logging.INFO)),
        cache_logger_on_first_use=True,
    )


async def _run_poller(poller: Any) -> None:
    """Own the poller's lifetime alongside the api's.

    A crash here must not take the api down with it -- the site serving slightly
    stale data is far better than the site being gone.
    """
    log = structlog.get_logger(__name__)
    try:
        await poller.run_forever()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.error("api.poller_crashed", error=str(exc))
    finally:
        await poller.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)

    # Fail here, with a sentence naming the variable, rather than several
    # frames deep inside a database driver.
    validate_for_deployment(settings)

    cache = await build_cache(settings.redis_url)

    from shared.session import session_factory

    from services.api.repository import seed_predictions

    sessions = session_factory()
    app.state.app_state = AppState(settings=settings, cache=cache, sessions=sessions)
    log = structlog.get_logger(__name__)

    # The four people and the two seeded predictions are written once. Existing
    # rows are never overwritten, so a prediction filed since the last deploy
    # survives a restart.
    try:
        async with sessions() as db:
            written = await seed_predictions(db)
            await db.commit()
        if written:
            log.info("api.seeded_predictions", count=written)
    except Exception as exc:
        log.warning("api.seed_predictions_failed", error=str(exc))

    poller_task: asyncio.Task[None] | None = None
    if settings.poller_in_process:
        # The poller runs here rather than in its own worker. See render.yaml
        # for why: at four users the split costs a $7 worker and $10 of Redis
        # and buys nothing that asyncio does not already provide.
        from services.poller.main import Poller

        poller_task = asyncio.create_task(_run_poller(Poller(settings, cache)))
        log.info("api.poller_started_in_process")

    elif settings.seed_on_start and settings.environment == "local":
        # Dev affordance when the poller runs separately: one pass so a clean
        # clone shows real data without starting a second process.
        from services.poller.main import Poller

        poller = Poller(settings, cache)
        try:
            await poller.once()
            log.info("api.seeded_cache_for_local_dev")
        except Exception as exc:
            log.warning("api.seed_failed", error=str(exc))
        finally:
            await poller.close()

    log.info("api.started", environment=settings.environment, season=settings.season)
    try:
        yield
    finally:
        if poller_task is not None:
            poller_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poller_task

        from shared.session import dispose

        await cache.close()
        await dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Prediction League 26/27",
        version="0.1.0",
        description=(
            "Premier League predictions, FPL and a watch log for four friends. "
            "Every response is served from cache; the poller is the only process "
            "that talks to an upstream."
        ),
        lifespan=lifespan,
    )

    # Explicit allow-list, never "*" -- browsers reject a wildcard when the
    # request carries credentials, and EventSource needs credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        expose_headers=["X-CSRF-Token"],
        max_age=600,
    )

    for module in (
        session,
        football,
        tables,
        predictions,
        leaderboard,
        fpl,
        watch,
        news,
        chat,
        stats,
        stream,
        admin,
        calendar,
        picks,
    ):
        app.include_router(module.router)

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        """Liveness: the process is up. Never touches a dependency."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    async def readyz(request: Request) -> JSONResponse:
        """Readiness: the cache answers and the fixture list has been filled."""
        from shared import keys

        state: AppState = request.app.state.app_state
        entry = await state.cache.get(keys.FPL_FIXTURES)
        ready = entry is not None
        return JSONResponse(
            {
                "status": "ready" if ready else "waiting",
                "fixtures_cached": ready,
                "cache_age_seconds": round(entry.age_seconds, 1) if entry else None,
            },
            status_code=200 if ready else 503,
        )

    # Mounted last: every /api route and the health checks are already
    # registered, so only genuinely unmatched paths reach the app shell.
    from services.api import spa

    spa.mount(app)

    return app


app = create_app()
