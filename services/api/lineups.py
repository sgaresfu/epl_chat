"""On-demand line-ups: resolve API-Football's fixture id, fetch, cache.

This is the **one** route in the app that triggers an upstream call on a
user's own request path -- explicitly sanctioned by BRIEF section 4 ("no
user action triggers an upstream fetch except opening a match for
line-ups"). Everywhere else, the poller fills the cache and a request only
ever reads it.
"""

from __future__ import annotations

from typing import Any

import structlog
from shared import keys
from shared.cache import Cache
from shared.clubs import UnknownClubError, by_fpl_id
from shared.config import MISSING_KEY_MESSAGES, Settings
from shared.models import LineupPlayerOut, LineupSideOut, LineupsOut

from services.poller import api_football, quota
from services.poller.api_football import LineupSide
from services.poller.http import UpstreamError

log = structlog.get_logger(__name__)

NOT_OUT_YET = "Line-ups are not out yet."
UNREACHABLE = "Could not reach API-Football right now."


def _side_out(side: LineupSide) -> LineupSideOut:
    return LineupSideOut(
        formation=side.formation,
        starting=[LineupPlayerOut(name=p.name, number=p.number, position=p.position) for p in side.starting],
        bench=[LineupPlayerOut(name=p.name, number=p.number, position=p.position) for p in side.bench],
    )


async def _resolve_fixture_id_for_date(
    cache: Cache, settings: Settings, all_rows: list[dict[str, Any]], date: str
) -> dict[str, int] | None:
    """Resolve every match on ``date`` in one call, and cache all of them.

    Returns the day's mapping (``"HOME-AWAY"`` -> API-Football fixture id),
    or ``None`` if the call itself failed. The budget is checked by the
    caller, before this runs, so it can report the specific quota reason
    rather than this function's more generic "could not reach" one.
    Caching every fixture found on the date, not just the one being asked
    about, is what keeps this "one call per matchday" rather than one per
    match.
    """
    up = api_football.api_football_client(settings.api_football_key)
    season = int(settings.season.split("-")[0])
    try:
        mapping = await api_football.resolve_fixture_ids(up, date, season)
    except UpstreamError as exc:
        log.warning("lineups.resolve_failed", error=str(exc))
        return None
    finally:
        await up.close()
    await quota.spend(cache, "api-football", "day")

    for day_row in all_rows:
        kickoff = day_row.get("kickoff_time")
        if not kickoff or str(kickoff)[:10] != date:
            continue
        try:
            home = by_fpl_id(int(day_row["team_h"]))
            away = by_fpl_id(int(day_row["team_a"]))
        except (UnknownClubError, KeyError, TypeError, ValueError):
            continue
        found = mapping.get(f"{home.short_name}-{away.short_name}")
        if found is not None:
            await cache.set(keys.api_football_fixture_id(int(day_row["id"])), found, source="api-football")

    return mapping


async def get_lineups(
    fixture_id: int,
    row: dict[str, Any],
    all_rows: list[dict[str, Any]],
    cache: Cache,
    settings: Settings,
) -> LineupsOut:
    """Confirmed line-ups for one fixture, fetching only if the cache is cold."""
    if not settings.has("api_football_key"):
        return LineupsOut(available=False, reason=MISSING_KEY_MESSAGES["api_football_key"])

    cached = await cache.get(keys.lineups(fixture_id))
    if cached is not None and not cached.is_stale(keys.LINEUPS_TTL):
        return LineupsOut.model_validate(cached.value)

    def stale_or(reason: str) -> LineupsOut:
        """The last good answer, if there is one, beats a blank error."""
        if cached is not None:
            return LineupsOut.model_validate(cached.value)
        return LineupsOut(available=False, reason=reason)

    kickoff = row.get("kickoff_time")
    if not kickoff:
        return LineupsOut(available=False, reason="This fixture has no kickoff date yet.")
    date = str(kickoff)[:10]

    home = by_fpl_id(int(row["team_h"]))
    away = by_fpl_id(int(row["team_a"]))

    resolved_entry = await cache.get(keys.api_football_fixture_id(fixture_id))
    af_fixture_id = int(resolved_entry.value) if resolved_entry is not None else None

    if af_fixture_id is None:
        resolve_verdict = await quota.check(cache, "api-football", "day", settings.api_football_daily_budget)
        if not resolve_verdict.allowed:
            log.info("lineups.resolve_quota_exhausted", reason=resolve_verdict.reason)
            return stale_or(resolve_verdict.reason)
        mapping = await _resolve_fixture_id_for_date(cache, settings, all_rows, date)
        if mapping is None:
            return stale_or(UNREACHABLE)
        af_fixture_id = mapping.get(f"{home.short_name}-{away.short_name}")

    if af_fixture_id is None:
        result = LineupsOut(available=False, reason=NOT_OUT_YET)
        await cache.set(keys.lineups(fixture_id), result.model_dump(mode="json"), source="api-football")
        return result

    verdict = await quota.check(cache, "api-football", "day", settings.api_football_daily_budget)
    if not verdict.allowed:
        return stale_or(verdict.reason)

    up = api_football.api_football_client(settings.api_football_key)
    try:
        payload = await api_football.fetch_lineups(up, af_fixture_id)
    except UpstreamError as exc:
        log.warning("lineups.fetch_failed", error=str(exc))
        return stale_or(UNREACHABLE)
    finally:
        await up.close()
    await quota.spend(cache, "api-football", "day")

    home_side, away_side = api_football.normalise(payload, home.short_name, away.short_name)
    if home_side is None or away_side is None:
        result = LineupsOut(available=False, reason=NOT_OUT_YET)
    else:
        result = LineupsOut(available=True, home=_side_out(home_side), away=_side_out(away_side))

    await cache.set(keys.lineups(fixture_id), result.model_dump(mode="json"), source="api-football")
    return result
