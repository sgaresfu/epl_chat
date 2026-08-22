"""Odds tests: parsing bet365's prices, building the response, quota discipline.

Fixture id 1 in the captured payload is Arsenal (team_h=1) v Coventry
(team_h_a=7, canonical short_name "COV") -- the same season opener used in
test_news.py's fixture data -- so odds-cache keys below use ``ARS-COV``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from httpx import AsyncClient
from services.poller.odds import _bet365_prices, normalise, to_cache_payload
from shared.cache import MemoryCache
from shared.config import Settings
from shared.db import OddsHistory

from tests.conftest import sign_in

EVENT_TEMPLATE: dict[str, Any] = {
    "home_team": "Arsenal",
    "away_team": "Coventry City",
    "bookmakers": [
        {
            "key": "bet365",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Arsenal", "price": 1.40},
                        {"name": "Draw", "price": 4.75},
                        {"name": "Coventry City", "price": 8.00},
                    ],
                }
            ],
        }
    ],
}


class TestBet365Prices:
    def test_the_three_prices_are_read(self) -> None:
        home, draw, away, available, reason = _bet365_prices(EVENT_TEMPLATE)
        assert (home, draw, away) == (1.40, 4.75, 8.00)
        assert available is True
        assert reason == ""

    def test_a_missing_bet365_book_is_reported_not_substituted(self) -> None:
        event = {**EVENT_TEMPLATE, "bookmakers": [{"key": "pinnacle", "markets": []}]}
        home, draw, away, available, reason = _bet365_prices(event)
        assert (home, draw, away) == (None, None, None)
        assert available is False
        assert "bet365" in reason

    def test_no_bookmakers_at_all_is_reported_not_an_exception(self) -> None:
        _home, _draw, _away, available, reason = _bet365_prices({})
        assert available is False
        assert reason


class TestNormalise:
    def test_the_two_clubs_resolve_to_canonical_short_names(self) -> None:
        matches = normalise([EVENT_TEMPLATE])
        assert "ARS-COV" in matches
        match = matches["ARS-COV"]
        assert match.home_club == "ARS"
        assert match.away_club == "COV"
        assert match.home == 1.40

    def test_an_unmapped_club_is_dropped_not_fatal(self) -> None:
        """The whole round's payload must survive one club this app cannot map."""
        event = {**EVENT_TEMPLATE, "home_team": "Real Madrid", "away_team": "Not A Real Club"}
        assert normalise([event]) == {}

    def test_one_unmapped_event_does_not_drop_the_rest(self) -> None:
        bad = {**EVENT_TEMPLATE, "home_team": "Nowhere FC", "away_team": "Not A Real Club"}
        matches = normalise([bad, EVENT_TEMPLATE])
        assert list(matches) == ["ARS-COV"]

    def test_the_cache_payload_survives_a_json_round_trip(self) -> None:
        import json

        matches = normalise([EVENT_TEMPLATE])
        payload = to_cache_payload(matches)
        assert json.loads(json.dumps(payload)) == payload
        assert payload["ARS-COV"]["home"] == 1.40


