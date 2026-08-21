"""Scoring engine tests, built from the worked examples in BRIEF section 10."""

from __future__ import annotations

from typing import ClassVar

import pytest
from shared.scoring import (
    AWARD_POINTS,
    CHAMPION_AND_RELEGATED_BONUS,
    EXACT_POINTS,
    NEAR_POINTS,
    TOP_FOUR_BONUS,
    Award,
    ScoreBreakdown,
    Standing,
    position_points,
    rank_standings,
    score_awards,
    score_prediction,
    score_table,
)

# A full, valid 20-club finishing order used as the baseline "actual" table.
ACTUAL = [
    "ARS",
    "MCI",
    "LIV",
    "CHE",
    "TOT",
    "MUN",
    "NEW",
    "AVL",
    "BHA",
    "BOU",
    "CRY",
    "FUL",
    "BRE",
    "NFO",
    "EVE",
    "SUN",
    "LEE",
    "COV",
    "HUL",
    "IPS",
]


def _table_with(**moves: int) -> list[str]:
    """Build a predicted table from ACTUAL, forcing specific clubs to given positions."""
    table = [c for c in ACTUAL if c not in moves]
    for club, position in sorted(moves.items(), key=lambda kv: kv[1]):
        table.insert(position - 1, club)
    return table


class TestPositionPoints:
    """The three per-club cases the brief spells out."""

    def test_exact_position_scores_three(self) -> None:
        # Predicted Arsenal 1st, finished 1st -> 3
        assert position_points(1, 1) == EXACT_POINTS

    def test_within_one_place_scores_one(self) -> None:
        # Predicted Chelsea 4th, finished 5th -> 1
        assert position_points(4, 5) == NEAR_POINTS

    def test_four_places_out_scores_nothing(self) -> None:
        # Predicted Everton 19th, finished 15th -> 0
        assert position_points(19, 15) == 0

    def test_within_one_place_counts_in_both_directions(self) -> None:
        assert position_points(5, 4) == NEAR_POINTS
        assert position_points(4, 5) == NEAR_POINTS

    def test_two_places_out_scores_nothing(self) -> None:
        assert position_points(4, 6) == 0

    def test_club_absent_from_actual_table_scores_nothing(self) -> None:
        assert position_points(3, None) == 0


