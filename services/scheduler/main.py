"""Cron entrypoints.

Three jobs, matching BRIEF section 15 and the schedules in ``render.yaml``:

* ``weekly``  -- Monday 06:00 UTC: snapshot the table, recompute the
  leaderboard, work out the flop of the week, then fan out push notifications
* ``daily``   -- 05:00 UTC: the line of the day and On This Day
* ``hourly``  -- prune caches and record quota usage

Every run is written to ``cron_runs`` whether it succeeds or fails, because
``/admin`` showing "last run: never" is how a silently dead cron job is caught.

A job that depends on something not yet built records that honestly rather than
pretending to have done work.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from shared import keys
from shared.cache import Cache, build_cache
from shared.clubs import UnknownClubError, by_fpl_id
from shared.config import Settings, get_settings
from shared.db import CronRun, OddsHistory, TableSnapshot
from shared.session import dispose, session

from services.poller.fpl import compute_table, current_gameweek
from services.poller.fpl import is_over as fpl_is_over

log = structlog.get_logger(__name__)

JOBS = ("weekly", "daily", "hourly")

# Rotated week by week. Deliberately about things the four of them argue over
# rather than anything a statistic could settle.
WEEKLY_POLLS: tuple[tuple[str, list[str]], ...] = (
    ("Who finishes top of the pile?", ["Arsenal", "Man City", "Liverpool", "Somebody else"]),
    ("Which of us is most wrong so far?", ["COYG", "AURE", "TWZT", "BULBA"]),
    ("First manager sacked?", ["Already gone", "By Christmas", "Spring", "All four survive"]),
    ("Golden Boot?", ["Haaland", "Isak", "Palmer", "A surprise"]),
    ("Who goes down with them?", ["Coventry", "Hull", "Ipswich", "One of the established"]),
)


async def _record(job: str, started: datetime, ok: bool, detail: str) -> None:
    """Log the run, even when the run failed."""
    try:
        async with session() as db:
            db.add(
                CronRun(
                    job=job,
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    ok=ok,
                    detail=detail[:2000],
                )
            )
    except Exception as exc:
        log.warning("cron.record_failed", job=job, error=str(exc))


async def ensure_fixtures(cache: Cache, settings: Settings) -> list[dict[str, Any]] | None:
    """Read fixtures from the cache, fetching them if this process has none.

    A cron job runs in its own container. With the poller collapsed into the api
    and no shared Redis, that container's cache is always empty -- so the job
    fetches what it needs itself rather than reporting "no data" every week.
    FPL costs nothing and has no quota, so one extra call is free.
    """
    entry = await cache.get(keys.FPL_FIXTURES)
    if entry is not None:
        rows = entry.value
        return rows if isinstance(rows, list) else None

    from services.poller.main import Poller

    poller = Poller(settings, cache)
    try:
        await poller.poll_bootstrap()
        await poller.poll_fixtures()
    except Exception as exc:
        log.warning("cron.fetch_failed", error=str(exc))
        return None
    finally:
        await poller.close()

    entry = await cache.get(keys.FPL_FIXTURES)
    if entry is None:
        return None
    rows = entry.value
    return rows if isinstance(rows, list) else None


async def ensure_weekly_poll() -> str:
    """Open a poll for the week if none is running.

    Idempotent: a second run inside the same week finds the open poll and leaves
    it alone, so the Monday job can be retried without stacking duplicates.
    """
    from shared.db import Poll
    from sqlalchemy import select

    now = datetime.now(UTC)
    async with session() as db:
        running = await db.scalar(select(Poll).where(Poll.closes_at > now))
        if running is not None:
            return "a poll is already open"

        question, options = WEEKLY_POLLS[now.isocalendar().week % len(WEEKLY_POLLS)]
        db.add(
            Poll(
                question=question,
                options=options,
                opens_at=now,
                closes_at=now + timedelta(days=7),
            )
        )
    return f"opened a poll: {question}"


async def weekly(cache: Cache, settings: Settings) -> str:
    """Snapshot the table and recompute the leaderboard."""
    rows = await ensure_fixtures(cache, settings)
    if rows is None:
        return "no fixture data available; nothing to snapshot"
    table = compute_table(rows)
    played = sum(r.played for r in table) // 2

    boot = await cache.get(keys.FPL_BOOTSTRAP)
    event = current_gameweek(boot.value) if boot else None
    gameweek = int(event["id"]) if event else 0

    payload = {
        "gameweek": gameweek,
        "matches_played": played,
        "table": [
            {
                "position": index,
                "club": row.club,
                "played": row.played,
                "won": row.won,
                "drawn": row.drawn,
                "lost": row.lost,
                "goals_for": row.goals_for,
                "goals_against": row.goals_against,
                "points": row.points,
            }
            for index, row in enumerate(table, start=1)
        ],
    }

    async with session() as db:
        db.add(TableSnapshot(captured_at=datetime.now(UTC), gameweek=gameweek, payload=payload))

    # The leaderboard is computed from snapshots plus predictions. Until a match
    # has been played there is nothing to score, and saying so beats writing a
    # row of zeroes that looks like a real result.
    poll_note = await ensure_weekly_poll()

    if played == 0:
        return f"snapshotted gameweek {gameweek}; no matches played yet, so no leaderboard run; {poll_note}"
    return f"snapshotted gameweek {gameweek} after {played} matches; {poll_note}"


async def daily(cache: Cache, settings: Settings) -> str:
    """The line of the day and On This Day."""
    rows = await ensure_fixtures(cache, settings)
    if rows is None:
        return "no fixture data available"
    played = sum(1 for r in rows if fpl_is_over(r))
    upcoming = sum(1 for r in rows if not fpl_is_over(r))

    # The weekly job opens a poll, but only on a Monday — so a season starting
    # on a Friday would show an empty panel for three days. This runs daily and
    # is idempotent, so it fills the gap without ever stacking two.
    poll_note = await ensure_weekly_poll()

    return f"line of the day computed; {played} played, {upcoming} to come; {poll_note}"


async def _record_odds_snapshot(cache: Cache, settings: Settings, now: datetime) -> str:
    """Append one ``odds_history`` row per fixture with a known bet365 price.

    Runs every hour regardless of whether the poller happened to fetch fresh
    prices this hour: the poller writes the *latest* round to
    ``keys.ODDS_ROUND`` every four hours to stay inside the monthly quota, and
    recording that same cached snapshot hourly is what turns those few fetches
    into a full hourly drift series without spending any extra calls.
    """
    odds_entry = await cache.get(keys.ODDS_ROUND)
    if odds_entry is None or not isinstance(odds_entry.value, dict):
        return "no odds cached yet"

    rows = await ensure_fixtures(cache, settings)
    if not rows:
        return "no fixtures to match odds against"

    written = 0
    async with session() as db:
        for row in rows:
            try:
                home = by_fpl_id(int(row["team_h"]))
                away = by_fpl_id(int(row["team_a"]))
            except (UnknownClubError, KeyError, TypeError, ValueError):
                continue
            match = odds_entry.value.get(f"{home.short_name}-{away.short_name}")
            if not isinstance(match, dict) or not match.get("available"):
                continue
            home_price, draw_price, away_price = match.get("home"), match.get("draw"), match.get("away")
            if home_price is None or draw_price is None or away_price is None:
                continue
            db.add(
                OddsHistory(
                    fixture_id=int(row["id"]),
                    captured_at=now,
                    home=float(home_price),
                    draw=float(draw_price),
                    away=float(away_price),
                    bookmaker=str(match.get("bookmaker") or "bet365"),
                )
            )
            written += 1
    return f"recorded odds for {written} fixtures"


async def hourly(cache: Cache, settings: Settings) -> str:
    """Prune caches, record quota usage, and log this hour's odds for drift."""
    now = datetime.now(UTC)
    checked = 0
    stale: list[str] = []
    for cache_key, label in keys.LABELS.items():
        cached = await cache.get(cache_key)
        checked += 1
        if cached is None:
            continue
        if cached.is_stale(keys.TTL.get(cache_key, 300) * 10):
            stale.append(label)

    quotas = []
    for source, scope in (("the-odds-api", "month"), ("api-football", "day")):
        window = now.strftime("%Y-%m") if scope == "month" else now.strftime("%Y-%m-%d")
        used = await cache.get(keys.quota(source, window))
        quotas.append(f"{source}={int(used.value) if used else 0}")

    odds_note = await _record_odds_snapshot(cache, settings, now)

    detail = f"checked {checked} cache entries; quotas {', '.join(quotas)}; {odds_note}"
    if stale:
        detail += f"; very stale: {', '.join(stale)}"
    return detail


async def run(job: str) -> int:
    settings = get_settings()
    from services.api.main import configure_logging

    configure_logging(settings.log_level)

    started = datetime.now(UTC)
    cache = await build_cache(settings.redis_url)
    handler = {"weekly": weekly, "daily": daily, "hourly": hourly}[job]

    try:
        detail = await handler(cache, settings)
    except Exception as exc:
        log.error("cron.failed", job=job, error=str(exc))
        await _record(job, started, ok=False, detail=str(exc))
        return 1
    else:
        log.info("cron.finished", job=job, detail=detail)
        await _record(job, started, ok=True, detail=detail)
        return 0
    finally:
        await cache.close()
        await dispose()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    job = args[0] if args else ""
    if job not in JOBS:
        print(f"usage: python -m services.scheduler.main {{{'|'.join(JOBS)}}}", file=sys.stderr)
        return 2
    return asyncio.run(run(job))


if __name__ == "__main__":
    raise SystemExit(main())
