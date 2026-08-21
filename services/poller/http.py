"""Shared HTTP plumbing for every upstream client.

One pooled ``httpx.AsyncClient``, sane timeouts, ``tenacity`` retries with
backoff, and a record of every call so ``/admin`` reports real consumption
rather than an estimate. FPL in particular returns 503 around deadlines and at
season rollover, which is normal rather than exceptional, so retrying and then
serving the last good payload is the designed behaviour.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

log = structlog.get_logger(__name__)

TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)
LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)

USER_AGENT = "prediction-league/0.1 (four friends, one mini-league)"

# Headers upstreams use to report what is left of a quota.
QUOTA_HEADERS = (
    "x-requests-remaining",  # The Odds API
    "x-ratelimit-requests-remaining",  # API-Football
    "x-requests-used",
)


class UpstreamError(RuntimeError):
    """An upstream failed after retries. The caller serves cache instead."""

    def __init__(self, source: str, detail: str, status: int | None = None) -> None:
        super().__init__(f"{source}: {detail}")
        self.source = source
        self.detail = detail
        self.status = status


@dataclass
class CallRecord:
    """One upstream request, for the admin page and the logs."""

    source: str
    endpoint: str
    status: int
    latency_ms: int
    quota_remaining: str = ""
    ok: bool = True


@dataclass
class Upstream:
    """A single upstream API, with its own quota accounting."""

    name: str
    base_url: str
    headers: dict[str, str] = field(default_factory=dict)
    calls: list[CallRecord] = field(default_factory=list)

    _client: httpx.AsyncClient | None = None

    async def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=TIMEOUT,
                limits=LIMITS,
                headers={"User-Agent": USER_AGENT, **self.headers},
                follow_redirects=True,
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=8.0),
        reraise=True,
    )
    async def _request(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        client = await self.client()
        response = await client.get(path, params=params)
        # 4xx other than 429 is a bug in our request, not a blip; do not retry it.
        if response.status_code >= 500 or response.status_code == 429:
            response.raise_for_status()
        return response

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch and decode JSON, recording latency and quota headers."""
        started = time.perf_counter()
        try:
            response = await self._request(path, params)
        except httpx.HTTPError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            self.calls.append(CallRecord(self.name, path, 0, elapsed, ok=False))
            log.warning("upstream.failed", source=self.name, path=path, error=str(exc), ms=elapsed)
            raise UpstreamError(self.name, str(exc)) from exc

        elapsed = int((time.perf_counter() - started) * 1000)
        quota = next(
            (response.headers[h] for h in QUOTA_HEADERS if h in response.headers),
            "",
        )
        record = CallRecord(
            source=self.name,
            endpoint=path,
            status=response.status_code,
            latency_ms=elapsed,
            quota_remaining=quota,
            ok=response.is_success,
        )
        self.calls.append(record)
        log.info(
            "upstream.call",
            source=self.name,
            path=path,
            status=response.status_code,
            ms=elapsed,
            quota_remaining=quota or None,
        )

        if not response.is_success:
            raise UpstreamError(self.name, f"HTTP {response.status_code}", response.status_code)

        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError(self.name, "response was not JSON") from exc

    async def get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        """Fetch raw text, for RSS feeds that are not JSON."""
        started = time.perf_counter()
        try:
            response = await self._request(path, params)
        except httpx.HTTPError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            self.calls.append(CallRecord(self.name, path, 0, elapsed, ok=False))
            raise UpstreamError(self.name, str(exc)) from exc
        elapsed = int((time.perf_counter() - started) * 1000)
        self.calls.append(CallRecord(self.name, path, response.status_code, elapsed, ok=response.is_success))
        if not response.is_success:
            raise UpstreamError(self.name, f"HTTP {response.status_code}", response.status_code)
        return response.text

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