class TestTableBonuses:
    def test_perfect_table_scores_every_position_and_both_bonuses(self) -> None:
        result = score_prediction(ACTUAL, ACTUAL)
        expected = 20 * EXACT_POINTS + TOP_FOUR_BONUS + CHAMPION_AND_RELEGATED_BONUS
        assert result.total == expected
        assert result.exact_hits == 20

    def test_top_four_bonus_lands_in_any_order(self) -> None:
        # Same four clubs, shuffled within the top four.
        predicted = ["CHE", "LIV", "MCI", "ARS", *ACTUAL[4:]]
        _, bonuses = score_table(predicted, ACTUAL)
        assert bonuses.top_four == TOP_FOUR_BONUS

    def test_top_four_bonus_is_all_or_nothing(self) -> None:
        predicted = ["ARS", "MCI", "LIV", "TOT", "CHE", *ACTUAL[5:]]
        _, bonuses = score_table(predicted, ACTUAL)
        assert bonuses.top_four == 0

    def test_top_four_bonus_adds_on_top_of_position_points(self) -> None:
        predicted = ["CHE", "LIV", "MCI", "ARS", *ACTUAL[4:]]
        result = score_prediction(predicted, ACTUAL)
        positions = sum(c.points for c in result.clubs)
        assert result.table_points == positions + TOP_FOUR_BONUS

    def test_champion_and_all_three_relegated_scores_fifteen(self) -> None:
        # Champion right, bottom three right (order among them irrelevant),
        # but the top four deliberately wrong so only the 15 lands.
        predicted = ["ARS", "LIV", "TOT", "MCI", "CHE", *ACTUAL[5:-3], "IPS", "COV", "HUL"]
        _, bonuses = score_table(predicted, ACTUAL)
        assert bonuses.champion_and_relegated == CHAMPION_AND_RELEGATED_BONUS
        assert bonuses.top_four == 0

    def test_champion_wrong_forfeits_the_fifteen(self) -> None:
        predicted = ["MCI", "ARS", "LIV", "CHE", *ACTUAL[4:-3], "IPS", "COV", "HUL"]
        _, bonuses = score_table(predicted, ACTUAL)
        assert bonuses.champion_and_relegated == 0

    def test_one_relegated_club_wrong_forfeits_the_fifteen(self) -> None:
        # Swap LEE (17th) with HUL (19th): champion still right, but the
        # relegated set is now {COV, LEE, IPS} against an actual {COV, HUL, IPS}.
        predicted = list(ACTUAL)
        predicted[16], predicted[18] = predicted[18], predicted[16]
        assert len(set(predicted)) == 20, "the swap must keep the table valid"
        assert set(predicted[-3:]) != set(ACTUAL[-3:])
        _, bonuses = score_table(predicted, ACTUAL)
        assert bonuses.champion_and_relegated == 0

    def test_both_bonuses_stack(self) -> None:
        predicted = ["ARS", "CHE", "LIV", "MCI", *ACTUAL[4:-3], "IPS", "HUL", "COV"]
        _, bonuses = score_table(predicted, ACTUAL)
        assert bonuses.top_four == TOP_FOUR_BONUS
        assert bonuses.champion_and_relegated == CHAMPION_AND_RELEGATED_BONUS
        assert bonuses.total == TOP_FOUR_BONUS + CHAMPION_AND_RELEGATED_BONUS

    def test_incomplete_table_earns_no_all_or_nothing_bonus(self) -> None:
        # Mid-season the "actual" table is still 20 clubs, but a malformed or
        # partial table must not hand out a bonus by accident.
        _, bonuses = score_table(ACTUAL[:10], ACTUAL[:10])
        assert bonuses.total == 0


class TestAwards:
    WINNERS: ClassVar[dict[Award, list[str]]] = {
        Award.GOLDEN_BOOT: ["Haaland", "Isak"],  # a shared Golden Boot
        Award.GOLDEN_GLOVE: ["Raya"],
        Award.DEFENDER: ["Gabriel"],
        Award.PLAYMAKER: ["Odegaard"],
        Award.PLAYER_OF_THE_SEASON: ["Rice"],
    }

    def test_correct_award_scores_five(self) -> None:
        scored = score_awards({Award.GOLDEN_GLOVE: "Raya"}, self.WINNERS)
        assert scored[0].points == AWARD_POINTS

    def test_shared_golden_boot_counts_for_either_winner(self) -> None:
        # "a shared Golden Boot counts if your player is one of the joint winners"
        for pick in ("Haaland", "Isak"):
            scored = score_awards({Award.GOLDEN_BOOT: pick}, self.WINNERS)
            assert scored[0].points == AWARD_POINTS, pick

    def test_wrong_award_pick_scores_nothing(self) -> None:
        scored = score_awards({Award.GOLDEN_BOOT: "Salah"}, self.WINNERS)
        assert scored[0].points == 0

    def test_award_with_no_winner_yet_scores_nothing(self) -> None:
        scored = score_awards({Award.GOLDEN_BOOT: "Haaland"}, {})
        assert scored[0].points == 0
        assert scored[0].winners == ()

    def test_all_five_awards_correct_scores_twenty_five(self) -> None:
        picks = {
            Award.GOLDEN_BOOT: "Haaland",
            Award.GOLDEN_GLOVE: "Raya",
            Award.DEFENDER: "Gabriel",
            Award.PLAYMAKER: "Odegaard",
            Award.PLAYER_OF_THE_SEASON: "Rice",
        }
        result = score_prediction(ACTUAL, ACTUAL, picks, self.WINNERS)
        assert result.award_points == 5 * AWARD_POINTS

    def test_awards_accept_plain_string_keys(self) -> None:
        # Payloads arrive from JSON, so the keys are strings, not enum members.
        scored = score_awards({"golden_glove": "Raya"}, {"golden_glove": ["Raya"]})
        assert scored[0].points == AWARD_POINTS
        assert scored[0].award is Award.GOLDEN_GLOVE


