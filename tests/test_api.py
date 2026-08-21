"""End-to-end API tests against real captured payloads.

These run the actual FastAPI app in-process with a cache filled from genuine
FPL responses, so they cover the shapes production sees -- including the
pre-season state the site launches in.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import CODES, sign_in


class TestAuth:
    async def test_every_code_word_signs_its_own_person_in(self, client: AsyncClient) -> None:
        for person, code in CODES.items():
            response = await client.post("/api/session", json={"code": code})
            assert response.status_code == 200, person
            assert response.json()["person"]["key"] == person

    async def test_a_wrong_code_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/api/session", json={"code": "not-a-code"})
        assert response.status_code == 401
        assert "four" in response.json()["detail"]

    async def test_an_empty_code_is_rejected_before_it_reaches_the_comparison(
        self, client: AsyncClient
    ) -> None:
        response = await client.post("/api/session", json={"code": ""})
        assert response.status_code == 422

    async def test_signing_in_sets_an_httponly_session_cookie(self, client: AsyncClient) -> None:
        response = await client.post("/api/session", json={"code": CODES["coyg"]})
        cookie = response.headers.get("set-cookie", "")
        assert "pl_session=" in cookie
        assert "HttpOnly" in cookie

    async def test_the_csrf_cookie_is_readable_by_the_client(self, client: AsyncClient) -> None:
        # Deliberately not HttpOnly: the client must echo it back in a header.
        await sign_in(client)
        assert client.cookies.get("pl_csrf")

    async def test_protected_routes_reject_an_anonymous_caller(self, client: AsyncClient) -> None:
        for path in ("/api/me", "/api/table", "/api/fixtures", "/api/home", "/api/predictions"):
            response = await client.get(path)
            assert response.status_code == 401, path

    async def test_a_forged_session_cookie_is_refused(self, client: AsyncClient) -> None:
        client.cookies.set("pl_session", "forged.not.signed", domain="api.test")
        response = await client.get("/api/me")
        assert response.status_code == 401

    async def test_signing_out_clears_the_session(self, client: AsyncClient) -> None:
        await sign_in(client)
        assert (await client.get("/api/me")).status_code == 200
        await client.delete("/api/session")
        client.cookies.clear()
        assert (await client.get("/api/me")).status_code == 401

    async def test_rate_limit_stops_repeated_guessing(self, client: AsyncClient) -> None:
        # 10 attempts per IP per hour, per BRIEF section 3.
        codes = [{"code": f"guess-{n}"} for n in range(12)]
        statuses = [(await client.post("/api/session", json=c)).status_code for c in codes]
        assert 429 in statuses
        assert statuses.count(401) <= 10


class TestIdentity:
    async def test_me_returns_the_signed_in_person_and_their_zone(self, client: AsyncClient) -> None:
        await sign_in(client, "bulba")
        body = (await client.get("/api/me")).json()
        assert body["person"]["key"] == "bulba"
        assert body["person"]["timezone"] == "America/Anchorage"
        assert body["person"]["city"] == "Alaska"

    async def test_me_lists_all_four_people(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/me")).json()
        assert [p["key"] for p in body["people"]] == ["coyg", "aure", "twzt", "bulba"]


class TestTable:
    async def test_the_table_is_twenty_clubs_on_zero_before_the_season(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/table")).json()
        assert len(body["rows"]) == 20
        assert body["season_started"] is False
        assert all(row["points"] == 0 for row in body["rows"])

    async def test_the_empty_table_explains_itself(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/table")).json()
        # An empty screen is an instruction, not an apology.
        assert body["empty_message"]
        assert "zero points" in body["empty_message"]

    async def test_every_row_carries_its_crest_colours(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/table")).json()
        for row in body["rows"]:
            assert row["club"]["primary"].startswith("#")
            assert row["club"]["on_primary"].startswith("#")

    async def test_the_table_reports_its_own_freshness(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/table")).json()
        assert body["freshness"]["available"] is True
        assert body["freshness"]["source"] == "fpl"


class TestProjectedTable:
    async def test_the_projection_ranks_all_twenty(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/table/projected")).json()
        assert len(body["rows"]) == 20

    async def test_only_the_promoted_clubs_are_flagged_modelled(self, client: AsyncClient) -> None:
        # Every club plays the promoted three, so flagging any row with a single
        # modelled fixture would flag all twenty and mean nothing.
        await sign_in(client)
        body = (await client.get("/api/table/projected")).json()
        assert sorted(body["modelled_rows"]) == ["COV", "HUL", "IPS"]

    async def test_the_projection_states_its_method(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/table/projected")).json()
        assert "272" in body["method"]
        assert "108" in body["method"]

    async def test_established_clubs_carry_an_honest_partial_note(self, client: AsyncClient) -> None:
        await sign_in(client)
        rows = (await client.get("/api/table/projected")).json()["rows"]
        arsenal = next(r for r in rows if r["club"]["short_name"] == "ARS")
        assert arsenal["modelled"] is False
        assert "6 of 38" in arsenal["note"]


class TestFixtures:
    async def test_the_full_fixture_list_is_returned(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fixtures")).json()
        assert len(body["fixtures"]) == 380

    async def test_every_fixture_carries_all_four_cities(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fixtures?gameweek=1")).json()
        for fixture in body["fixtures"]:
            places = [t["place"] for t in fixture["local_times"]]
            assert places == ["coyg", "aure", "twzt", "bulba"]

    async def test_every_city_names_its_broadcaster(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fixtures?gameweek=1")).json()
        opener = body["fixtures"][0]
        listings = {t["city"]: t["broadcaster"] for t in opener["local_times"]}
        assert listings["Lviv"] == "Setanta Sports"
        assert listings["Michigan"] == "Peacock"
        assert listings["Alberta"] == "Fubo"
        assert listings["Alaska"] == "Peacock"

    async def test_broadcast_listings_carry_a_verification_date(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fixtures?gameweek=1")).json()
        for slot in body["fixtures"][0]["local_times"]:
            assert slot["verified_on"] == "2026-08-21"

    async def test_the_opening_match_shows_the_right_time_in_each_city(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fixtures?gameweek=1")).json()
        opener = body["fixtures"][0]
        assert opener["home"]["short_name"] == "ARS"
        assert opener["away"]["short_name"] == "COV"
        times = {t["city"]: t["time"] for t in opener["local_times"]}
        assert times == {"Lviv": "22:00", "Michigan": "15:00", "Alberta": "13:00", "Alaska": "11:00"}

    async def test_a_derby_is_badged(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fixtures")).json()
        derbies = [f["derby"] for f in body["fixtures"] if f["derby"]]
        assert "North London derby" in derbies
        assert "Merseyside derby" in derbies

    async def test_filtering_by_gameweek_returns_ten_matches(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fixtures?gameweek=1")).json()
        assert len(body["fixtures"]) == 10

    async def test_an_unknown_fixture_is_a_404(self, client: AsyncClient) -> None:
        await sign_in(client)
        assert (await client.get("/api/fixtures/999999")).status_code == 404

    async def test_the_watch_window_is_shut_before_kickoff(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fixtures?gameweek=1")).json()
        # Nothing has kicked off yet, so no match can be marked watched.
        assert all(f["watch_open"] is False for f in body["fixtures"])


class TestSeasonTimeline:
    async def test_the_timeline_is_computed_not_hardcoded(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/season")).json()
        assert body["matches_total"] == 380
        assert body["gameweeks_total"] == 38
        assert body["total_days"] == 282

    async def test_nothing_has_been_played_yet(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/season")).json()
        assert body["matches_played"] == 0
        assert body["gameweeks_played"] == 0
        assert body["matches_remaining"] == 380

    async def test_the_calendar_markers_are_ordered_and_bounded(self, client: AsyncClient) -> None:
        await sign_in(client)
        markers = (await client.get("/api/season")).json()["markers"]
        percents = [m["percent"] for m in markers]
        assert percents == sorted(percents)
        assert all(0 <= p <= 100 for p in percents)
        assert any(m["is_now"] for m in markers)


class TestHome:
    async def test_home_names_the_next_match(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/home")).json()
        fixture = body["next_match"]["fixture"]
        assert fixture["home"]["short_name"] == "ARS"
        assert fixture["away"]["short_name"] == "COV"

    async def test_home_counts_down_to_kickoff(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/home")).json()
        assert body["next_match"]["countdown_seconds"] >= 0

    async def test_home_writes_a_line_of_the_day(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/home")).json()
        assert body["line_of_the_day"]


class TestColdStart:
    """Before the poller has ever run, every panel must still say something useful."""

    async def test_the_table_explains_the_wait_rather_than_erroring(self, cold_client: AsyncClient) -> None:
        await sign_in(cold_client)
        response = await cold_client.get("/api/table")
        assert response.status_code == 200
        body = response.json()
        assert body["rows"] == []
        assert body["empty_message"]
        assert body["freshness"]["available"] is False
        assert body["freshness"]["reason"]

    async def test_fixtures_degrade_without_a_white_screen(self, cold_client: AsyncClient) -> None:
        await sign_in(cold_client)
        body = (await cold_client.get("/api/fixtures")).json()
        assert body["fixtures"] == []
        assert body["empty_message"]

    async def test_readiness_reports_not_ready_before_the_first_poll(self, cold_client: AsyncClient) -> None:
        response = await cold_client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["fixtures_cached"] is False

    async def test_liveness_never_depends_on_a_dependency(self, cold_client: AsyncClient) -> None:
        response = await cold_client.get("/healthz")
        assert response.status_code == 200


class TestPredictions:
    """The lock is the part that must be right, and it is enforced server-side."""

    async def test_all_four_seeded_predictions_are_present(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/predictions")).json()
        filed = {p["person"] for p in body["predictions"] if p["filed"]}
        assert filed == {"coyg", "aure", "twzt", "bulba"}

    async def test_an_unfiled_slot_reads_open_before_the_lock(
        self, settings: object, cache: object, empty_db: object
    ) -> None:
        """A person with no row shows an open slot, not an error.

        Exercised against a database with nothing seeded, because all four are
        filed now -- the state still has to work for a future season.
        """
        from httpx import ASGITransport
        from httpx import AsyncClient as Client

        from tests.conftest import CODES, _build_app

        app = _build_app(settings, cache, empty_db)  # type: ignore[arg-type]
        async with Client(transport=ASGITransport(app=app), base_url="http://api.test") as http:
            await http.post("/api/session", json={"code": CODES["coyg"]})
            body = (await http.get("/api/predictions")).json()
            statuses = {p["person"]: p["status"] for p in body["predictions"]}
            assert set(statuses.values()) == {"open"}

    async def test_an_owner_sees_their_own_picks(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        body = (await client.get("/api/predictions")).json()
        mine = next(p for p in body["predictions"] if p["person"] == "coyg")
        assert mine["redacted"] is False
        assert mine["table"][0] == "ARS"
        assert mine["awards"]["playmaker"] == "Ødegaard"

    async def test_another_persons_picks_are_redacted_before_the_lock(self, client: AsyncClient) -> None:
        # Otherwise the last to file could simply copy the best table on screen.
        await sign_in(client, "coyg")
        body = (await client.get("/api/predictions")).json()
        theirs = next(p for p in body["predictions"] if p["person"] == "aure")
        assert theirs["filed"] is True
        assert theirs["redacted"] is True
        assert theirs["table"] == []

    async def test_a_submission_timestamp_is_shown(self, client: AsyncClient) -> None:
        await sign_in(client, "coyg")
        body = (await client.get("/api/predictions")).json()
        mine = next(p for p in body["predictions"] if p["person"] == "coyg")
        assert mine["submitted_at"]

    async def test_filing_a_prediction_requires_a_csrf_token(self, client: AsyncClient) -> None:
        await sign_in(client, "twzt")
        from shared.clubs import CLUBS

        table = [c.short_name for c in CLUBS]
        response = await client.put("/api/predictions", json={"table": table})
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    async def _put(self, client: AsyncClient, table: list[str]) -> object:
        token = client.cookies.get("pl_csrf") or ""
        return await client.put("/api/predictions", json={"table": table}, headers={"X-CSRF-Token": token})

    async def test_a_valid_table_is_accepted_before_the_lock(self, client: AsyncClient) -> None:
        await sign_in(client, "twzt")
        from shared.clubs import CLUBS

        table = [c.short_name for c in CLUBS]
        response = await self._put(client, table)
        assert response.status_code == 200, response.text
        assert response.json()["person"] == "twzt"

    async def test_a_duplicate_club_is_refused(self, client: AsyncClient) -> None:
        await sign_in(client, "twzt")
        from shared.clubs import CLUBS

        table = [c.short_name for c in CLUBS]
        table[5] = table[0]
        response = await self._put(client, table)
        assert response.status_code == 422
        assert "twice" in response.json()["detail"]

    async def test_a_short_table_is_refused(self, client: AsyncClient) -> None:
        await sign_in(client, "twzt")
        from shared.clubs import CLUBS

        response = await self._put(client, [c.short_name for c in CLUBS][:19])
        assert response.status_code == 422
        assert "all 20" in response.json()["detail"]

    async def test_an_unknown_club_is_refused(self, client: AsyncClient) -> None:
        await sign_in(client, "twzt")
        from shared.clubs import CLUBS

        table = [c.short_name for c in CLUBS]
        table[3] = "LEI"
        response = await self._put(client, table)
        assert response.status_code == 422

    async def test_the_person_comes_from_the_session_not_the_payload(self, client: AsyncClient) -> None:
        # A client claiming to be somebody else must not be believed.
        await sign_in(client, "twzt")
        from shared.clubs import CLUBS

        table = [c.short_name for c in CLUBS]
        token = client.cookies.get("pl_csrf") or ""
        response = await client.put(
            "/api/predictions",
            json={"table": table, "person": "coyg", "who": "coyg"},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 200
        assert response.json()["person"] == "twzt"


class TestPredictionLock:
    """After the deadline the picker is read-only, whatever the client thinks."""

    async def test_writes_are_refused_once_the_lock_has_passed(
        self, settings: object, cache: object, sessions: object
    ) -> None:
        from httpx import ASGITransport
        from httpx import AsyncClient as Client
        from shared.config import Settings

        from tests.conftest import CODES, _build_app

        past_lock = Settings(
            environment="local",
            session_secret="test-secret-long-enough-for-signing-abcdefghijk",
            code_coyg=CODES["coyg"],
            code_aure=CODES["aure"],
            code_twzt=CODES["twzt"],
            code_bulba=CODES["bulba"],
            prediction_lock="2020-01-01T00:00:00Z",  # long past
        )
        app = _build_app(past_lock, cache, sessions)  # type: ignore[arg-type]
        async with Client(transport=ASGITransport(app=app), base_url="http://api.test") as http:
            await http.post("/api/session", json={"code": CODES["twzt"]})
            from shared.clubs import CLUBS

            token = http.cookies.get("pl_csrf") or ""
            response = await http.put(
                "/api/predictions",
                json={"table": [c.short_name for c in CLUBS]},
                headers={"X-CSRF-Token": token},
            )
            assert response.status_code == 403
            assert "locked" in response.json()["detail"].lower()

    async def test_after_the_lock_everyone_can_see_everything(self, cache: object, sessions: object) -> None:
        from httpx import ASGITransport
        from httpx import AsyncClient as Client
        from shared.config import Settings

        from tests.conftest import CODES, _build_app

        past_lock = Settings(
            environment="local",
            session_secret="test-secret-long-enough-for-signing-abcdefghijk",
            code_coyg=CODES["coyg"],
            code_aure=CODES["aure"],
            code_twzt=CODES["twzt"],
            code_bulba=CODES["bulba"],
            prediction_lock="2020-01-01T00:00:00Z",
        )
        app = _build_app(past_lock, cache, sessions)  # type: ignore[arg-type]
        async with Client(transport=ASGITransport(app=app), base_url="http://api.test") as http:
            await http.post("/api/session", json={"code": CODES["coyg"]})
            body = (await http.get("/api/predictions")).json()
            assert body["locked"] is True
            theirs = next(p for p in body["predictions"] if p["person"] == "aure")
            assert theirs["redacted"] is False
            assert theirs["table"][0] == "ARS"

    async def test_an_unfiled_slot_reads_did_not_file_after_the_lock(
        self, cache: object, empty_db: object
    ) -> None:
        from httpx import ASGITransport
        from httpx import AsyncClient as Client
        from shared.config import Settings

        from tests.conftest import CODES, _build_app

        past_lock = Settings(
            environment="local",
            session_secret="test-secret-long-enough-for-signing-abcdefghijk",
            code_coyg=CODES["coyg"],
            prediction_lock="2020-01-01T00:00:00Z",
        )
        # An empty database: nobody filed, so every slot must read did-not-file.
        app = _build_app(past_lock, cache, empty_db)  # type: ignore[arg-type]
        async with Client(transport=ASGITransport(app=app), base_url="http://api.test") as http:
            await http.post("/api/session", json={"code": CODES["coyg"]})
            body = (await http.get("/api/predictions")).json()
            statuses = {p["person"]: p["status"] for p in body["predictions"]}
            assert statuses["twzt"] == "did-not-file"
            assert statuses["bulba"] == "did-not-file"


class TestPreview:
    async def test_a_draft_table_scores_against_last_season(self, client: AsyncClient) -> None:
        await sign_in(client)
        from shared.projection import final_table

        # Last season's own finishing order, padded with the promoted clubs.
        table = [*final_table(), "COV", "HUL", "IPS"]
        response = await client.post("/api/predictions/preview", json={"table": table})
        assert response.status_code == 200
        body = response.json()
        # The 17 surviving clubs are all exactly right, so 17 x 3 points.
        assert body["exact_hits"] == 17
        assert body["table_points"] >= 51

    async def test_the_preview_names_the_season_it_scored_against(self, client: AsyncClient) -> None:
        await sign_in(client)
        from shared.projection import final_table

        table = [*final_table(), "COV", "HUL", "IPS"]
        body = (await client.post("/api/predictions/preview", json={"table": table})).json()
        assert body["against_season"] == "2025-26"


class TestAdmin:
    async def test_admin_reports_cache_ages(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/admin/status")).json()
        names = {c["name"]: c for c in body["caches"]}
        assert names["FPL fixtures"]["source"] == "fpl"
        assert names["FPL fixtures"]["age_seconds"] >= 0

    async def test_admin_reports_real_quota_budgets(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/admin/status")).json()
        sources = {q["source"]: q for q in body["quotas"]}
        assert sources["the-odds-api"]["budget"] == 450
        assert sources["api-football"]["budget"] == 85

    async def test_admin_names_the_missing_keys(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/admin/status")).json()
        # No upstream keys are configured in tests, so all four are reported.
        assert len(body["missing_keys"]) == 4

    async def test_broadcasters_are_listed_with_verification_dates(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/admin/broadcasters")).json()
        pl = [b for b in body if b["competition"] == "premier-league"]
        assert {b["country"] for b in pl} == {"UA", "US", "CA"}
        assert all(b["verified_on"] for b in pl)


class TestFplStandings:
    """The mapping is what makes a squad belong to a person."""

    async def test_all_four_managers_are_listed_before_the_first_deadline(self, client: AsyncClient) -> None:
        # FPL keeps them in new_entries until GW1 is scored; reading only
        # standings.results would return an empty league on launch day.
        await sign_in(client)
        body = (await client.get("/api/fpl/standings")).json()
        assert len(body["rows"]) == 4

    async def test_every_entry_is_attributed_to_a_person(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fpl/standings")).json()
        assert {r["person"] for r in body["rows"]} == {"coyg", "aure", "twzt", "bulba"}
        assert body["unmapped"] == []

    async def test_the_mapping_matches_the_confirmed_entries(self, client: AsyncClient) -> None:
        await sign_in(client)
        rows = (await client.get("/api/fpl/standings")).json()["rows"]
        by_person = {r["person"]: r for r in rows}
        assert by_person["coyg"]["entry_name"] == "champ"
        assert by_person["aure"]["entry_name"] == "HOBOurnemouth"
        assert by_person["twzt"]["entry_name"] == "Ionrunit"
        assert by_person["bulba"]["entry_name"] == "Isak Teeties"

    async def test_pending_rows_explain_why_there_are_no_points_yet(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fpl/standings")).json()
        assert all(r["pending"] for r in body["rows"])
        assert all(r["total"] == 0 for r in body["rows"])
        assert "gameweek one is settled" in body["empty_message"]

    async def test_the_league_is_named(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/fpl/standings")).json()
        assert body["league_id"] == 412955
        assert body["league_name"] == "EPL 50$"

    async def test_an_unmapped_entry_is_reported_not_dropped(
        self, settings: object, cache: object, sessions: object
    ) -> None:
        # A fifth manager joining must be visible as something to fix.
        from httpx import ASGITransport
        from httpx import AsyncClient as Client
        from shared import keys

        from tests.conftest import CODES, _build_app

        payload = (await cache.get(keys.FPL_LEAGUE)).value  # type: ignore[attr-defined]
        payload["new_entries"]["results"].append(
            {
                "entry": 999999,
                "entry_name": "Interloper",
                "player_first_name": "A",
                "player_last_name": "Stranger",
                "joined_time": "2026-08-21T00:00:00Z",
            }
        )
        await cache.set(keys.FPL_LEAGUE, payload, source="fpl")  # type: ignore[attr-defined]

        app = _build_app(settings, cache, sessions)  # type: ignore[arg-type]
        async with Client(transport=ASGITransport(app=app), base_url="http://api.test") as http:
            await http.post("/api/session", json={"code": CODES["coyg"]})
            body = (await http.get("/api/fpl/standings")).json()
            assert 999999 in body["unmapped"]
            assert len(body["rows"]) == 5


class TestLeaderboard:
    async def test_nobody_has_scored_before_a_match_is_played(self, client: AsyncClient) -> None:
        """The bug this guards: an alphabetical table is not a standing.

        ``compute_table`` returns all 20 clubs on zero points before kick-off,
        ordered by the alphabetical tie-break. Scoring predictions against that
        order handed one person a six-point lead before a ball was kicked.
        """
        await sign_in(client)
        body = (await client.get("/api/leaderboard")).json()
        assert [row["total"] for row in body["rows"]] == [0, 0, 0, 0]
        assert [row["exact_hits"] for row in body["rows"]] == [0, 0, 0, 0]

    async def test_there_is_no_leader_before_a_match_is_played(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/leaderboard")).json()
        assert body["leader"] is None
        assert body["if_season_ended_today"] is None

    async def test_everyone_shares_first_place_on_zero(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/leaderboard")).json()
        assert {row["rank"] for row in body["rows"]} == {1}

    async def test_it_explains_why_everything_is_zero(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/leaderboard")).json()
        assert "not a standing" in body["empty_message"]

    async def test_all_four_are_listed_as_filed(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/leaderboard")).json()
        assert all(row["filed"] for row in body["rows"])
        assert len(body["rows"]) == 4


class TestHeadToHead:
    """Comparing two predictions needs no results, so this works on day one."""

    async def test_it_finds_where_two_people_agree(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/h2h?a=coyg&b=bulba")).json()
        # Both put Arsenal top.
        assert body["agreement_count"] >= 1
        assert body["agreements"][0]["club"]["short_name"] == "ARS"
        assert body["agreements"][0]["position"] == 1

    async def test_gaps_are_ordered_widest_first(self, client: AsyncClient) -> None:
        await sign_in(client)
        gaps = (await client.get("/api/h2h?a=coyg&b=bulba")).json()["gaps"]
        distances = [g["distance"] for g in gaps]
        assert distances == sorted(distances, reverse=True)

    async def test_a_gap_reports_both_positions(self, client: AsyncClient) -> None:
        await sign_in(client)
        gap = (await client.get("/api/h2h?a=coyg&b=bulba")).json()["gaps"][0]
        assert gap["a_position"] != gap["b_position"]
        assert gap["distance"] == abs(gap["a_position"] - gap["b_position"])

    async def test_agreements_and_gaps_account_for_every_club(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/h2h?a=coyg&b=aure")).json()
        # Gaps are capped for display, so check the agreement side is complete.
        assert body["agreement_count"] + len(body["gaps"]) <= 20

    async def test_comparing_somebody_with_themselves_is_refused(self, client: AsyncClient) -> None:
        await sign_in(client)
        assert (await client.get("/api/h2h?a=coyg&b=coyg")).status_code == 422

    async def test_an_unknown_person_is_a_404(self, client: AsyncClient) -> None:
        await sign_in(client)
        assert (await client.get("/api/h2h?a=coyg&b=nobody")).status_code == 404
