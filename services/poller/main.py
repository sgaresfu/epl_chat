"""The poller: the only process that talks to an upstream.

Each source runs its own loop at its own cadence, writes the normalised payload
to the cache, and publishes a diff **only when the payload actually changed** --
so an idle afternoon produces no SSE traffic at all.

The cadences adapt to whether football is being played, because polling live
endpoints on a schedule when nothing is live is how a free tier gets spent on
nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from shared import keys
from shared.cache import CHANNEL_FPL, CHANNEL_ODDS, CHANNEL_SCORES, Cache, build_cache
from shared.config import Settings, get_settings

from services.poller import fpl, news, odds, quota
from services.poller.http import UpstreamError

log = structlog.get_logger(__name__)

# Cadences, in seconds.
LIVE_INTERVAL = 30  # while a match is in play
MATCHDAY_INTERVAL = 300  # on a matchday, nothing in play
IDLE_INTERVAL = 3600  # no football today
BOOTSTRAP_INTERVAL = 600
NEWS_INTERVAL = 900  # every 15 minutes, per BRIEF section 15
# The free CSV is regenerated a few times a day and costs nothing to read,
# so this is paced for freshness rather than for a quota.
ODDS_INTERVAL = 3600

# How close to kickoff counts as "a matchday" for the faster cadence.
MATCHDAY_WINDOW = timedelta(hours=6)


def digest(payload: Any) -> str:
    """A stable fingerprint, so we publish on change rather than on schedule."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class Poller:
    def __init__(self, settings: Settings, cache: Cache) -> None:
        self.settings = settings
        self.cache = cache
        self.fpl = fpl.client()
        self.sky = news.sky_client()
        self.odds = odds.odds_client()
        self.odds_api = odds.odds_api_client()
        self._digests: dict[str, str] = {}

    async def close(self) -> None:
        await self.fpl.close()
        await self.sky.close()
        await self.odds.close()
        await self.odds_api.close()

    async def write(self, name: str, payload: Any, source: str, channel: str | None = None) -> bool:
        """Cache a payload and publish only if it differs from the last one."""
        fingerprint = digest(payload)
        changed = self._digests.get(name) != fingerprint
        await self.cache.set(name, payload, source=source)
        self._digests[name] = fingerprint
        if changed and channel:
            await self.cache.publish(channel, {"key": name, "at": datetime.now(UTC).isoformat()})
            log.info("poller.published", key=name, channel=channel)
        return changed

    # -- state ------------------------------------------------------------

    async def fixtures_now(self) -> list[dict[str, Any]]:
        entry = await self.cache.get(keys.FPL_FIXTURES)
        rows = entry.value if entry else []
        return rows if isinstance(rows, list) else []

    async def anything_in_play(self) -> bool:
        rows = await self.fixtures_now()
        return any(fpl.is_in_play(r) for r in rows)

    async def is_matchday(self) -> bool:
        rows = await self.fixtures_now()
        now = datetime.now(UTC)
        for row in rows:
            kickoff = fpl.parse_kickoff(row.get("kickoff_time"))
            if kickoff and abs(kickoff - now) <= MATCHDAY_WINDOW:
                return True
        return False

    async def interval(self) -> float:
        if await self.anything_in_play():
            return LIVE_INTERVAL
        if await self.is_matchday():
            return MATCHDAY_INTERVAL
        return IDLE_INTERVAL

    # -- loops ------------------------------------------------------------

    async def once(self) -> None:
        """One full pass. Used by tests and by the local dev cache warm."""
        await self.poll_bootstrap()
        await self.poll_fixtures()
        await self.poll_league()
        await self.poll_news()
        await self.poll_odds()

    async def poll_news(self) -> None:
        """Sky's RSS needs no key, so this panel works with nothing configured."""
        try:
            payload = await news.poll_news(self.settings.youtube_api_key)
        except Exception as exc:
            log.warning("poller.news_failed", error=str(exc))
            return
        await self.write(keys.NEWS_SKY, payload, source="rss")

    async def poll_odds(self) -> None:
        """bet365 prices for the round.

        The free CSV needs no key and no quota, so this runs unconditionally.
        If ``ODDS_API_KEY`` is set the paid feed takes over -- it is fresher
        during a match -- but the panel never depends on it.
        """
        if self.settings.odds_api_key:
            verdict = await quota.check(
                self.cache, "the-odds-api", "month", self.settings.odds_monthly_budget
            )
            if verdict.allowed:
                try:
                    payload = await odds.fetch_odds(self.odds_api, self.settings.odds_api_key)
                except UpstreamError as exc:
                    log.warning("poller.odds_api_failed", error=str(exc))
                else:
                    await quota.spend(self.cache, "the-odds-api", "month")
                    await self.write(
                        keys.ODDS_ROUND,
                        odds.to_cache_payload(odds.normalise(payload)),
                        source="the-odds-api",
                        channel=CHANNEL_ODDS,
                    )
                    return
            else:
                log.info("poller.odds_quota_exhausted", reason=verdict.reason)

        try:
            matches = await odds.fetch_free_odds(self.odds)
        except UpstreamError as exc:
            log.warning("poller.odds_failed", error=str(exc))
            return
        if not matches:
            log.info("poller.odds_empty", note="no Premier League rows in the fixture file")
            return
        await self.write(
            keys.ODDS_ROUND,
            odds.to_cache_payload(matches),
            source="football-data",
            channel=CHANNEL_ODDS,
        )

    async def poll_bootstrap(self) -> None:
        try:
            payload = await fpl.bootstrap(self.fpl)
        except UpstreamError as exc:
            log.warning("poller.bootstrap_failed", error=str(exc))
            return
        await self.write(keys.FPL_BOOTSTRAP, payload, source="fpl")

    async def poll_fixtures(self) -> None:
        try:
            payload = await fpl.fixtures(self.fpl)
        except UpstreamError as exc:
            # FPL returns 503 around deadlines and at season rollover. The last
            # good payload stays in the cache and the UI shows its age.
            log.warning("poller.fixtures_failed", error=str(exc))
            return
        await self.write(keys.FPL_FIXTURES, payload, source="fpl", channel=CHANNEL_SCORES)

    async def poll_league(self) -> None:
        try:
            payload = await fpl.league_standings(self.fpl, self.settings.fpl_league_id)
        except UpstreamError as exc:
            log.warning("poller.league_failed", error=str(exc))
            return
        await self.write(keys.FPL_LEAGUE, payload, source="fpl")
        await self.poll_squads(payload)

    async def poll_squads(self, league_payload: dict[str, Any]) -> None:
        """Every manager's picks, and the live points for the round.

        Picks are readable the moment the deadline passes, so there is nothing
        to wait for. FPL is free and unmetered, so four extra calls cost nothing
        that matters.
        """
        boot = await self.cache.get(keys.FPL_BOOTSTRAP)
        event = fpl.current_gameweek(boot.value) if boot else None
        if event is None:
            return
        gameweek = int(event["id"])

        # Before the deadline nobody's team is visible; asking is just noise.
        if not event.get("finished") and event.get("is_next") and not event.get("deadline_time_passed", True):
            deadline = fpl.parse_kickoff(event.get("deadline_time"))
            if deadline and datetime.now(UTC) < deadline:
                return

        for member in fpl.parse_league(league_payload):
            try:
                picks = await fpl.entry_picks(self.fpl, member.entry_id, gameweek)
            except UpstreamError as exc:
                log.info("poller.picks_unavailable", entry=member.entry_id, error=str(exc))
                continue
            await self.write(keys.fpl_picks(member.entry_id, gameweek), picks, source="fpl")

            try:
                history = await fpl.entry_history(self.fpl, member.entry_id)
            except UpstreamError as exc:
                log.info("poller.history_unavailable", entry=member.entry_id, error=str(exc))
            else:
                await self.write(keys.fpl_history(member.entry_id), history, source="fpl")

        try:
            live = await fpl.live_gameweek(self.fpl, gameweek)
        except UpstreamError as exc:
            log.warning("poller.live_failed", error=str(exc))
            return
        await self.write(keys.fpl_live(gameweek), live, source="fpl", channel=CHANNEL_FPL)

    async def run_forever(self) -> None:
        log.info("poller.starting", league=self.settings.fpl_league_id)
        last_bootstrap = 0.0
        last_news = 0.0
        last_odds = 0.0
        while True:
            started = asyncio.get_running_loop().time()
            try:
                if started - last_bootstrap > BOOTSTRAP_INTERVAL:
                    await self.poll_bootstrap()
                    last_bootstrap = started
                if started - last_news > NEWS_INTERVAL:
                    await self.poll_news()
                    last_news = started
                if started - last_odds > ODDS_INTERVAL:
                    await self.poll_odds()
                    last_odds = started
                await self.poll_fixtures()
                await self.poll_league()
            except Exception as exc:
                log.error("poller.iteration_failed", error=str(exc))

            delay = await self.interval()
            log.info("poller.sleeping", seconds=delay)
            await asyncio.sleep(delay)


async def main() -> None:
    settings = get_settings()
    from services.api.main import configure_logging

    configure_logging(settings.log_level)
    cache = await build_cache(settings.redis_url)
    poller = Poller(settings, cache)
    try:
        await poller.run_forever()
    finally:
        await poller.close()
        await cache.close()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
