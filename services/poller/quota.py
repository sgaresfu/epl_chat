"""Quota guards for the two metered upstreams.

BRIEF section 15's stated intervals overrun both free tiers, so the ceiling is
enforced here rather than trusted to arithmetic that was never done:

* **The Odds API** allows 500 calls a month. Polling every 30 minutes needs
  30 x 48 = 1,440 -- nearly three times the allowance. Odds are therefore
  fetched only inside a window around each round.
* **API-Football** allows 100 calls a day. Polling live events during play would
  spend that on a single afternoon, so match minutes come from FPL (free,
  unmetered) and this budget is reserved for on-demand line-ups.

Every spend is counted in the cache so ``/admin`` reports real consumption, and
a refused call returns a reason the UI can show rather than failing silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from shared.cache import Cache
from shared.keys import quota

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Verdict:
    allowed: bool
    used: int
    budget: int
    reason: str = ""

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.used)


def _window(scope: str, now: datetime) -> str:
    return now.strftime("%Y-%m") if scope == "month" else now.strftime("%Y-%m-%d")


async def check(cache: Cache, source: str, scope: str, budget: int, now: datetime | None = None) -> Verdict:
    """Whether one more call to ``source`` is within budget."""
    now = now or datetime.now(UTC)
    entry = await cache.get(quota(source, _window(scope, now)))
    used = int(entry.value) if entry else 0
    if used >= budget:
        reason = (
            f"{source} has used its {scope}ly budget of {budget} calls. "
            "Serving the last cached payload instead."
        )
        log.warning("quota.exhausted", source=source, used=used, budget=budget)
        return Verdict(False, used, budget, reason)
    return Verdict(True, used, budget)


async def spend(cache: Cache, source: str, scope: str, now: datetime | None = None) -> int:
    """Record one call against the budget."""
    now = now or datetime.now(UTC)
    name = quota(source, _window(scope, now))
    entry = await cache.get(name)
    used = (int(entry.value) if entry else 0) + 1
    await cache.set(name, used, source="quota")
    return used