class TestBuildOddsForRow:
    ROW: ClassVar[dict[str, Any]] = {"id": 1, "team_h": 1, "team_a": 7}
    NOW = datetime(2026, 9, 1, tzinfo=UTC)

    def test_no_cache_yet_is_reported_distinctly(self) -> None:
        from services.api.views import build_odds_for_row

        price = build_odds_for_row(self.ROW, None, [], self.NOW)
        assert price.available is False
        assert "not been fetched" in (price.reason or "")

    def test_an_unavailable_match_carries_its_own_reason(self) -> None:
        from services.api.views import build_odds_for_row

        cache = {"ARS-COV": {"available": False, "reason": "bet365 has no listed price for this match."}}
        price = build_odds_for_row(self.ROW, cache, [], self.NOW)
        assert price.available is False
        assert "bet365" in (price.reason or "")

    def test_an_available_match_carries_its_prices(self) -> None:
        from services.api.views import build_odds_for_row

        cache = {
            "ARS-COV": {
                "home": 1.40,
                "draw": 4.75,
                "away": 8.00,
                "bookmaker": "bet365",
                "available": True,
                "reason": "",
            }
        }
        price = build_odds_for_row(self.ROW, cache, [], self.NOW)
        assert price.available is True
        assert price.home == 1.40
        assert price.bookmaker == "bet365"
        assert price.drift is None, "fewer than two history points means no drift to show"

    def test_drift_pairs_a_week_old_baseline_with_the_live_price(self) -> None:
        from services.api.views import build_odds_for_row

        cache = {
            "ARS-COV": {"home": 1.65, "draw": 4.50, "away": 6.50, "bookmaker": "bet365", "available": True}
        }
        history = [
            OddsHistory(
                fixture_id=1, captured_at=self.NOW - timedelta(days=6), home=1.40, draw=4.75, away=8.00
            ),
            OddsHistory(
                fixture_id=1, captured_at=self.NOW - timedelta(hours=1), home=1.65, draw=4.50, away=6.50
            ),
        ]
        price = build_odds_for_row(self.ROW, cache, history, self.NOW)
        assert price.drift == {"home": 1.40, "draw": 4.75, "away": 8.00}
        assert price.home == 1.65, "the live price is unchanged by drift, only the baseline is attached"

    def test_a_single_history_point_yields_no_drift(self) -> None:
        from services.api.views import build_odds_for_row

        cache = {
            "ARS-COV": {"home": 1.65, "draw": 4.50, "away": 6.50, "bookmaker": "bet365", "available": True}
        }
        history = [OddsHistory(fixture_id=1, captured_at=self.NOW, home=1.65, draw=4.50, away=6.50)]
        price = build_odds_for_row(self.ROW, cache, history, self.NOW)
        assert price.drift is None

    async def test_history_read_back_from_sqlite_still_compares(self, sessions: Any) -> None:
        """A regression test for a real bug: SQLite (dev and this test suite)
        hands back a *naive* datetime for a ``DateTime(timezone=True))``
        column even though the value stored is always UTC, while Postgres
        (production) does not have this quirk. Constructing ``OddsHistory``
        rows directly in Python -- as every other test in this file does --
        never exercises this, because the objects keep whatever tzinfo the
        test gave them. Only a real write-then-read through the database
        surfaces it, which is exactly what broke ``/api/fixtures/1`` the
        first time this endpoint was hit with real seeded data.
        """
        from services.api.repository import odds_drift
        from services.api.views import build_odds_for_row

        async with sessions() as db:
            db.add(
                OddsHistory(
                    fixture_id=1, captured_at=self.NOW - timedelta(days=6), home=1.40, draw=4.75, away=8.00
                )
            )
            db.add(
                OddsHistory(
                    fixture_id=1, captured_at=self.NOW - timedelta(hours=1), home=1.65, draw=4.50, away=6.50
                )
            )
            await db.commit()

        async with sessions() as db:
            history = await odds_drift(db, 1)
        assert history[0].captured_at.tzinfo is None, "confirms this test exercises the naive-datetime path"

        cache = {
            "ARS-COV": {"home": 1.65, "draw": 4.50, "away": 6.50, "bookmaker": "bet365", "available": True}
        }
        price = build_odds_for_row(self.ROW, cache, history, self.NOW)  # must not raise
        assert price.drift == {"home": 1.40, "draw": 4.75, "away": 8.00}


class TestFreeSource:
    """The default path: football-data.co.uk, no key, no quota.

    The brief names The Odds API, but that credential was never issued and the
    panel shipped dark because of it. This source publishes the same bet365
    1X2 prices for free, so the panel works out of the box.
    """

    CSV = (
        "Div,Date,Time,HomeTeam,AwayTeam,B365H,B365D,B365A,MaxH,MaxD,MaxA\n"
        "E0,21/08/2026,20:00,Arsenal,Coventry,1.2,7,13,1.23,7.5,16.5\n"
        "E0,22/08/2026,12:30,Hull,Man United,8.5,5,1.36,9,5.25,1.39\n"
        "E1,22/08/2026,15:00,Millwall,Watford,2.1,3.4,3.5,2.2,3.5,3.6\n"
        "E0,23/08/2026,14:00,Brighton,Aston Villa,,,,,,\n"
        "E0,23/08/2026,16:30,Nowhere FC,Not A Club,2.0,3.0,4.0,2.1,3.1,4.1\n"
    )

    def test_only_the_premier_league_division_is_kept(self) -> None:
        from services.poller.odds import parse_fixtures_csv

        matches = parse_fixtures_csv(self.CSV)
        assert "ARS-COV" in matches
        assert not [k for k in matches if "MIL" in k], "E1 is the Championship, not this league"

    def test_prices_are_read_for_a_priced_match(self) -> None:
        from services.poller.odds import parse_fixtures_csv

        m = parse_fixtures_csv(self.CSV)["ARS-COV"]
        assert (m.home, m.draw, m.away) == (1.2, 7.0, 13.0)
        assert m.available is True
        assert m.bookmaker == "bet365"

    def test_the_market_maximum_is_carried_alongside(self) -> None:
        from services.poller.odds import parse_fixtures_csv

        m = parse_fixtures_csv(self.CSV)["ARS-COV"]
        assert m.market_max == {"home": 1.23, "draw": 7.5, "away": 16.5}

    def test_a_row_with_no_prices_yet_is_unavailable_not_absent(self) -> None:
        from services.poller.odds import parse_fixtures_csv

        m = parse_fixtures_csv(self.CSV)["BHA-AVL"]
        assert m.available is False
        assert m.reason
        assert m.home is None

    def test_an_unmappable_club_is_skipped_not_fatal(self) -> None:
        from services.poller.odds import parse_fixtures_csv

        matches = parse_fixtures_csv(self.CSV)
        assert len(matches) == 3, "Arsenal, Hull and Brighton map; the fake club does not"

    def test_a_utf8_bom_does_not_void_the_division_filter(self) -> None:
        """A regression test for a bug that returned zero matches, silently.

        football-data.co.uk serves the file with a BOM. Left in place it
        becomes part of the first column's name -- "\ufeffDiv" rather than
        "Div" -- so ``row.get("Div")`` is None for every row, the division
        filter matches nothing, and the whole league vanishes with no error.
        """
        from services.poller.odds import parse_fixtures_csv

        assert parse_fixtures_csv("\ufeff" + self.CSV) == parse_fixtures_csv(self.CSV)
        assert len(parse_fixtures_csv("\ufeff" + self.CSV)) == 3

    def test_a_nonsense_price_is_dropped_rather_than_rendered(self) -> None:
        """A decimal price at or below evens is impossible."""
        from services.poller.odds import parse_fixtures_csv

        bad = "Div,HomeTeam,AwayTeam,B365H,B365D,B365A\nE0,Arsenal,Coventry,0.5,x,13\n"
        m = parse_fixtures_csv(bad)["ARS-COV"]
        assert m.home is None
        assert m.draw is None
        assert m.available is False

    def test_an_empty_file_yields_nothing_rather_than_raising(self) -> None:
        from services.poller.odds import parse_fixtures_csv

        assert parse_fixtures_csv("") == {}
        assert parse_fixtures_csv("Div,HomeTeam\n") == {}


