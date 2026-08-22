"""bet365 prices, from a source that needs no key.

The brief names The Odds API, whose free tier is 500 calls a month and needs a
credential. That credential was never issued, so the odds panel shipped dark:
correct code, permanently empty.

**football-data.co.uk publishes the same numbers for free.** Its
``fixtures.csv`` carries ``B365H``/``B365D``/``B365A`` -- Bet365's 1X2 prices,
the exact market BRIEF section 6 asks for -- for every upcoming fixture across
the major European leagues, with no key, no registration and no quota. It also
publishes the market maximum and average, which the paid API does not.

So this prefers the free CSV and keeps The Odds API as an optional upgrade: set
``ODDS_API_KEY`` and it takes over, giving a fresher in-play price. Neither path
is required for the panel to work, which is the point.
"""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from typing import Any

import structlog
from shared.clubs import find

from services.poller.http import Upstream

log = structlog.get_logger(__name__)

FOOTBALL_DATA = "https://www.football-data.co.uk"
FIXTURES_PATH = "/fixtures.csv"
# football-data.co.uk's code for the Premier League. E1/E2/E3 are the divisions
# below it and EC is the Conference; all four share the file.
PREMIER_LEAGUE_DIV = "E0"

ODDS_API = "https://api.the-odds-api.com"
BOOKMAKER = "bet365"


def odds_client() -> Upstream:
    """The keyless source. No credential, so this always works."""
    return Upstream(name="football-data", base_url=FOOTBALL_DATA)


def odds_api_client() -> Upstream:
    return Upstream(name="the-odds-api", base_url=ODDS_API)


@dataclass(frozen=True, slots=True)
class MatchOdds:
    home_club: str  # canonical short_name
    away_club: str
    home: float | None
    draw: float | None
    away: float | None
    bookmaker: str
    # The best price anywhere in the market, where the source publishes it.
    # Useful context: a bet365 price well below the market max is a short one.
    market_max: dict[str, float] | None
    available: bool
    reason: str = ""


def _price(row: dict[str, str], column: str) -> float | None:
    raw = (row.get(column) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    # A decimal price below evens is impossible; treat it as a bad cell rather
    # than rendering a number that would read as a 500% favourite.
    return value if value > 1.0 else None


def parse_fixtures_csv(text: str) -> dict[str, MatchOdds]:
    """Read football-data.co.uk's fixture file into canonical match keys.

    Deliberately tolerant: the file covers a dozen leagues and changes shape
    between seasons, so a row this app cannot map is skipped rather than
    raising. Only the Premier League division is kept.
    """
    # football-data.co.uk serves the file with a UTF-8 BOM. Left in place it
    # becomes part of the first column's name -- "\ufeffDiv" rather than "Div"
    # -- so the division filter below matches nothing and the entire league is
    # silently skipped, with no error anywhere to say why.
    out: dict[str, MatchOdds] = {}
    for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        if (row.get("Div") or "").strip() != PREMIER_LEAGUE_DIV:
            continue
        home = find((row.get("HomeTeam") or "").strip())
        away = find((row.get("AwayTeam") or "").strip())
        if home is None or away is None:
            log.info("odds.unmapped_row", home=row.get("HomeTeam"), away=row.get("AwayTeam"))
            continue

        h, d, a = _price(row, "B365H"), _price(row, "B365D"), _price(row, "B365A")
        max_h, max_d, max_a = _price(row, "MaxH"), _price(row, "MaxD"), _price(row, "MaxA")
        market_max = (
            {"home": max_h, "draw": max_d, "away": max_a} if None not in (max_h, max_d, max_a) else None
        )

        available = None not in (h, d, a)
        out[f"{home.short_name}-{away.short_name}"] = MatchOdds(
            home_club=home.short_name,
            away_club=away.short_name,
            home=h,
            draw=d,
            away=a,
            bookmaker=BOOKMAKER,
            market_max=market_max,  # type: ignore[arg-type]
            available=available,
            reason="" if available else "bet365 has no listed price for this match yet.",
        )
    return out


async def fetch_free_odds(up: Upstream) -> dict[str, MatchOdds]:
    """The whole upcoming round, keyless."""
    text = await up.get_text(FIXTURES_PATH)
    matches = parse_fixtures_csv(text)
    log.info("odds.free_fetched", matches=len(matches))
    return matches


# --------------------------------------------------------------------------
# The Odds API — optional, only when a key is configured
# --------------------------------------------------------------------------


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
            bookmaker=BOOKMAKER,
            market_max=None,
            available=available,
            reason=reason,
        )
    return out


def to_cache_payload(matches: dict[str, MatchOdds]) -> dict[str, dict[str, Any]]:
    """JSON-safe form for :meth:`Poller.write`."""
    return {key: asdict(match) for key, match in matches.items()}
