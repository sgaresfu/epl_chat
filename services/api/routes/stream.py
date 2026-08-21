"""Server-Sent Events: the endpoint that makes the site feel alive.

SSE rather than WebSockets because the traffic is one-directional, it
reconnects on its own, and it survives proxies. A comment heartbeat every 20
seconds keeps idle connections from being culled by Render's proxy.

``EventSource`` sends cookies only with ``withCredentials: true``, and this
response needs the same CORS credential headers as every other route -- which
is why the allow-list is explicit and never ``*``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from shared.cache import ALL_CHANNELS

from services.api.auth import MAX_STREAMS_PER_PERSON
from services.api.deps import CurrentSession, State

log = structlog.get_logger(__name__)
router = APIRouter(tags=["stream"])

HEARTBEAT_SECONDS = 20.0


def sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.get("/api/stream")
async def stream(request: Request, session: CurrentSession, state: State) -> StreamingResponse:
    """Subscribe to live score, FPL and odds changes for as long as the tab is open."""
    person = session.person
    open_streams = state.streams.get(person, 0)
    if open_streams >= MAX_STREAMS_PER_PERSON:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many open connections. Close a tab and try again.",
        )
    state.streams[person] = open_streams + 1

    async def events() -> AsyncIterator[str]:
        log.info("sse.opened", person=person, open=state.streams[person])
        queue: asyncio.Queue[str] = asyncio.Queue()

        async def pump() -> None:
            # aclosing() guarantees the subscription's cleanup runs the moment
            # this task is cancelled. Without it the async generator is merely
            # suspended and its queue stays registered until garbage collection,
            # which leaks a subscriber for every closed tab.
            try:
                async with contextlib.aclosing(state.cache.subscribe(*ALL_CHANNELS)) as stream:
                    async for channel, payload in stream:
                        name = channel.rsplit(":", 1)[-1]
                        await queue.put(sse(name, payload))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("sse.subscription_failed", error=str(exc))

        task = asyncio.create_task(pump())
        try:
            # Tell the client immediately that the stream is live, so the UI can
            # drop its reconnecting indicator without waiting for real traffic.
            yield sse("hello", {"person": person, "at": datetime.now(UTC).isoformat()})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                    yield message
                except TimeoutError:
                    # A comment line, not an event: keeps proxies from culling
                    # an idle connection without waking any client handler.
                    yield ": heartbeat\n\n"
        finally:
            task.cancel()
            state.streams[person] = max(0, state.streams.get(person, 1) - 1)
            log.info("sse.closed", person=person, open=state.streams[person])

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Render and most CDNs buffer proxied responses unless told not to,
            # which would hold events until the buffer filled.
            "X-Accel-Buffering": "no",
        },
    )
