"""bet365 prices from The Odds API.

BRIEF quota discipline: 500 calls a month, and **one call fetches the whole
round** -- never one call per match. Filtered to bet365 only; if bet365 has
no listed price for a match this says so rather than silently substituting
another book.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import structlog
from shared.clubs import find

from services.poller.http import Upstream

log = structlog.get_logger(__name__)

ODDS_API = "https://api.the-odds-api.com"
BOOKMAKER = "bet365"


def odds_client() -> Upstream:
    return Upstream(name="the-odds-api", base_url=ODDS_API)


async def fetch_odds(up: Upstream, api_key: str) -> list[dict[str, Any]]:
    """The whole round's events, bet365's h2h market only."""
    payload = await up.get_json(
        "/v4/sports/soccer_epl/odds",
        params={
            "apiKey": api_key,
            "regions": "uk",
            "markets": "h2h",
            "bookmakers": BOOKMAKER,
            "oddsFormat": "decimal",
        },
    )
    return payload if isinstance(payload, list) else []


@dataclass(frozen=True, slots=True)
class MatchOdds:
    home_club: str  # canonical short_name
    away_club: str
    home: float | None
    draw: float | None
    away: float | None
    available: bool
    reason: str = ""


def _bet365_prices(event: dict[str, Any]) -> tuple[float | None, float | None, float | None, bool, str]:
    """Pull bet365's h2h prices out of one event, or say why there are none.

    The brief is explicit: if bet365 is absent for a region, say so rather
    than silently showing another book's price instead.
    """
    home_name = event.get("home_team")
    away_name = event.get("away_team")
    for bookmaker in event.get("bookmakers", []):
        if bookmaker.get("key") != BOOKMAKER:
            continue
        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue
            prices: dict[str, float] = {}
            for outcome in market.get("outcomes", []):
                name, price = outcome.get("name"), outcome.get("price")
                if name and price is not None:
                    prices[name] = float(price)
            return (
                prices.get(home_name) if home_name else None,
                prices.get("Draw"),
                prices.get(away_name) if away_name else None,
                True,
                "",
            )
    return None, None, None, False, "bet365 has no listed price for this match."


def normalise(payload: list[dict[str, Any]]) -> dict[str, MatchOdds]:
    """Map every event to its two canonical clubs, keyed by ``"HOME-AWAY"``.

    An event this app cannot map to two of the 20 canonical clubs is dropped
    rather than raising: ``shared.clubs.resolve``'s loud-failure contract is
    for the canonical *lookup*, not for filtering an upstream's own payload,
    which may include a friendly or a club outside the league entirely.
    """
    out: dict[str, MatchOdds] = {}
    for event in payload:
        home = find(str(event.get("home_team") or ""))
        away = find(str(event.get("away_team") or ""))
        if home is None or away is None:
            log.info("odds.unmapped_event", home=event.get("home_team"), away=event.get("away_team"))
            continue
        home_price, draw_price, away_price, available, reason = _bet365_prices(event)
        out[f"{home.short_name}-{away.short_name}"] = MatchOdds(
            home_club=home.short_name,
            away_club=away.short_name,
            home=home_price,
            draw=draw_price,
            away=away_price,
            available=available,
            reason=reason,
        )
    return out


def to_cache_payload(matches: dict[str, MatchOdds]) -> dict[str, dict[str, Any]]:
    """JSON-safe form for :meth:`Poller.write`."""
    return {key: asdict(match) for key, match in matches.items()}
