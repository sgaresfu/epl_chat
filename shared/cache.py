"""The cache and pub/sub layer between the poller and the api.

The whole architecture rests on one rule: the poller writes, the api reads, and
no upstream call is ever on a user's critical path. This module is that
boundary.

Redis is the real implementation. An in-memory fallback stands in when
``REDIS_URL`` is unreachable so a clean clone still runs and the test suite
needs no services -- it is process-local and therefore correct only for a single
process, which is exactly the local-dev case it exists for.

Every entry carries the time it was written, because BRIEF section 11 requires a
stale panel to say *how* stale it is rather than silently serving old numbers.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)

# Cache keys, one per upstream payload. Namespaced so a FLUSHDB in dev cannot
# be mistaken for a production incident.
NS = "pl2627"


def key(*parts: str | int) -> str:
    return ":".join([NS, *(str(p) for p in parts)])


# Pub/sub channels the api subscribes an SSE connection to.
CHANNEL_SCORES = f"{NS}:live:scores"
CHANNEL_FPL = f"{NS}:live:fpl"
CHANNEL_ODDS = f"{NS}:live:odds"
ALL_CHANNELS = (CHANNEL_SCORES, CHANNEL_FPL, CHANNEL_ODDS)


@dataclass(frozen=True, slots=True)
class Entry:
    """A cached payload with the metadata the staleness note needs."""

    value: Any
    written_at: float
    source: str

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.written_at)

    def is_stale(self, ttl: float) -> bool:
        return self.age_seconds > ttl


class Cache(Protocol):
    """What the api needs from a cache, and all it is allowed to do."""

    async def get(self, name: str) -> Entry | None: ...
    async def set(self, name: str, value: Any, source: str) -> None: ...
    async def publish(self, channel: str, payload: Any) -> None: ...
    def subscribe(self, *channels: str) -> AsyncGenerator[tuple[str, Any], None]: ...
    async def close(self) -> None: ...


class MemoryCache:
    """Process-local cache and pub/sub, for local dev and tests."""

    def __init__(self) -> None:
        self._data: dict[str, Entry] = {}
        self._subscribers: dict[str, set[asyncio.Queue[tuple[str, Any]]]] = defaultdict(set)

    async def get(self, name: str) -> Entry | None:
        return self._data.get(name)

    async def set(self, name: str, value: Any, source: str) -> None:
        self._data[name] = Entry(value=value, written_at=time.time(), source=source)

    async def publish(self, channel: str, payload: Any) -> None:
        for queue in list(self._subscribers.get(channel, ())):
            queue.put_nowait((channel, payload))

    async def subscribe(self, *channels: str) -> AsyncGenerator[tuple[str, Any], None]:
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        for channel in channels:
            self._subscribers[channel].add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            for channel in channels:
                self._subscribers[channel].discard(queue)

    async def close(self) -> None:
        self._data.clear()
        self._subscribers.clear()

    # Test and admin helper; not part of the Cache protocol.
    def keys(self) -> list[str]:
        return sorted(self._data)


class RedisCache:
    """The real cache. One connection pool, shared by the whole process."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(url, decode_responses=True)

    async def get(self, name: str) -> Entry | None:
        raw = await self._redis.get(name)
        if raw is None:
            return None
        try:
            envelope = json.loads(raw)
            return Entry(
                value=envelope["value"],
                written_at=float(envelope["written_at"]),
                source=str(envelope.get("source", "unknown")),
            )
        except (ValueError, KeyError, TypeError):
            log.warning("cache.corrupt_entry", key=name)
            return None

    async def set(self, name: str, value: Any, source: str) -> None:
        envelope = {"value": value, "written_at": time.time(), "source": source}
        # No TTL: a stale payload is strictly better than a blank panel, and the
        # age is rendered in the UI. The scheduler prunes rather than expiring.
        await self._redis.set(name, json.dumps(envelope, default=str))

    async def publish(self, channel: str, payload: Any) -> None:
        await self._redis.publish(channel, json.dumps(payload, default=str))

    async def subscribe(self, *channels: str) -> AsyncGenerator[tuple[str, Any], None]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(*channels)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    yield str(message["channel"]), json.loads(message["data"])
                except ValueError:
                    log.warning("cache.bad_message", channel=message.get("channel"))
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    async def close(self) -> None:
        await self._redis.aclose()


async def build_cache(url: str) -> Cache:
    """Connect to Redis, falling back to memory so a clean clone still runs."""
    if url.startswith(("redis://", "rediss://")):
        try:
            cache = RedisCache(url)
            await cache._redis.ping()
            log.info("cache.redis_connected", url=url.split("@")[-1])
            return cache
        except Exception as exc:
            log.warning("cache.redis_unavailable", error=str(exc), fallback="memory")
    return MemoryCache()
