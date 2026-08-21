"""Cache key names, shared by the poller that writes them and the api that reads.

Kept in one place so a typo cannot make the poller write somewhere the api never
looks -- a failure that shows up as a permanently empty panel with no error.
"""

from __future__ import annotations

from shared.cache import key

FPL_BOOTSTRAP = key("fpl", "bootstrap")
FPL_FIXTURES = key("fpl", "fixtures")
FPL_LEAGUE = key("fpl", "league")
TABLE = key("table", "live")
ODDS_ROUND = key("odds", "round")
NEWS_SKY = key("news", "sky")
NEWS_ATHLETIC = key("news", "athletic")
NEWS_YOUTUBE = key("news", "youtube")
EUROPE_STANDINGS = key("europe", "standings")
EUROPE_FIXTURES = key("europe", "fixtures")
TRANSFERS = key("transfers", "window")
PRESENCE = key("presence", "now")


def fpl_live(gameweek: int) -> str:
    return key("fpl", "live", gameweek)


def fpl_picks(entry_id: int, gameweek: int) -> str:
    return key("fpl", "picks", entry_id, gameweek)


def fpl_history(entry_id: int) -> str:
    return key("fpl", "history", entry_id)


def lineups(fixture_id: int) -> str:
    return key("lineups", fixture_id)


def quota(source: str, window: str) -> str:
    return key("quota", source, window)


# Human labels for the admin page's cache-age table.
LABELS: dict[str, str] = {
    FPL_BOOTSTRAP: "FPL bootstrap (teams, players, gameweeks)",
    FPL_FIXTURES: "FPL fixtures",
    FPL_LEAGUE: "FPL mini-league",
    TABLE: "Live table",
    ODDS_ROUND: "bet365 odds",
    NEWS_SKY: "Sky Sports news",
    NEWS_ATHLETIC: "The Athletic headlines",
    NEWS_YOUTUBE: "YouTube uploads",
    EUROPE_STANDINGS: "Champions League standings",
    EUROPE_FIXTURES: "Champions League fixtures",
}

# Freshness budgets, in seconds. Exceeding one does not clear the entry -- it
# only makes the UI say how old the number is.
TTL: dict[str, float] = {
    FPL_BOOTSTRAP: 600,
    FPL_FIXTURES: 300,
    FPL_LEAGUE: 300,
    TABLE: 120,
    ODDS_ROUND: 1800,
    NEWS_SKY: 900,
    NEWS_ATHLETIC: 1800,
    NEWS_YOUTUBE: 1800,
    EUROPE_STANDINGS: 900,
    EUROPE_FIXTURES: 900,
}
