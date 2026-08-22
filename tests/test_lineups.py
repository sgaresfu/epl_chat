"""Line-up tests: club-matched normalisation, fixture-id resolution, the
on-demand fetch/cache/quota orchestration, and the one route allowed to
reach an upstream on a user's own request.

Fixture id 1 in the captured payload is Arsenal (team_h=1) v Coventry
(team_a=7), kicking off 2026-08-21 -- the same fixture used in test_odds.py.
"""

from __future__ import annotations

import time
from typing import Any

from httpx import AsyncClient
from services.poller.api_football import (
    LineupPlayer,
    _players,
    normalise,
    resolve_fixture_ids,
)
from shared.cache import Entry, MemoryCache
from shared.config import Settings

from tests.conftest import sign_in


def backdate(cache: MemoryCache, key: str, value: object, seconds_ago: float) -> None:
    """Age a cache entry past any TTL, without waiting on real time."""
    cache._data[key] = Entry(value=value, written_at=time.time() - seconds_ago, source="api-football")


ROW: dict[str, Any] = {"id": 1, "team_h": 1, "team_a": 7, "kickoff_time": "2026-08-21T19:00:00Z"}

LINEUPS_PAYLOAD: dict[str, Any] = {
    "response": [
        {
            "team": {"id": 1, "name": "Arsenal FC"},
            "formation": "4-3-3",
            "startXI": [
                {"player": {"id": 1, "name": "David Raya", "number": 1, "pos": "G"}},
                {"player": {"id": 2, "name": "William Saliba", "number": 2, "pos": "D"}},
            ],
            "substitutes": [{"player": {"id": 3, "name": "Neto", "number": 31, "pos": "G"}}],
        },
        {
            "team": {"id": 7, "name": "Coventry City"},
            "formation": "4-4-2",
            "startXI": [{"player": {"id": 4, "name": "Ben Wilson", "number": 1, "pos": "G"}}],
            "substitutes": [],
        },
    ]
}

FIXTURES_PAYLOAD: dict[str, Any] = {
    "response": [
        {
            "fixture": {"id": 999001, "date": "2026-08-21T19:00:00+00:00"},
            "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Coventry"}},
        },
        {
            "fixture": {"id": 999002, "date": "2026-08-21T19:00:00+00:00"},
            "teams": {"home": {"name": "Real Madrid"}, "away": {"name": "Not A Real Club"}},
        },
    ]
}


class TestPlayers:
    def test_named_players_are_read(self) -> None:
        rows = [{"player": {"name": "David Raya", "number": 1, "pos": "G"}}]
        players = _players(rows)
        assert players == [LineupPlayer(name="David Raya", number=1, position="G")]

    def test_a_player_with_no_name_is_dropped_not_fatal(self) -> None:
        rows = [{"player": {"number": 1, "pos": "G"}}, {"player": {"name": "David Raya"}}]
        assert len(_players(rows)) == 1

    def test_empty_rows_yield_no_players(self) -> None:
        assert _players([]) == []


class TestNormalise:
    def test_the_two_sides_are_matched_by_club_not_array_order(self) -> None:
        home, away = normalise(LINEUPS_PAYLOAD, "ARS", "COV")
        assert home is not None
        assert away is not None
        assert home.formation == "4-3-3"
        assert away.formation == "4-4-2"
        assert [p.name for p in home.starting] == ["David Raya", "William Saliba"]
        assert [p.name for p in away.starting] == ["Ben Wilson"]

    def test_a_reversed_response_order_still_matches_correctly(self) -> None:
        """API-Football makes no ordering promise between the two sides."""
        reversed_payload = {"response": list(reversed(LINEUPS_PAYLOAD["response"]))}
        home, away = normalise(reversed_payload, "ARS", "COV")
        assert home is not None
        assert home.formation == "4-3-3"
        assert away is not None
        assert away.formation == "4-4-2"

    def test_not_out_yet_is_an_empty_response_not_an_exception(self) -> None:
        home, away = normalise({"response": []}, "ARS", "COV")
        assert (home, away) == (None, None)

    def test_an_unmapped_club_in_the_response_is_skipped(self) -> None:
        payload = {"response": [{"team": {"name": "Not A Real Club"}, "formation": "4-4-2", "startXI": []}]}
        home, away = normalise(payload, "ARS", "COV")
        assert (home, away) == (None, None)


class TestResolveFixtureIds:
    async def test_the_two_clubs_resolve_to_canonical_short_names(self, monkeypatch: Any) -> None:
        from services.poller.api_football import api_football_client

        up = api_football_client("test-key")

        async def fake_get_json(path: str, params: Any = None) -> Any:
            return FIXTURES_PAYLOAD

        monkeypatch.setattr(up, "get_json", fake_get_json)
        mapping = await resolve_fixture_ids(up, "2026-08-21", 2026)
        assert mapping == {"ARS-COV": 999001}
        await up.close()


