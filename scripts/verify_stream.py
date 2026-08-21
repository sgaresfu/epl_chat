"""Verify SSE against a real uvicorn server, not an in-process transport.

The brief is explicit that the stream must be tested for real, because an
infinite streaming response behaves differently over a socket than it does
through an ASGI test transport -- buffering, chunking and disconnect detection
all differ. This starts the actual api, signs in with a real cookie, opens a
real EventSource-shaped request, publishes a change, and checks it arrives.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

BASE = "http://127.0.0.1:8099"


async def main() -> int:
    import uvicorn
    from services.api.deps import AppState
    from services.api.main import create_app
    from shared import keys
    from shared.cache import CHANNEL_SCORES, MemoryCache
    from shared.config import Settings

    cache = MemoryCache()
    seed = Path("/tmp/cache_seed.json")
    if seed.exists():  # noqa: ASYNC240 - one-shot script, not a request handler
        for name, value in json.loads(seed.read_text()).items():  # noqa: ASYNC240
            await cache.set(name, value, source="fpl")

    settings = Settings(
        environment="local",
        session_secret="verify-secret-abcdefghijklmnopqrstuvwxyz",
        code_coyg="verify-coyg",
        frontend_origin="http://localhost:5173",
    )

    app = create_app()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def noop_lifespan(_app: object):  # type: ignore[no-untyped-def]
        yield

    app.router.lifespan_context = noop_lifespan  # type: ignore[assignment]
    app.state.app_state = AppState(settings=settings, cache=cache)

    config = uvicorn.Config(app, host="127.0.0.1", port=8099, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    for _ in range(50):
        await asyncio.sleep(0.1)
        if server.started:
            break
    else:
        print("FAIL: server did not start")
        return 1

    failures = 0
    try:
        async with httpx.AsyncClient(base_url=BASE, timeout=10.0) as http:
            # 1. Sign in over the wire and keep the cookie, exactly as a browser would.
            login = await http.post("/api/session", json={"code": "verify-coyg"})
            assert login.status_code == 200, login.text
            print(f"  login              -> {login.status_code} as {login.json()['person']['key']}")
            assert "pl_session" in http.cookies, "no session cookie was set"
            print("  session cookie     -> set")

            # 2. Cached GET latency, the p95 target from the definition of done.
            import time

            samples = []
            for _ in range(30):
                started = time.perf_counter()
                response = await http.get("/api/table")
                assert response.status_code == 200
                samples.append((time.perf_counter() - started) * 1000)
            samples.sort()
            p95 = samples[int(len(samples) * 0.95) - 1]
            print(f"  GET /api/table     -> p95 {p95:.1f}ms over {len(samples)} calls")
            if p95 >= 100:
                print(f"  FAIL: p95 {p95:.1f}ms exceeds the 100ms target")
                failures += 1

            # 3. Open the stream and read the greeting.
            received: list[str] = []

            async def read_stream() -> None:
                async with http.stream("GET", "/api/stream") as response:
                    assert response.status_code == 200, response.status_code
                    ctype = response.headers["content-type"]
                    assert ctype.startswith("text/event-stream"), ctype
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            received.append(line.split(": ", 1)[1])
                            if len(received) >= 2:
                                return

            reader = asyncio.create_task(read_stream())
            await asyncio.sleep(0.4)

            # 4. Publish a change and confirm it arrives down the open socket.
            await cache.publish(CHANNEL_SCORES, {"key": keys.TABLE, "goal": "ARS 1-0"})
            try:
                await asyncio.wait_for(reader, timeout=5.0)
            except TimeoutError:
                reader.cancel()
                print(f"  FAIL: no event delivered; received {received}")
                failures += 1
            else:
                print(f"  SSE events         -> {received}")
                if received != ["hello", "scores"]:
                    print(f"  FAIL: expected ['hello', 'scores'], got {received}")
                    failures += 1

            # 5. CORS must be an explicit origin, never a wildcard.
            cors = await http.get("/api/table", headers={"Origin": "http://localhost:5173"})
            allow = cors.headers.get("access-control-allow-origin")
            creds = cors.headers.get("access-control-allow-credentials")
            print(f"  CORS origin        -> {allow} (credentials: {creds})")
            if allow == "*":
                print("  FAIL: wildcard CORS is rejected by browsers when credentials are sent")
                failures += 1
            if creds != "true":
                print("  FAIL: EventSource needs allow-credentials")
                failures += 1
    finally:
        server.should_exit = True
        await task

    print("\nRESULT:", "PASS" if failures == 0 else f"FAIL ({failures})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
