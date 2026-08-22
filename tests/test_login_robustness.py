"""Login must work for four people on shared connections and repeat attempts.

BRIEF section 3 asks for 10 attempts per IP per hour. Counting *successful*
logins against that ceiling locks out the very people it protects: four friends
behind one home connection share an address, and signing in on a phone and a
laptop is two attempts before anyone has typed anything wrong.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import CODES


class TestSuccessesAreFree:
    async def test_signing_in_many_times_never_locks_you_out(self, client: AsyncClient) -> None:
        # Four people, several devices each, one shared IP.
        for _ in range(20):
            response = await client.post("/api/session", json={"code": CODES["coyg"]})
            assert response.status_code == 200

    async def test_all_four_can_sign_in_from_one_address(self, client: AsyncClient) -> None:
        for person, code in CODES.items():
            response = await client.post("/api/session", json={"code": code})
            assert response.status_code == 200, person
            assert response.json()["person"]["key"] == person

    async def test_a_success_clears_earlier_failures(self, client: AsyncClient) -> None:
        """A typo followed by the right word must not count against you."""
        for _ in range(10):
            await client.post("/api/session", json={"code": "wrong"})
        assert (await client.post("/api/session", json={"code": CODES["coyg"]})).status_code == 200
        # And the slate is clean afterwards.
        for _ in range(10):
            assert (await client.post("/api/session", json={"code": "wrong"})).status_code == 401


class TestFailuresStillCount:
    async def test_repeated_wrong_guesses_are_eventually_refused(self, client: AsyncClient) -> None:
        statuses = [
            (await client.post("/api/session", json={"code": f"guess-{n}"})).status_code for n in range(25)
        ]
        assert 429 in statuses

    async def test_the_refusal_explains_itself(self, client: AsyncClient) -> None:
        for n in range(25):
            response = await client.post("/api/session", json={"code": f"guess-{n}"})
            if response.status_code == 429:
                detail = response.json()["detail"]
                assert "incorrect code words" in detail
                assert "hour" in detail
                return
        raise AssertionError("never rate limited")


class TestErrorsAreUseful:
    async def test_a_wrong_code_hints_at_the_common_cause(self, client: AsyncClient) -> None:
        response = await client.post("/api/session", json={"code": "nope"})
        assert "stray space" in response.json()["detail"]

    async def test_a_code_with_a_trailing_space_still_works(self, client: AsyncClient) -> None:
        # Phone keyboards add one after autocomplete; refusing it is hostile.
        response = await client.post("/api/session", json={"code": f"{CODES['coyg']} "})
        assert response.status_code == 200

    async def test_a_code_with_a_leading_space_still_works(self, client: AsyncClient) -> None:
        response = await client.post("/api/session", json={"code": f" {CODES['aure']}"})
        assert response.status_code == 200
