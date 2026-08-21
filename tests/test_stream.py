"""SSE tests.

The endpoint itself is verified against a real uvicorn server by
``scripts/verify_stream.py``, because an infinite streaming response behaves
differently through an in-process ASGI transport than it does over a socket --
and the brief is explicit that the stream must be tested for real rather than
assumed. What is unit-tested here is the logic underneath it: the wire format,
and the publish-to-subscriber delivery the endpoint is a thin wrapper over.
"""

from __future__ import annotations

import asyncio
import contextlib

from httpx import AsyncClient
from services.api.routes.stream import sse
from shared.cache import ALL_CHANNELS, CHANNEL_ODDS, CHANNEL_SCORES, MemoryCache


class TestWireFormat:
    def test_an_event_is_framed_for_eventsource(self) -> None:
        assert sse("scores", {"a": 1}) == 'event: scores\ndata: {"a": 1}\n\n'

    def test_the_frame_ends_with_a_blank_line(self) -> None:
        # Without the terminating blank line EventSource never dispatches.
        assert sse("fpl", {}).endswith("\n\n")

    def test_payloads_containing_datetimes_serialise(self) -> None:
        from datetime import UTC, datetime

        frame = sse("odds", {"at": datetime(2026, 8, 21, 19, tzinfo=UTC)})
        assert "2026-08-21" in frame


class TestPublishDelivery:
    async def test_a_subscriber_receives_a_published_payload(self) -> None:
        cache = MemoryCache()
        received: list[tuple[str, object]] = []

        async def listen() -> None:
            async for channel, payload in cache.subscribe(*ALL_CHANNELS):
                received.append((channel, payload))
                return

        task = asyncio.create_task(listen())
        await asyncio.sleep(0.05)
        await cache.publish(CHANNEL_SCORES, {"goal": "ARS 1-0"})
        await asyncio.wait_for(task, timeout=2.0)

        assert received == [(CHANNEL_SCORES, {"goal": "ARS 1-0"})]

    async def test_a_subscriber_hears_every_channel_it_asked_for(self) -> None:
        cache = MemoryCache()
        seen: list[str] = []

        async def listen() -> None:
            async for channel, _ in cache.subscribe(*ALL_CHANNELS):
                seen.append(channel)
                if len(seen) == 2:
                    return

        task = asyncio.create_task(listen())
        await asyncio.sleep(0.05)
        await cache.publish(CHANNEL_SCORES, {})
        await cache.publish(CHANNEL_ODDS, {})
        await asyncio.wait_for(task, timeout=2.0)

        assert set(seen) == {CHANNEL_SCORES, CHANNEL_ODDS}

    async def test_closing_a_subscription_deregisters_it(self) -> None:
        """Abandoning the iterator is not enough -- it must be closed.

        ``async for ...: return`` leaves the generator suspended, so its cleanup
        only runs at garbage collection and the queue stays subscribed. Every
        closed browser tab would leak one. The SSE endpoint wraps its
        subscription in ``contextlib.aclosing`` for exactly this reason.
        """
        cache = MemoryCache()

        async def listen() -> None:
            async with contextlib.aclosing(cache.subscribe(CHANNEL_SCORES)) as stream:
                async for _ in stream:
                    return

        task = asyncio.create_task(listen())
        await asyncio.sleep(0.05)
        assert cache._subscribers.get(CHANNEL_SCORES)

        await cache.publish(CHANNEL_SCORES, {})
        await asyncio.wait_for(task, timeout=2.0)

        assert not cache._subscribers.get(CHANNEL_SCORES)


class TestStreamAccess:
    async def test_the_stream_refuses_an_anonymous_caller(self, client: AsyncClient) -> None:
        response = await client.get("/api/stream")
        assert response.status_code == 401


class TestChangeDetection:
    """The poller publishes on change, not on schedule."""

    async def test_an_unchanged_payload_publishes_nothing(self) -> None:
        from services.poller.main import Poller
        from shared.config import Settings

        cache = MemoryCache()
        poller = Poller(Settings(), cache)
        published: list[str] = []

        async def spy(channel: str, payload: object) -> None:
            published.append(channel)

        cache.publish = spy  # type: ignore[method-assign]

        await poller.write("k", {"a": 1}, source="fpl", channel=CHANNEL_SCORES)
        assert published == [CHANNEL_SCORES]

        # Same payload again: cached, but nothing published.
        await poller.write("k", {"a": 1}, source="fpl", channel=CHANNEL_SCORES)
        assert published == [CHANNEL_SCORES]

        # A real change publishes again.
        await poller.write("k", {"a": 2}, source="fpl", channel=CHANNEL_SCORES)
        assert published == [CHANNEL_SCORES, CHANNEL_SCORES]