class TestGetLineups:
    async def test_no_key_falls_back_to_a_predicted_xi(self, cache: MemoryCache) -> None:
        """No API-Football credential was ever issued, so a permanently empty
        panel was the old behaviour. FPL knows who has been starting; predict
        from that and label it, rather than showing nothing for ever.
        """
        from services.api.lineups import get_lineups

        result = await get_lineups(1, ROW, [ROW], cache, Settings(api_football_key=""))
        # The slim test bootstrap carries only nine players, too few for an XI,
        # so this asserts the honest refusal rather than a fabricated team.
        assert result.confirmed is False
        assert "API_FOOTBALL_KEY" not in (result.reason or ""), "no longer a credential problem"

    async def test_a_cached_answer_within_ttl_is_served_without_any_upstream_call(self) -> None:
        from services.api.lineups import get_lineups
        from shared.keys import lineups as lineups_key
        from shared.models import LineupsOut

        cache = MemoryCache()
        cached = LineupsOut(available=False, reason="Line-ups are not out yet.")
        await cache.set(lineups_key(1), cached.model_dump(mode="json"), source="api-football")

        result = await get_lineups(1, ROW, [ROW], cache, Settings(api_football_key="test-key"))
        assert result.reason == "Line-ups are not out yet."

    async def test_a_fixture_with_no_kickoff_yet_is_reported_distinctly(self) -> None:
        from services.api.lineups import get_lineups

        row = {**ROW, "kickoff_time": None}
        result = await get_lineups(1, row, [row], MemoryCache(), Settings(api_football_key="test-key"))
        assert result.available is False
        assert "kickoff date" in (result.reason or "")

    async def test_an_exhausted_quota_with_nothing_cached_says_so(self) -> None:
        from datetime import UTC, datetime

        from services.api.lineups import get_lineups
        from shared.keys import quota

        cache = MemoryCache()
        window = datetime.now(UTC).strftime("%Y-%m-%d")
        await cache.set(quota("api-football", window), 1, source="quota")
        settings = Settings(api_football_key="test-key", api_football_daily_budget=1)

        result = await get_lineups(1, ROW, [ROW], cache, settings)
        assert result.available is False
        assert "budget" in (result.reason or "")

    async def test_the_full_happy_path_resolves_then_fetches_then_caches(self, monkeypatch: Any) -> None:
        from services.api import lineups as lineups_mod

        async def fake_resolve(up: Any, date: str, season: int) -> dict[str, int]:
            assert date == "2026-08-21"
            return {"ARS-COV": 999001}

        async def fake_fetch(up: Any, af_fixture_id: int) -> dict[str, Any]:
            assert af_fixture_id == 999001
            return LINEUPS_PAYLOAD

        monkeypatch.setattr(lineups_mod.api_football, "resolve_fixture_ids", fake_resolve)
        monkeypatch.setattr(lineups_mod.api_football, "fetch_lineups", fake_fetch)

        cache = MemoryCache()
        settings = Settings(api_football_key="test-key")
        result = await lineups_mod.get_lineups(1, ROW, [ROW], cache, settings)

        assert result.available is True
        assert result.confirmed is True, "a real team sheet is confirmed, not predicted"
        assert result.home is not None
        assert result.home.formation == "4-3-3"
        assert [p.name for p in result.home.starting] == ["David Raya", "William Saliba"]
        assert result.away is not None
        assert result.away.formation == "4-4-2"

        # Cached for next time, at both keys the day's resolution should fill.
        from shared.keys import api_football_fixture_id
        from shared.keys import lineups as lineups_key

        assert await cache.get(lineups_key(1)) is not None
        resolved = await cache.get(api_football_fixture_id(1))
        assert resolved is not None
        assert int(resolved.value) == 999001

    async def test_a_second_call_reuses_the_cached_fixture_id_resolution(self, monkeypatch: Any) -> None:
        """The whole point: resolving costs one call a matchday, not one a match."""
        from services.api import lineups as lineups_mod

        resolve_calls = []

        async def fake_resolve(up: Any, date: str, season: int) -> dict[str, int]:
            resolve_calls.append(date)
            return {"ARS-COV": 999001}

        async def fake_fetch(up: Any, af_fixture_id: int) -> dict[str, Any]:
            return {"response": []}  # not out yet, but that's fine -- id resolution is what's under test

        monkeypatch.setattr(lineups_mod.api_football, "resolve_fixture_ids", fake_resolve)
        monkeypatch.setattr(lineups_mod.api_football, "fetch_lineups", fake_fetch)

        cache = MemoryCache()
        settings = Settings(api_football_key="test-key")
        await lineups_mod.get_lineups(1, ROW, [ROW], cache, settings)

        # Force past the lineups cache TTL check without waiting for real time.
        from shared.keys import lineups as lineups_key

        backdate(
            cache,
            lineups_key(1),
            {"available": False, "reason": "stale", "home": None, "away": None},
            seconds_ago=10_000,
        )

        await lineups_mod.get_lineups(1, ROW, [ROW], cache, settings)
        assert resolve_calls == ["2026-08-21"], "second call must not resolve again"

    async def test_a_resolve_failure_falls_back_to_the_last_cached_answer(self, monkeypatch: Any) -> None:
        from services.api import lineups as lineups_mod
        from services.poller.http import UpstreamError
        from shared.keys import lineups as lineups_key
        from shared.models import LineupsOut

        async def failing_resolve(up: Any, date: str, season: int) -> dict[str, int]:
            raise UpstreamError("api-football", "boom")

        monkeypatch.setattr(lineups_mod.api_football, "resolve_fixture_ids", failing_resolve)

        cache = MemoryCache()
        stale = LineupsOut(available=True, home=None, away=None, reason="from before")
        # Backdate it past the TTL so get_lineups actually attempts a refetch.
        backdate(cache, lineups_key(1), stale.model_dump(mode="json"), seconds_ago=10_000)

        result = await lineups_mod.get_lineups(1, ROW, [ROW], cache, Settings(api_football_key="test-key"))
        assert result.reason == "from before", (
            "a failed refetch must serve the last good answer, not go blank"
        )


