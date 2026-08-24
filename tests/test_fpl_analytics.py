"""The projection model, captaincy and transfer advice.

Pure functions over plain dicts, so every branch is reachable without a
network or a database. The cases that matter are the ones where the model
has to refuse: too small a sample, an injured player, a blank gameweek.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from shared.fpl_analytics import (
    FIXTURE_FACTOR,
    MIN_APPEARANCES,
    appearances_of,
    availability,
    base_points,
    captain_options,
    difficulty_by_club,
    forecast,
    manager_report,
    transfer_ideas,
    worst_managed,
)


def player(**kw: Any) -> dict[str, Any]:
    base = {
        "id": 1,
        "web_name": "Player",
        "element_type": 3,
        "team": 1,
        "now_cost": 75,
        "points_per_game": "5.0",
        "form": "5.0",
        "minutes": 900,
        "starts": 10,
        "status": "a",
        "chance_of_playing_next_round": None,
        "total_points": 50,
        "ep_next": "4.0",
    }
    base.update(kw)
    return base


class TestAvailability:
    def test_a_fit_regular_starter_is_close_to_full(self) -> None:
        a = availability(player(minutes=900, starts=10))
        assert a.label == "fit"
        assert a.factor == pytest.approx(1.0)

    @pytest.mark.parametrize(
        ("status", "reason"),
        [("i", "injured"), ("s", "suspended"), ("u", "unavailable"), ("n", "ineligible")],
    )
    def test_an_unavailable_player_scores_nothing(self, status: str, reason: str) -> None:
        a = availability(player(status=status))
        assert a.factor == 0.0
        assert a.label == "out"
        assert a.note == reason

    def test_a_doubt_is_discounted_by_the_published_percentage(self) -> None:
        a = availability(player(chance_of_playing_next_round=25))
        assert a.label == "doubt"
        assert a.factor == pytest.approx(0.25)
        assert "25%" in a.note

    def test_a_null_chance_means_no_doubt_rather_than_unknown(self) -> None:
        """The field reads the wrong way round, which is worth pinning down."""
        assert availability(player(chance_of_playing_next_round=None)).label == "fit"

    def test_zero_percent_is_out_not_merely_doubtful(self) -> None:
        assert availability(player(chance_of_playing_next_round=0)).label == "out"

    def test_a_rotation_risk_is_discounted(self) -> None:
        a = availability(player(minutes=900, starts=2))
        assert a.label == "rotation"
        assert a.factor < 0.6

    def test_a_player_with_no_minutes_is_unproven(self) -> None:
        a = availability(player(minutes=0, starts=0))
        assert a.label == "unproven"
        assert 0 < a.factor < 0.5


class TestBase:
    def test_it_blends_season_and_form(self) -> None:
        assert base_points(player(points_per_game="4.0", form="6.0")) == pytest.approx(4.8)

    def test_form_alone_carries_a_player_with_no_season_average(self) -> None:
        assert base_points(player(points_per_game="0", form="6.0")) == 6.0

    def test_no_form_falls_back_to_the_season_average(self) -> None:
        assert base_points(player(points_per_game="4.0", form="0")) == 4.0

    def test_strings_and_nulls_do_not_crash_it(self) -> None:
        assert base_points({"points_per_game": None, "form": "nonsense"}) == 0.0


class TestAppearances:
    def test_minutes_become_whole_appearances(self) -> None:
        assert appearances_of(player(minutes=270)) == 3
        assert appearances_of(player(minutes=269)) == 2
        assert appearances_of(player(minutes=0)) == 0


class TestForecast:
    def test_an_easy_fixture_scores_higher_than_a_hard_one(self) -> None:
        easy = forecast(player(), difficulty=1, club_short="ARS")
        hard = forecast(player(), difficulty=5, club_short="ARS")
        assert easy.expected_points > hard.expected_points

    def test_with_no_prior_the_projection_is_purely_the_observed_rate(self) -> None:
        """Pinned exactly, so a change to the blend cannot pass unnoticed."""
        f = forecast(player(ep_next="0", minutes=90 * 10, starts=10), difficulty=1, club_short="ARS")
        assert f.basis == "observed"
        assert f.expected_points == pytest.approx(5.0 * FIXTURE_FACTOR[1], rel=1e-3)

    def test_an_injured_player_projects_zero_however_good_they_are(self) -> None:
        f = forecast(player(points_per_game="9.0", form="9.0", status="i"), 1, "ARS")
        assert f.expected_points == 0.0
        assert f.availability == "out"

    def test_a_thin_sample_is_flagged_rather_than_hidden(self) -> None:
        f = forecast(player(minutes=90), difficulty=3, club_short="ARS")
        assert f.appearances == 1
        assert f.confident is False
        assert f.basis == "blended"
        assert any("partly an estimate" in r for r in f.reasons)

    def test_one_appearance_and_no_prior_is_too_little_to_use(self) -> None:
        f = forecast(player(minutes=90, ep_next="0"), difficulty=3, club_short="ARS")
        assert f.basis == "thin"
        assert any("too little" in r for r in f.reasons)

    def test_enough_minutes_earns_confidence(self) -> None:
        f = forecast(player(minutes=90 * MIN_APPEARANCES), difficulty=3, club_short="ARS")
        assert f.confident is True

    def test_it_carries_the_readable_fields_the_ui_needs(self) -> None:
        f = forecast(player(now_cost=125, element_type=4), 2, "MCI")
        assert f.price == 12.5
        assert f.position == "FWD"
        assert f.club == "MCI"


class TestDifficulty:
    FIXTURES: ClassVar[list[dict[str, Any]]] = [
        {"event": 5, "team_h": 1, "team_a": 2, "team_h_difficulty": 2, "team_a_difficulty": 4},
        {"event": 6, "team_h": 2, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 3},
    ]

    def test_it_reads_one_gameweek(self) -> None:
        d = difficulty_by_club(self.FIXTURES, gameweek=5, horizon=1)
        assert d[1] == 2
        assert d[2] == 4

    def test_it_averages_over_a_horizon(self) -> None:
        d = difficulty_by_club(self.FIXTURES, gameweek=5, horizon=2)
        assert d[1] == round((2 + 3) / 2)
        assert d[2] == round((4 + 3) / 2)

    def test_a_club_with_no_fixture_is_absent_rather_than_guessed(self) -> None:
        assert 99 not in difficulty_by_club(self.FIXTURES, gameweek=5, horizon=1)

    def test_fixtures_outside_the_window_are_ignored(self) -> None:
        assert difficulty_by_club(self.FIXTURES, gameweek=9, horizon=1) == {}


class TestCaptain:
    def test_the_highest_projection_wears_the_armband(self) -> None:
        squad = [
            forecast(player(id=1, web_name="Low", points_per_game="2.0", form="2.0"), 3, "ARS"),
            forecast(player(id=2, web_name="High", points_per_game="8.0", form="8.0"), 2, "MCI"),
        ]
        picks = captain_options(squad)
        assert picks[0].forecast.name == "High"
        assert picks[0].doubled == pytest.approx(picks[0].forecast.expected_points * 2)
        assert picks[0].rank == 1

    def test_a_one_game_wonder_is_shrunk_rather_than_taken_at_face_value(self) -> None:
        """The brief warns against projecting from a two-game mean.

        A hard gate would answer that by refusing to advise at all, which in
        gameweek 1 means advising nobody about anything. Shrinkage answers it
        properly: a single 20-point return is pulled most of the way back to
        the league's own expectation, and the recommendation carries the
        sample size so the reader can see what it rests on.
        """
        newcomer = forecast(
            player(id=2, web_name="Newcomer", points_per_game="20.0", minutes=90, starts=1, ep_next="4.0"),
            difficulty=1,
            club_short="MCI",
        )
        raw_rate = 20.0
        assert newcomer.expected_points < raw_rate / 2, "a single big return must not be trusted whole"
        assert newcomer.basis == "blended"
        assert newcomer.appearances == 1

        pick = captain_options([newcomer])[0]
        assert pick.forecast.basis == "blended", "the interface is told what this rests on"

    def test_an_unavailable_player_is_not_recommended(self) -> None:
        squad = [
            forecast(player(id=1, web_name="Fit", points_per_game="5.0"), 3, "ARS"),
            forecast(player(id=2, web_name="Injured", points_per_game="20.0", status="i"), 1, "MCI"),
        ]
        assert [p.forecast.name for p in captain_options(squad)] == ["Fit"]

    def test_an_empty_squad_yields_no_advice_rather_than_an_error(self) -> None:
        assert captain_options([]) == []


class TestTransfers:
    def squad(self) -> list[Any]:
        return [
            forecast(
                player(id=1, web_name="Weak", element_type=3, points_per_game="2.0", form="2.0", now_cost=60),
                4,
                "BOU",
            ),
            forecast(
                player(
                    id=2, web_name="Strong", element_type=3, points_per_game="8.0", form="8.0", now_cost=100
                ),
                2,
                "ARS",
            ),
        ]

    def market(self) -> list[Any]:
        return [
            forecast(
                player(
                    id=10, web_name="Better", element_type=3, points_per_game="6.0", form="6.0", now_cost=65
                ),
                2,
                "MCI",
            ),
            forecast(
                player(
                    id=11, web_name="Pricey", element_type=3, points_per_game="9.0", form="9.0", now_cost=140
                ),
                1,
                "LIV",
            ),
            forecast(
                player(
                    id=12, web_name="WrongPos", element_type=1, points_per_game="9.0", form="9.0", now_cost=50
                ),
                1,
                "LIV",
            ),
        ]

    def test_it_replaces_the_weakest_player(self) -> None:
        ideas = transfer_ideas(self.squad(), self.market(), bank=1.0)
        assert ideas
        assert ideas[0].out_player.name == "Weak"
        assert ideas[0].gain > 0

    def test_it_will_not_suggest_somebody_unaffordable(self) -> None:
        ideas = transfer_ideas(self.squad(), self.market(), bank=0.0)
        assert all(i.in_player.name != "Pricey" for i in ideas)

    def test_a_bigger_bank_unlocks_a_better_target(self) -> None:
        rich = transfer_ideas(self.squad(), self.market(), bank=8.0)
        assert rich[0].in_player.name == "Pricey"

    def test_it_never_crosses_positions(self) -> None:
        ideas = transfer_ideas(self.squad(), self.market(), bank=50.0)
        assert all(i.in_player.name != "WrongPos" for i in ideas)
        assert all(i.in_player.position == i.out_player.position for i in ideas)

    def test_it_never_suggests_a_player_already_owned(self) -> None:
        squad = self.squad()
        ideas = transfer_ideas(squad, squad + self.market(), bank=50.0)
        owned = {f.element for f in squad}
        assert all(i.in_player.element not in owned for i in ideas)

    def test_a_sideways_move_is_not_offered(self) -> None:
        squad = [forecast(player(id=1, points_per_game="6.0", form="6.0"), 3, "ARS")]
        market = [forecast(player(id=2, web_name="Same", points_per_game="6.0", form="6.0"), 3, "MCI")]
        assert transfer_ideas(squad, market, bank=5.0) == []

    def test_a_target_with_no_signal_at_all_is_never_recommended(self) -> None:
        """No minutes *and* no published prior means unknown, not promising."""
        squad = [forecast(player(id=1, points_per_game="2.0", form="2.0"), 3, "ARS")]
        market = [
            forecast(
                player(id=2, web_name="Unknown", minutes=0, points_per_game="0", form="0", ep_next="0"),
                1,
                "MCI",
            )
        ]
        assert transfer_ideas(squad, market, bank=50.0) == []

    def test_a_hot_start_is_discounted_before_it_is_recommended(self) -> None:
        squad = [forecast(player(id=1, points_per_game="2.0", form="2.0"), 3, "ARS")]
        market = [
            forecast(
                player(id=2, web_name="Hot", points_per_game="15.0", minutes=90, starts=1, ep_next="4.0"),
                1,
                "MCI",
            )
        ]
        ideas = transfer_ideas(squad, market, bank=50.0)
        assert ideas, "a shrunk estimate is still usable advice"
        assert ideas[0].in_player.expected_points < 15.0 / 2
        assert any("league's own expectation" in r for r in ideas[0].reasoning)

    def test_the_reasoning_is_populated_and_readable(self) -> None:
        ideas = transfer_ideas(self.squad(), self.market(), bank=1.0)
        assert ideas[0].reasoning
        assert any("points better" in r for r in ideas[0].reasoning)


class TestManagerReport:
    def squad(self, **kw: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "person": "coyg",
            "live_points": 40,
            "bench_points": 7,
            "bench_counts": False,
            "players_to_play": 2,
            "captain": {"name": "Haaland", "points": 2, "multiplier": 2},
            "starting": [
                {"name": "Haaland", "points": 2},
                {"name": "Saka", "points": 12},
            ],
            "bench": [{"name": "Sub", "points": 7}],
        }
        base.update(kw)
        return base

    def test_it_names_the_better_armband_that_was_available(self) -> None:
        r = manager_report(self.squad())
        assert r.captain == "Haaland"
        assert r.best_captain == "Saka"
        assert r.captain_cost == 10  # (12 - 2) x (2 - 1)

    def test_bench_points_count_as_wasted_only_when_the_bench_is_not_counting(self) -> None:
        assert manager_report(self.squad()).bench_wasted == 7
        assert manager_report(self.squad(bench_counts=True)).bench_wasted == 0

    def test_a_perfect_round_says_so(self) -> None:
        r = manager_report(
            self.squad(
                bench_points=0,
                captain={"name": "Saka", "points": 12, "multiplier": 2},
                starting=[{"name": "Saka", "points": 12}],
            )
        )
        assert r.captain_cost == 0
        assert r.bench_wasted == 0
        assert "Nothing left" in r.verdict

    def test_a_triple_captain_multiplies_the_regret(self) -> None:
        r = manager_report(self.squad(captain={"name": "Haaland", "points": 2, "multiplier": 3}))
        assert r.captain_cost == 20  # (12 - 2) x (3 - 1)

    def test_an_empty_squad_does_not_crash(self) -> None:
        r = manager_report({"person": "coyg"})
        assert r.live_points == 0
        assert r.captain is None


class TestWorstManaged:
    def test_it_names_whoever_left_most_on_the_table(self) -> None:
        a = manager_report({"person": "a", "bench_points": 12, "starting": [], "captain": None})
        b = manager_report({"person": "b", "bench_points": 2, "starting": [], "captain": None})
        assert worst_managed([a, b]).person == "a"

    def test_a_flawless_round_for_everybody_names_nobody(self) -> None:
        clean = manager_report({"person": "a", "bench_points": 0, "starting": [], "captain": None})
        assert worst_managed([clean]) is None

    def test_it_judges_decisions_rather_than_the_score(self) -> None:
        """A low score can be bad luck; a full bench is a choice."""
        unlucky = manager_report(
            {"person": "unlucky", "live_points": 12, "bench_points": 0, "starting": [], "captain": None}
        )
        careless = manager_report(
            {"person": "careless", "live_points": 90, "bench_points": 15, "starting": [], "captain": None}
        )
        assert worst_managed([unlucky, careless]).person == "careless"


class TestShrinkage:
    """A thin sample is shrunk toward FPL's own published expectation.

    Refusing to project at all would be honest and useless: in gameweek 1 no
    player in the league has three appearances, so a hard gate leaves the
    whole feature blank for the first month of every season.
    """

    def test_a_player_with_no_minutes_is_entirely_the_prior(self) -> None:
        f = forecast(
            player(minutes=0, starts=0, points_per_game="0", form="0", ep_next="4.0"),
            difficulty=3,
            club_short="ARS",
        )
        assert f.basis == "prior"
        # The availability discount for an unproven player still applies.
        assert f.expected_points == pytest.approx(4.0 * 0.35, rel=1e-3)
        assert any("league's own expectation" in r for r in f.reasons)

    def test_a_long_record_leans_on_the_player_not_the_prior(self) -> None:
        many = forecast(
            player(minutes=90 * 20, starts=20, points_per_game="8.0", form="8.0", ep_next="2.0"),
            difficulty=3,
            club_short="ARS",
        )
        few = forecast(
            player(minutes=90, starts=1, points_per_game="8.0", form="8.0", ep_next="2.0"),
            difficulty=3,
            club_short="ARS",
        )
        assert many.basis == "observed"
        assert few.basis == "blended"
        assert many.expected_points > few.expected_points, (
            "twenty games of evidence should outweigh the prior more than one game does"
        )

    def test_the_weight_moves_smoothly_with_the_sample(self) -> None:
        xs = [
            forecast(
                player(minutes=90 * n, starts=n, points_per_game="8.0", form="8.0", ep_next="2.0"),
                3,
                "ARS",
            ).expected_points
            for n in (0, 1, 4, 12)
        ]
        assert xs == sorted(xs), "more evidence of a good player should never lower the projection"

    def test_the_fixture_factor_is_not_applied_to_the_prior_twice(self) -> None:
        """ep_next already accounts for the fixture, so only the observed half
        is scaled by difficulty. With no minutes the projection must not move
        when the fixture changes."""
        easy = forecast(player(minutes=0, points_per_game="0", form="0", ep_next="4.0"), 1, "ARS")
        hard = forecast(player(minutes=0, points_per_game="0", form="0", ep_next="4.0"), 5, "ARS")
        assert easy.expected_points == pytest.approx(hard.expected_points)

    def test_no_prior_and_no_minutes_is_marked_unusable(self) -> None:
        f = forecast(player(minutes=0, points_per_game="0", form="0", ep_next="0"), 3, "ARS")
        assert f.basis == "thin"

    def test_an_unusable_player_is_never_captained_or_recommended(self) -> None:
        thin = forecast(player(id=9, minutes=0, points_per_game="0", form="0", ep_next="0"), 3, "ARS")
        good = forecast(player(id=8, minutes=900, points_per_game="6.0", form="6.0"), 3, "ARS")
        assert [c.forecast.element for c in captain_options([thin, good])] == [8]
        assert transfer_ideas([good], [thin], bank=50.0) == []

    def test_an_injured_player_projects_zero_even_with_a_healthy_prior(self) -> None:
        f = forecast(player(status="i", ep_next="9.0"), 1, "ARS")
        assert f.expected_points == 0.0

    def test_early_season_advice_says_what_it_rests_on(self) -> None:
        squad = [forecast(player(id=1, minutes=0, points_per_game="0", form="0", ep_next="1.0"), 3, "ARS")]
        market = [
            forecast(
                player(id=2, web_name="Prior", minutes=0, points_per_game="0", form="0", ep_next="6.0"),
                3,
                "MCI",
            )
        ]
        ideas = transfer_ideas(squad, market, bank=50.0)
        assert ideas
        assert any("league's own expectation" in r for r in ideas[0].reasoning)