class TestPoller:
    """Quota only gates the optional paid feed; the free one is unmetered."""

    async def test_an_exhausted_quota_falls_back_to_the_free_source(self, monkeypatch: Any) -> None:
        """Running out of paid calls must not take the panel down with it."""
        from services.poller import odds as odds_mod
        from services.poller.main import Poller
        from shared.cache import MemoryCache
        from shared.keys import quota

        async def fake_free(up: Any) -> dict[str, Any]:
            return {"ARS-COV": odds_mod.MatchOdds("ARS", "COV", 1.4, 4.75, 8.0, "bet365", None, True)}

        monkeypatch.setattr(odds_mod, "fetch_free_odds", fake_free)

        settings = Settings(odds_api_key="test-key", odds_monthly_budget=1)
        cache = MemoryCache()
        await cache.set(quota("the-odds-api", datetime.now(UTC).strftime("%Y-%m")), 1, source="quota")

        poller = Poller(settings, cache)
        try:
            await poller.poll_odds()
        finally:
            await poller.close()

        entry = await cache.get("pl2627:odds:round")
        assert entry is not None, "the free source must still fill the cache"
        assert entry.source == "football-data"

    async def test_the_free_source_runs_with_no_key_at_all(self, monkeypatch: Any) -> None:
        from services.poller import odds as odds_mod
        from services.poller.main import Poller
        from shared.cache import MemoryCache

        async def fake_free(up: Any) -> dict[str, Any]:
            return {"ARS-COV": odds_mod.MatchOdds("ARS", "COV", 1.4, 4.75, 8.0, "bet365", None, True)}

        monkeypatch.setattr(odds_mod, "fetch_free_odds", fake_free)

        cache = MemoryCache()
        poller = Poller(Settings(odds_api_key=""), cache)
        try:
            await poller.poll_odds()
        finally:
            await poller.close()

        entry = await cache.get("pl2627:odds:round")
        assert entry is not None
        assert entry.value["ARS-COV"]["home"] == 1.4


class TestEndpoint:
    async def test_an_unpolled_cache_says_so_rather_than_blaming_a_key(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fixtures/1")).json()
        assert body["odds"]["available"] is False
        assert "not been fetched" in body["odds"]["reason"]
        assert "KEY" not in body["odds"]["reason"], "odds no longer need a credential"

    async def test_it_needs_a_session(self, client: AsyncClient) -> None:
        assert (await client.get("/api/odds")).status_code == 401

    async def test_the_whole_round_lists_fixtures_before_the_poller_runs(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/odds")).json()
        assert body["fixtures"], "gameweek 1 should list fixtures even with no odds yet"
        assert all(f["odds"]["available"] is False for f in body["fixtures"])


class TestAdminQuotaReporting:
    """The bug: admin.py read the literal scope string ('month') as the cache
    key instead of the computed calendar window ('2026-09') that
    services/poller/quota.py actually writes to -- so the panel always showed
    zero no matter how much had actually been spent.
    """

    async def test_a_real_spend_is_reflected_not_read_as_zero(
        self, client: AsyncClient, cache: MemoryCache
    ) -> None:
        from services.poller.quota import spend

        await sign_in(client, "coyg")

        await spend(cache, "the-odds-api", "month")
        await spend(cache, "the-odds-api", "month")

        body = (await client.get("/api/admin/status")).json()
        odds_quota = next(q for q in body["quotas"] if q["source"] == "the-odds-api")
        assert odds_quota["used"] == 2