class TestEndpoint:
    async def test_it_needs_a_session(self, client: AsyncClient) -> None:
        assert (await client.get("/api/fixtures/1/lineups")).status_code == 401

    async def test_an_unknown_fixture_is_404(self, client: AsyncClient) -> None:
        await sign_in(client)
        assert (await client.get("/api/fixtures/999999/lineups")).status_code == 404

    async def test_with_no_key_the_endpoint_still_answers(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fixtures/1/lineups")).json()
        assert body["confirmed"] is False
        assert "API_FOOTBALL_KEY" not in (body["reason"] or "")


class TestPredictedXI:
    """The keyless path. Built from a bootstrap with a full enough squad."""

    @staticmethod
    def squad(team: int, n: int = 20) -> list[dict[str, Any]]:
        # 3 keepers, 7 defenders, 7 midfielders, 3 forwards, descending starts.
        plan = [(1, 3), (2, 7), (3, 7), (4, 3)]
        out: list[dict[str, Any]] = []
        pid = team * 1000
        for element_type, count in plan:
            for i in range(count):
                pid += 1
                out.append(
                    {
                        "id": pid,
                        "team": team,
                        "element_type": element_type,
                        "web_name": f"T{team}-{element_type}-{i}",
                        "starts": count - i,
                        "minutes": (count - i) * 90,
                        "selected_by_percent": "1.0",
                        "status": "a",
                        "chance_of_playing_next_round": None,
                    }
                )
        return out[:n] if n < len(out) else out

    def test_it_picks_a_full_eleven_in_the_expected_shape(self) -> None:
        from services.api.lineups import predict_side

        boot = {"elements": self.squad(1) + self.squad(7)}
        side = predict_side(boot, 1)
        assert side is not None
        assert len(side.starting) == 11
        counts = {
            p.position: sum(1 for q in side.starting if q.position == p.position) for p in side.starting
        }
        assert counts == {"G": 1, "D": 4, "M": 4, "F": 2}

    def test_the_most_frequent_starters_are_picked_first(self) -> None:
        from services.api.lineups import predict_side

        side = predict_side({"elements": self.squad(1)}, 1)
        assert side is not None
        assert side.starting[0].name == "T1-1-0", "the keeper with the most starts"

    def test_an_injured_player_is_excluded(self) -> None:
        from services.api.lineups import predict_side

        squad = self.squad(1)
        top_keeper = next(p for p in squad if p["web_name"] == "T1-1-0")
        top_keeper["status"] = "i"
        side = predict_side({"elements": squad}, 1)
        assert side is not None
        assert side.starting[0].name != "T1-1-0", "the injured keeper must not start"

    def test_a_major_doubt_is_excluded(self) -> None:
        from services.api.lineups import predict_side

        squad = self.squad(1)
        next(p for p in squad if p["web_name"] == "T1-1-0")["chance_of_playing_next_round"] = 25
        side = predict_side({"elements": squad}, 1)
        assert side is not None
        assert side.starting[0].name != "T1-1-0"

    def test_too_thin_a_squad_refuses_rather_than_inventing(self) -> None:
        from services.api.lineups import predict_side

        assert predict_side({"elements": self.squad(1, n=5)}, 1) is None

    def test_the_other_club_is_not_borrowed_from(self) -> None:
        from services.api.lineups import predict_side

        side = predict_side({"elements": self.squad(1) + self.squad(7)}, 1)
        assert side is not None
        assert all(p.name.startswith("T1-") for p in side.starting)

    async def test_the_endpoint_returns_a_labelled_prediction(self) -> None:
        from services.api.lineups import predicted_lineups
        from shared.cache import MemoryCache
        from shared.keys import FPL_BOOTSTRAP

        cache = MemoryCache()
        await cache.set(FPL_BOOTSTRAP, {"elements": self.squad(1) + self.squad(7)}, source="fpl")
        result = await predicted_lineups(ROW, cache)

        assert result.available is True
        assert result.confirmed is False
        assert "Not the confirmed team sheet" in result.basis
        assert result.home is not None
        assert len(result.home.starting) == 11

    async def test_no_bootstrap_yet_says_so(self) -> None:
        from services.api.lineups import predicted_lineups
        from shared.cache import MemoryCache

        result = await predicted_lineups(ROW, MemoryCache())
        assert result.available is False
        assert "not loaded yet" in (result.reason or "")
