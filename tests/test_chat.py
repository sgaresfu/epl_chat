"""Chat tests: quotes, the weekly poll, the bets ledger and the timeline.

None of it touches an upstream, so it works with nothing configured. What it
does need is that nobody can forge anything — a scoreboard with no money on it
is worth exactly as much as its integrity.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from shared.db import Poll

from tests.conftest import CODES, sign_in


async def csrf(http: AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": http.cookies.get("pl_csrf") or ""}


class TestQuotes:
    async def test_there_are_none_to_begin_with(self, client: AsyncClient) -> None:
        await sign_in(client)
        assert (await client.get("/api/chat/quotes")).json() == []

    async def test_a_quote_can_be_added_and_read_back(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        response = await client.post(
            "/api/chat/quotes",
            json={"body": "Arsenal are winning this."},
            headers=await csrf(client),
        )
        assert response.status_code == 200
        assert response.json()["body"] == "Arsenal are winning this."

        quotes = (await client.get("/api/chat/quotes")).json()
        assert len(quotes) == 1
        assert quotes[0]["person"] == "coyg"

    async def test_a_quote_can_be_pinned_to_a_club(self, client: AsyncClient) -> None:
        await sign_in(client, "aure")
        response = await client.post(
            "/api/chat/quotes",
            json={"body": "Spurs will collapse.", "subject_type": "club", "subject_id": "TOT"},
            headers=await csrf(client),
        )
        assert response.json()["subject_type"] == "club"
        assert response.json()["subject_id"] == "TOT"

    async def test_the_author_comes_from_the_session(self, client: AsyncClient) -> None:
        await sign_in(client, "bulba")
        response = await client.post(
            "/api/chat/quotes",
            json={"body": "mine", "person": "coyg"},
            headers=await csrf(client),
        )
        assert response.json()["person"] == "bulba"

    async def test_an_empty_quote_is_refused(self, client: AsyncClient) -> None:
        await sign_in(client)
        response = await client.post("/api/chat/quotes", json={"body": ""}, headers=await csrf(client))
        assert response.status_code == 422

    async def test_adding_a_quote_needs_a_csrf_token(self, client: AsyncClient) -> None:
        await sign_in(client)
        assert (await client.post("/api/chat/quotes", json={"body": "x"})).status_code == 403

    async def test_newest_first(self, client: AsyncClient) -> None:
        await sign_in(client)
        for body in ("first", "second", "third"):
            await client.post("/api/chat/quotes", json={"body": body}, headers=await csrf(client))
        bodies = [q["body"] for q in (await client.get("/api/chat/quotes")).json()]
        assert bodies[0] == "third"


class TestPoll:
    async def _make_poll(self, sessions: Any, closes_in: timedelta = timedelta(days=7)) -> int:
        now = datetime.now(UTC)
        async with sessions() as db:
            poll = Poll(
                question="Who finishes top four?",
                options=["Arsenal", "City", "Liverpool", "Chelsea"],
                opens_at=now - timedelta(minutes=1),
                closes_at=now + closes_in,
            )
            db.add(poll)
            await db.commit()
            return int(poll.id)

    async def test_it_says_so_when_there_is_no_poll(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/chat/poll")).json()
        assert body["current"] is None
        assert "each week" in body["empty_message"]

    async def test_an_open_poll_is_returned_as_current(self, client: AsyncClient, sessions: Any) -> None:
        await self._make_poll(sessions)
        await sign_in(client)
        body = (await client.get("/api/chat/poll")).json()
        assert body["current"]["question"] == "Who finishes top four?"
        assert body["current"]["open"] is True
        assert len(body["current"]["options"]) == 4

    async def test_a_vote_is_counted(self, client: AsyncClient, sessions: Any) -> None:
        poll_id = await self._make_poll(sessions)
        await sign_in(client, "coyg")
        response = await client.post(
            "/api/chat/poll",
            json={"poll_id": poll_id, "choice": "Arsenal"},
            headers=await csrf(client),
        )
        assert response.status_code == 200
        assert response.json()["total_votes"] == 1
        assert response.json()["my_vote"] == "Arsenal"

    async def test_four_people_vote_independently(self, client: AsyncClient, sessions: Any) -> None:
        poll_id = await self._make_poll(sessions)
        for person, choice in [("coyg", "Arsenal"), ("aure", "City"), ("twzt", "Arsenal")]:
            await client.post("/api/session", json={"code": CODES[person]})
            await client.post(
                "/api/chat/poll",
                json={"poll_id": poll_id, "choice": choice},
                headers=await csrf(client),
            )
        body = (await client.get("/api/chat/poll")).json()
        counts = {o["choice"]: o["votes"] for o in body["current"]["options"]}
        assert counts["Arsenal"] == 2
        assert counts["City"] == 1
        assert body["current"]["total_votes"] == 3

    async def test_voting_twice_replaces_rather_than_double_counts(
        self, client: AsyncClient, sessions: Any
    ) -> None:
        poll_id = await self._make_poll(sessions)
        await sign_in(client, "coyg")
        for choice in ("Arsenal", "Liverpool"):
            await client.post(
                "/api/chat/poll",
                json={"poll_id": poll_id, "choice": choice},
                headers=await csrf(client),
            )
        body = (await client.get("/api/chat/poll")).json()
        assert body["current"]["total_votes"] == 1
        assert body["current"]["my_vote"] == "Liverpool"

    async def test_a_choice_outside_the_options_is_refused(self, client: AsyncClient, sessions: Any) -> None:
        poll_id = await self._make_poll(sessions)
        await sign_in(client)
        response = await client.post(
            "/api/chat/poll",
            json={"poll_id": poll_id, "choice": "Wolves"},
            headers=await csrf(client),
        )
        assert response.status_code == 422

    async def test_a_closed_poll_refuses_votes(self, client: AsyncClient, sessions: Any) -> None:
        poll_id = await self._make_poll(sessions, closes_in=timedelta(seconds=-1))
        await sign_in(client)
        response = await client.post(
            "/api/chat/poll",
            json={"poll_id": poll_id, "choice": "Arsenal"},
            headers=await csrf(client),
        )
        assert response.status_code == 409

    async def test_a_closed_poll_is_archived_not_deleted(self, client: AsyncClient, sessions: Any) -> None:
        await self._make_poll(sessions, closes_in=timedelta(seconds=-1))
        await sign_in(client)
        body = (await client.get("/api/chat/poll")).json()
        assert body["current"] is None
        assert len(body["archive"]) == 1


class TestBets:
    async def test_the_ledger_starts_empty_and_explains_itself(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/chat/bets")).json()
        assert body["bets"] == []
        assert "No money" in body["empty_message"]

    async def test_a_bet_can_be_proposed(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        response = await client.post(
            "/api/chat/bets",
            json={"opponent": "aure", "terms": "Arsenal finish above City."},
            headers=await csrf(client),
        )
        assert response.status_code == 200
        assert response.json()["proposer"] == "coyg"
        assert response.json()["opponent"] == "aure"
        assert response.json()["settled"] is False

    async def test_you_cannot_bet_against_yourself(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        response = await client.post(
            "/api/chat/bets",
            json={"opponent": "coyg", "terms": "x"},
            headers=await csrf(client),
        )
        assert response.status_code == 422

    async def test_an_unknown_opponent_is_refused(self, client: AsyncClient) -> None:
        await sign_in(client)
        response = await client.post(
            "/api/chat/bets",
            json={"opponent": "nobody", "terms": "x"},
            headers=await csrf(client),
        )
        assert response.status_code == 404

    async def _propose(self, client: AsyncClient) -> int:
        await sign_in(client, "coyg")
        response = await client.post(
            "/api/chat/bets",
            json={"opponent": "aure", "terms": "Arsenal above City."},
            headers=await csrf(client),
        )
        return int(response.json()["id"])

    async def test_settling_records_the_winner_on_the_scoreboard(self, client: AsyncClient) -> None:
        bet_id = await self._propose(client)
        response = await client.put(
            "/api/chat/bets",
            json={"bet_id": bet_id, "winner": "coyg"},
            headers=await csrf(client),
        )
        assert response.status_code == 200
        assert response.json()["settled"] is True

        board = (await client.get("/api/chat/bets")).json()["scoreboard"]
        assert board["coyg"] == 1
        assert board["aure"] == 0

    async def test_an_outsider_cannot_settle_somebody_elses_bet(self, client: AsyncClient) -> None:
        # Otherwise the ledger is worthless.
        bet_id = await self._propose(client)
        await client.post("/api/session", json={"code": CODES["bulba"]})
        response = await client.put(
            "/api/chat/bets",
            json={"bet_id": bet_id, "winner": "bulba"},
            headers=await csrf(client),
        )
        assert response.status_code == 403

    async def test_the_winner_must_be_one_of_the_two(self, client: AsyncClient) -> None:
        bet_id = await self._propose(client)
        response = await client.put(
            "/api/chat/bets",
            json={"bet_id": bet_id, "winner": "twzt"},
            headers=await csrf(client),
        )
        assert response.status_code == 422

    async def test_a_settled_bet_cannot_be_settled_again(self, client: AsyncClient) -> None:
        bet_id = await self._propose(client)
        await client.put(
            "/api/chat/bets",
            json={"bet_id": bet_id, "winner": "coyg"},
            headers=await csrf(client),
        )
        second = await client.put(
            "/api/chat/bets",
            json={"bet_id": bet_id, "winner": "aure"},
            headers=await csrf(client),
        )
        assert second.status_code == 409


class TestTimeline:
    async def test_it_already_contains_the_filed_predictions(self, client: AsyncClient) -> None:
        await sign_in(client)
        entries = (await client.get("/api/timeline")).json()["entries"]
        kinds = {e["kind"] for e in entries}
        assert "prediction" in kinds
        assert len([e for e in entries if e["kind"] == "prediction"]) == 4

    async def test_a_quote_appears_in_the_feed(self, client: AsyncClient) -> None:
        await sign_in(client, "twzt")
        await client.post(
            "/api/chat/quotes", json={"body": "Leeds are going down."}, headers=await csrf(client)
        )
        entries = (await client.get("/api/timeline")).json()["entries"]
        quote = next(e for e in entries if e["kind"] == "quote")
        assert quote["person"] == "twzt"
        assert "Leeds" in quote["detail"]

    async def test_a_settled_bet_appears_twice_proposed_and_settled(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        bet = await client.post(
            "/api/chat/bets",
            json={"opponent": "aure", "terms": "Arsenal above City."},
            headers=await csrf(client),
        )
        await client.put(
            "/api/chat/bets",
            json={"bet_id": bet.json()["id"], "winner": "coyg"},
            headers=await csrf(client),
        )
        kinds = [e["kind"] for e in (await client.get("/api/timeline")).json()["entries"]]
        assert "bet" in kinds
        assert "bet-settled" in kinds

    async def test_entries_are_newest_first(self, client: AsyncClient) -> None:
        await sign_in(client)
        await client.post("/api/chat/quotes", json={"body": "latest"}, headers=await csrf(client))
        entries = (await client.get("/api/timeline")).json()["entries"]
        times = [e["at"] for e in entries]
        assert times == sorted(times, reverse=True)

    async def test_it_needs_a_session(self, client: AsyncClient) -> None:
        assert (await client.get("/api/timeline")).status_code == 401
