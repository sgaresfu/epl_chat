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

    def test_a_missing_key_is_reported_by_name(self) -> None:
        from services.api.views import build_odds_for_row

        price = build_odds_for_row(self.ROW, None, [], self.NOW, "ODDS_API_KEY needed")
        assert price.available is False
        assert "ODDS_API_KEY" in (price.reason or "")

    def test_no_cache_yet_is_reported_distinctly(self) -> None:
        from services.api.views import build_odds_for_row

        price = build_odds_for_row(self.ROW, None, [], self.NOW, None)
        assert price.available is False
        assert "not been fetched" in (price.reason or "")

    def test_an_unavailable_match_carries_its_own_reason(self) -> None:
        from services.api.views import build_odds_for_row

        cache = {"ARS-COV": {"available": False, "reason": "bet365 has no listed price for this match."}}
        price = build_odds_for_row(self.ROW, cache, [], self.NOW, None)
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
        price = build_odds_for_row(self.ROW, cache, [], self.NOW, None)
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
        price = build_odds_for_row(self.ROW, cache, history, self.NOW, None)
        assert price.drift == {"home": 1.40, "draw": 4.75, "away": 8.00}
        assert price.home == 1.65, "the live price is unchanged by drift, only the baseline is attached"

    def test_a_single_history_point_yields_no_drift(self) -> None:
        from services.api.views import build_odds_for_row

        cache = {
            "ARS-COV": {"home": 1.65, "draw": 4.50, "away": 6.50, "bookmaker": "bet365", "available": True}
        }
        history = [OddsHistory(fixture_id=1, captured_at=self.NOW, home=1.65, draw=4.50, away=6.50)]
        price = build_odds_for_row(self.ROW, cache, history, self.NOW, None)
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
        price = build_odds_for_row(self.ROW, cache, history, self.NOW, None)  # must not raise
        assert price.drift == {"home": 1.40, "draw": 4.75, "away": 8.00}


class TestPoller:
    """The poller's quota gate and its no-key no-op."""

    async def test_no_key_is_a_silent_no_op(self) -> None:
        from services.poller.main import Poller
        from shared.cache import MemoryCache

        cache = MemoryCache()
        poller = Poller(Settings(odds_api_key=""), cache)
        try:
            await poller.poll_odds()
        finally:
            await poller.close()
        assert await cache.get("pl2627:odds:round") is None

    async def test_an_exhausted_quota_is_a_silent_no_op(self) -> None:
        from services.poller.main import Poller
        from shared.cache import MemoryCache
        from shared.keys import quota

        settings = Settings(odds_api_key="test-key", odds_monthly_budget=1)
        cache = MemoryCache()
        window = datetime.now(UTC).strftime("%Y-%m")
        await cache.set(quota("the-odds-api", window), 1, source="quota")

        poller = Poller(settings, cache)
        try:
            await poller.poll_odds()
        finally:
            await poller.close()
        assert await cache.get("pl2627:odds:round") is None


class TestEndpoint:
    async def test_a_missing_key_names_itself_on_the_fixture(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fixtures/1")).json()
        assert body["odds"]["available"] is False
        assert "ODDS_API_KEY" in body["odds"]["reason"]

    async def test_it_needs_a_session(self, client: AsyncClient) -> None:
        assert (await client.get("/api/odds")).status_code == 401

    async def test_the_whole_round_reports_the_missing_key_too(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/odds")).json()
        assert body["fixtures"], "gameweek 1 should list fixtures even with no odds yet"
        assert all(f["odds"]["available"] is False for f in body["fixtures"])
        assert "ODDS_API_KEY" in body["freshness"]["reason"]


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
