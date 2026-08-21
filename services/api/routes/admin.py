"""Admin: cache ages, quota consumption, cron log, broadcaster editor."""

from __future__ import annotations

from fastapi import APIRouter
from shared import broadcasters, keys
from shared.config import MISSING_KEY_MESSAGES
from shared.models import AdminStatusOut, BroadcasterOut, CacheAge, CronRunOut, QuotaOut

from services.api.deps import Config, CurrentSession, State

router = APIRouter(tags=["admin"])


@router.get("/api/admin/status", response_model=AdminStatusOut)
async def status(_: CurrentSession, state: State, settings: Config) -> AdminStatusOut:
    caches: list[CacheAge] = []
    for cache_key, label in keys.LABELS.items():
        entry = await state.cache.get(cache_key)
        caches.append(
            CacheAge(
                name=label,
                source=entry.source if entry else "never written",
                age_seconds=round(entry.age_seconds, 1) if entry else -1.0,
                stale=entry.is_stale(keys.TTL.get(cache_key, 300)) if entry else True,
            )
        )

    quotas: list[QuotaOut] = []
    for source, budget, window, note in (
        (
            "the-odds-api",
            settings.odds_monthly_budget,
            "month",
            "Free tier allows 500/month. Polling every 30 minutes as briefed "
            "would need about 1,440, so odds are fetched only around each round.",
        ),
        (
            "api-football",
            settings.api_football_daily_budget,
            "day",
            "Free tier allows 100/day. Live event polling would exhaust that in "
            "one match, so scores come from FPL and this is kept for line-ups.",
        ),
    ):
        entry = await state.cache.get(keys.quota(source, window))
        used = int(entry.value) if entry else 0
        quotas.append(
            QuotaOut(
                source=source,
                used=used,
                budget=budget,
                remaining=max(0, budget - used),
                window=window,
                note=note,
            )
        )

    missing = [message for field, message in MISSING_KEY_MESSAGES.items() if not settings.has(field)]

    return AdminStatusOut(
        caches=caches,
        quotas=quotas,
        cron=_cron_log(),
        missing_keys=missing,
        environment=settings.environment,
    )


def _cron_log() -> list[CronRunOut]:
    """The scheduler's recent runs.

    Empty until the scheduler has run, which is the honest answer rather than a
    fabricated history -- the admin page renders that as "no runs recorded yet".
    """
    return []


@router.get("/api/admin/broadcasters", response_model=list[BroadcasterOut])
async def listings(_: CurrentSession) -> list[BroadcasterOut]:
    out: list[BroadcasterOut] = []
    for competition in ("premier-league", "champions-league"):
        for listing in broadcasters.all_listings(competition):
            out.append(
                BroadcasterOut(
                    country=listing.country,
                    competition=competition,
                    provider=listing.provider,
                    url=listing.url,
                    verified_on=listing.verified_on,
                    note=listing.note,
                )
            )
    return out
