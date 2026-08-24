"""The picks endpoints, and the two rules the server has to enforce itself.

A deadline the client merely renders is an honour system, and a pick you can
read off somebody else before kick-off is not a prediction. Both are checked
here against the API rather than the UI.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from shared.cache import MemoryCache
from shared.config import Settings

from tests.conftest import CODES, _build_app, sign_in

OPENER = 1


def csrf(http: AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": http.cookies.get("pl_csrf") or ""}


@pytest.fixture
async def picks_client(settings: Settings, fixtures_payload: list[dict[str, Any]], sessions: Any) -> Any:
    """Gameweek 1 with one finished match and the rest still to come.

    Times are relative to now so the suite does not expire the way the watch
    tests did when the captured kickoffs drifted into the past.
    """
    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for row in fixtures_payload:
        copy = dict(row)
        if copy.get("event") != 1:
            rows.append(copy)
            continue
        if int(copy["id"]) == OPENER:
            copy["kickoff_time"] = (now - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
            copy["started"], copy["finished"] = True, True
            copy["finished_provisional"] = True
            copy["team_h_score"], copy["team_a_score"] = 2, 1
            copy["minutes"] = 90
        else:
            copy["kickoff_time"] = (now + timedelta(days=2)).isoformat().replace("+00:00", "Z")
            copy["started"], copy["finished"] = False, False
            copy["team_h_score"] = copy["team_a_score"] = None
        rows.append(copy)

    cache = MemoryCache()
    from shared import keys

    await cache.set(keys.FPL_FIXTURES, rows, source="fpl")
    transport = ASGITransport(app=_build_app(settings, cache, sessions))
    async with AsyncClient(transport=transport, base_url="http://api.test") as http:
        yield http


class TestReadingTheRound:
    async def test_it_needs_a_session(self, picks_client: AsyncClient) -> None:
        assert (await picks_client.get("/api/picks")).status_code == 401

    async def test_it_lists_the_round(self, picks_client: AsyncClient) -> None:
        await sign_in(picks_client)
        body = (await picks_client.get("/api/picks?gameweek=1")).json()
        assert body["gameweek"] == 1
        assert len(body["fixtures"]) == 10

    async def test_an_unplayed_match_is_open_and_a_played_one_is_not(self, picks_client: AsyncClient) -> None:
        await sign_in(picks_client)
        body = (await picks_client.get("/api/picks?gameweek=1")).json()
        opener = next(f for f in body["fixtures"] if f["fixture_id"] == OPENER)
        others = [f for f in body["fixtures"] if f["fixture_id"] != OPENER]
        assert opener["open_for_picks"] is False
        assert opener["finished"] is True
        assert all(f["open_for_picks"] for f in others)


class TestSavingAPick:
    async def test_a_pick_is_saved_and_read_back(self, picks_client: AsyncClient) -> None:
        await sign_in(picks_client)
        target = 3
        r = await picks_client.put(
            "/api/picks",
            json={"fixture_id": target, "home_goals": 2, "away_goals": 1},
            headers=csrf(picks_client),
        )
        assert r.status_code == 200, r.text

        body = (await picks_client.get("/api/picks?gameweek=1")).json()
        fixture = next(f for f in body["fixtures"] if f["fixture_id"] == target)
        assert fixture["my_pick"]["home_goals"] == 2
        assert fixture["my_pick"]["away_goals"] == 1

    async def test_saving_twice_updates_rather_than_duplicates(self, picks_client: AsyncClient) -> None:
        await sign_in(picks_client)
        for goals in (1, 4):
            await picks_client.put(
                "/api/picks",
                json={"fixture_id": 3, "home_goals": goals, "away_goals": 0},
                headers=csrf(picks_client),
            )
        body = (await picks_client.get("/api/picks?gameweek=1")).json()
        fixture = next(f for f in body["fixtures"] if f["fixture_id"] == 3)
        assert fixture["my_pick"]["home_goals"] == 4

    async def test_a_pick_after_kick_off_is_refused(self, picks_client: AsyncClient) -> None:
        """The rule the whole feature rests on."""
        await sign_in(picks_client)
        r = await picks_client.put(
            "/api/picks",
            json={"fixture_id": OPENER, "home_goals": 2, "away_goals": 1},
            headers=csrf(picks_client),
        )
        assert r.status_code == 403
        assert "kick" in r.json()["detail"].lower()

    async def test_an_unknown_fixture_is_404(self, picks_client: AsyncClient) -> None:
        await sign_in(picks_client)
        r = await picks_client.put(
            "/api/picks",
            json={"fixture_id": 999999, "home_goals": 1, "away_goals": 0},
            headers=csrf(picks_client),
        )
        assert r.status_code == 404

    async def test_a_negative_or_absurd_score_is_rejected(self, picks_client: AsyncClient) -> None:
        await sign_in(picks_client)
        for payload in (
            {"fixture_id": 3, "home_goals": -1, "away_goals": 0},
            {"fixture_id": 3, "home_goals": 99, "away_goals": 0},
        ):
            r = await picks_client.put("/api/picks", json=payload, headers=csrf(picks_client))
            assert r.status_code == 422, payload

    async def test_it_needs_a_session(self, picks_client: AsyncClient) -> None:
        r = await picks_client.put("/api/picks", json={"fixture_id": 3, "home_goals": 1, "away_goals": 0})
        assert r.status_code == 401


class TestSecrecyBeforeKickOff:
    async def test_another_persons_pick_is_hidden_until_the_whistle(self, picks_client: AsyncClient) -> None:
        """A pick you can copy is not a prediction."""
        await picks_client.post("/api/session", json={"code": CODES["aure"]})
        await picks_client.put(
            "/api/picks",
            json={"fixture_id": 3, "home_goals": 3, "away_goals": 3},
            headers=csrf(picks_client),
        )

        await picks_client.post("/api/session", json={"code": CODES["coyg"]})
        body = (await picks_client.get("/api/picks?gameweek=1")).json()
        fixture = next(f for f in body["fixtures"] if f["fixture_id"] == 3)
        assert fixture["revealed"] is False
        assert fixture["picks"] == [], "nobody else's pick may be visible before kick-off"
        assert fixture["my_pick"] is None

    async def test_my_own_pick_is_always_visible_to_me(self, picks_client: AsyncClient) -> None:
        await sign_in(picks_client, "coyg")
        await picks_client.put(
            "/api/picks",
            json={"fixture_id": 3, "home_goals": 1, "away_goals": 1},
            headers=csrf(picks_client),
        )
        body = (await picks_client.get("/api/picks?gameweek=1")).json()
        fixture = next(f for f in body["fixtures"] if f["fixture_id"] == 3)
        assert fixture["my_pick"]["home_goals"] == 1
        assert fixture["picks"] == [], "still hidden from the shared list"

    async def test_everyone_is_revealed_once_the_match_has_started(
        self, picks_client: AsyncClient, sessions: Any
    ) -> None:
        from services.api.repository import save_pick

        async with sessions() as db:
            await save_pick(db, "aure", OPENER, 2, 1)
            await save_pick(db, "twzt", OPENER, 0, 3)
            await db.commit()

        await sign_in(picks_client, "coyg")
        body = (await picks_client.get("/api/picks?gameweek=1")).json()
        opener = next(f for f in body["fixtures"] if f["fixture_id"] == OPENER)
        assert opener["revealed"] is True
        assert {p["person"] for p in opener["picks"]} == {"aure", "twzt"}

    async def test_a_settled_pick_carries_its_score(self, picks_client: AsyncClient, sessions: Any) -> None:
        from services.api.repository import save_pick

        async with sessions() as db:
            await save_pick(db, "aure", OPENER, 2, 1)  # exact on a 2-1
            await save_pick(db, "twzt", OPENER, 1, 0)  # right result only
            await db.commit()

        await sign_in(picks_client, "coyg")
        body = (await picks_client.get("/api/picks?gameweek=1")).json()
        opener = next(f for f in body["fixtures"] if f["fixture_id"] == OPENER)
        scored = {p["person"]: p for p in opener["picks"]}
        assert scored["aure"]["points"] == 6
        assert scored["aure"]["exact"] is True
        assert scored["twzt"]["points"] == 2
        assert scored["twzt"]["exact"] is False


class TestAllTimeStats:
    async def test_it_needs_a_session(self, picks_client: AsyncClient) -> None:
        assert (await picks_client.get("/api/picks/stats")).status_code == 401

    async def test_an_empty_record_explains_itself(self, picks_client: AsyncClient) -> None:
        await sign_in(picks_client)
        body = (await picks_client.get("/api/picks/stats")).json()
        assert body["total_settled"] == 0
        assert body["empty_message"]
        assert len(body["rows"]) == 4, "all four are listed even before anybody picks"

    async def test_settled_picks_are_counted_and_ranked(
        self, picks_client: AsyncClient, sessions: Any
    ) -> None:
        from services.api.repository import save_pick

        async with sessions() as db:
            await save_pick(db, "aure", OPENER, 2, 1)  # exact -> 6
            await save_pick(db, "twzt", OPENER, 1, 0)  # outcome -> 2
            await save_pick(db, "coyg", OPENER, 0, 2)  # nothing -> 0
            await db.commit()

        await sign_in(picks_client)
        body = (await picks_client.get("/api/picks/stats")).json()
        assert body["total_settled"] == 3
        rows = {r["person"]["key"]: r for r in body["rows"]}
        assert rows["aure"]["points"] == 6
        assert rows["aure"]["exact"] == 1
        assert rows["twzt"]["points"] == 2
        assert rows["coyg"]["points"] == 0
        assert body["rows"][0]["person"]["key"] == "aure", "ranked best first"

    async def test_an_unsettled_pick_does_not_count(self, picks_client: AsyncClient, sessions: Any) -> None:
        from services.api.repository import save_pick

        async with sessions() as db:
            await save_pick(db, "aure", 3, 9, 0)  # fixture 3 has not been played
            await db.commit()

        await sign_in(picks_client)
        body = (await picks_client.get("/api/picks/stats")).json()
        assert body["total_settled"] == 0

    async def test_the_scoring_rule_is_published(self, picks_client: AsyncClient) -> None:
        await sign_in(picks_client)
        assert "exact score" in (await picks_client.get("/api/picks/stats")).json()["scoring"]