class TestRanking:
    def _standing(self, person: str, total_source: list[str], submitted: str, filed: bool = True) -> Standing:
        return Standing(
            person=person,
            breakdown=score_prediction(total_source, ACTUAL),
            submitted_at=submitted,
            filed=filed,
        )

    def test_higher_total_ranks_first(self) -> None:
        strong = self._standing("COYG", ACTUAL, "2026-08-01")
        weak = self._standing("AURE", list(reversed(ACTUAL)), "2026-08-01")
        ranked = rank_standings([weak, strong])
        assert [s.person for s in ranked] == ["COYG", "AURE"]
        assert ranked[0].rank == 1

    def test_unfiled_prediction_scores_zero_and_sorts_last(self) -> None:
        filed = self._standing("COYG", ACTUAL, "2026-08-01")
        unfiled = Standing(
            person="TWZT",
            breakdown=ScoreBreakdown(clubs=(), awards=(), bonuses=score_prediction([], []).bonuses),
            submitted_at=None,
            filed=False,
        )
        ranked = rank_standings([unfiled, filed])
        assert [s.person for s in ranked] == ["COYG", "TWZT"]
        assert ranked[1].total == 0

    def test_dead_heat_shares_a_rank(self) -> None:
        a = self._standing("COYG", ACTUAL, "2026-08-01")
        b = self._standing("AURE", ACTUAL, "2026-08-02")
        ranked = rank_standings([a, b])
        assert ranked[0].rank == ranked[1].rank == 1

    def test_earlier_submission_breaks_a_dead_heat_in_order(self) -> None:
        late = self._standing("AURE", ACTUAL, "2026-08-20")
        early = self._standing("COYG", ACTUAL, "2026-08-01")
        ranked = rank_standings([late, early])
        assert [s.person for s in ranked] == ["COYG", "AURE"]


class TestSeededPredictions:
    """The two seeded predictions from BRIEF section 6 must score coherently."""

    COYG: ClassVar[list[str]] = [
        "ARS",
        "MCI",
        "LIV",
        "CHE",
        "MUN",
        "AVL",
        "BOU",
        "TOT",
        "CRY",
        "BRE",
        "NEW",
        "BHA",
        "FUL",
        "SUN",
        "NFO",
        "IPS",
        "LEE",
        "HUL",
        "EVE",
        "COV",
    ]
    AURE: ClassVar[list[str]] = [
        "ARS",
        "MCI",
        "CHE",
        "LIV",
        "TOT",
        "MUN",
        "BHA",
        "BOU",
        "AVL",
        "NEW",
        "NFO",
        "SUN",
        "BRE",
        "LEE",
        "EVE",
        "CRY",
        "FUL",
        "COV",
        "IPS",
        "HUL",
    ]

    @pytest.mark.parametrize("table", [COYG, AURE])
    def test_seeded_tables_are_complete_and_unique(self, table: list[str]) -> None:
        assert len(table) == 20
        assert len(set(table)) == 20

    def test_both_seeds_score_against_a_live_table(self) -> None:
        for table in (self.COYG, self.AURE):
            result = score_prediction(table, ACTUAL)
            assert result.total >= 0
            assert len(result.clubs) == 20

    def test_both_seeds_call_arsenal_champions(self) -> None:
        # Both put Arsenal top, so against an Arsenal-winning table both take the exact 3.
        for table in (self.COYG, self.AURE):
            result = score_prediction(table, ACTUAL)
            assert result.clubs[0].points == EXACT_POINTS
