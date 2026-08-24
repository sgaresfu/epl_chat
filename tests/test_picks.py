"""Match-pick scoring and records.

Pure functions, so these are exhaustive where it is cheap to be: every
combination of exact / outcome / total is checked explicitly rather than
trusting one happy path.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from shared.picks import (
    CORRECT_OUTCOME,
    CORRECT_TOTAL,
    EXACT_SCORE,
    MAX_POINTS,
    Outcome,
    Pick,
    Result,
    outcome_of,
    rank,
    score_pick,
    summarise,
)


def pick(h: int, a: int, person: str = "coyg", **odds: float) -> Pick:
    return Pick(person=person, fixture_id=1, home_goals=h, away_goals=a, **odds)


class TestOutcome:
    def test_it_reads_the_three_results(self) -> None:
        assert outcome_of(2, 1) is Outcome.HOME
        assert outcome_of(1, 2) is Outcome.AWAY
        assert outcome_of(0, 0) is Outcome.DRAW

    def test_a_scoreline_derives_its_own_markets(self) -> None:
        p = pick(2, 1)
        assert p.outcome is Outcome.HOME
        assert p.total == 3


class TestScoring:
    def test_an_exact_score_takes_the_top_award_and_the_total_bonus(self) -> None:
        s = score_pick(pick(2, 1), Result(2, 1))
        assert s.exact is True
        assert s.outcome_hit is True
        assert s.total_hit is True
        assert s.points == EXACT_SCORE + CORRECT_TOTAL == MAX_POINTS

    def test_the_exact_award_does_not_stack_with_the_outcome_award(self) -> None:
        """2-1 on a 2-1 is five plus the total bonus, not seven plus."""
        s = score_pick(pick(2, 1), Result(2, 1))
        assert s.points == 6
        assert s.points < EXACT_SCORE + CORRECT_OUTCOME + CORRECT_TOTAL

    def test_the_right_result_at_the_wrong_score(self) -> None:
        s = score_pick(pick(2, 0), Result(3, 1))
        assert (s.exact, s.outcome_hit, s.total_hit) == (False, True, False)
        assert s.points == CORRECT_OUTCOME

    def test_the_right_result_and_the_right_total(self) -> None:
        s = score_pick(pick(2, 1), Result(3, 0))
        assert (s.exact, s.outcome_hit, s.total_hit) == (False, True, True)
        assert s.points == CORRECT_OUTCOME + CORRECT_TOTAL

    def test_the_total_bonus_is_independent_of_the_result(self) -> None:
        """3-1 on a 1-3: wrong side entirely, but four goals was right."""
        s = score_pick(pick(3, 1), Result(1, 3))
        assert (s.exact, s.outcome_hit, s.total_hit) == (False, False, True)
        assert s.points == CORRECT_TOTAL

    def test_a_miss_scores_nothing(self) -> None:
        s = score_pick(pick(2, 0), Result(0, 3))
        assert s.points == 0

    def test_a_drawn_pick_on_a_different_drawn_score(self) -> None:
        s = score_pick(pick(1, 1), Result(2, 2))
        assert (s.exact, s.outcome_hit, s.total_hit) == (False, True, False)
        assert s.points == CORRECT_OUTCOME

    @pytest.mark.parametrize(
        ("ph", "pa", "rh", "ra", "expected"),
        [
            (0, 0, 0, 0, 6),  # exact goalless
            (1, 1, 1, 1, 6),
            (4, 0, 0, 4, 1),  # mirror image: wrong side, four goals right
            (1, 0, 0, 1, 1),  # mirror image again -- one goal each way still totals 1
            (2, 0, 0, 1, 0),  # wrong side and wrong total: nothing
        ],
    )
    def test_a_table_of_cases(self, ph: int, pa: int, rh: int, ra: int, expected: int) -> None:
        assert score_pick(pick(ph, pa), Result(rh, ra)).points == expected


class TestFavourite:
    def test_the_shortest_price_is_the_favourite(self) -> None:
        p = pick(1, 0, odds_home=1.40, odds_draw=4.75, odds_away=8.00)
        assert p.favourite is Outcome.HOME

    def test_an_away_favourite(self) -> None:
        p = pick(1, 0, odds_home=8.50, odds_draw=5.00, odds_away=1.36)
        assert p.favourite is Outcome.AWAY

    def test_no_market_means_no_favourite(self) -> None:
        assert pick(1, 0).favourite is None

    def test_a_partial_market_is_not_a_market(self) -> None:
        assert pick(1, 0, odds_home=1.4, odds_draw=4.0).favourite is None

    def test_a_nonsense_price_is_not_trusted(self) -> None:
        assert pick(1, 0, odds_home=0.5, odds_draw=4.0, odds_away=8.0).favourite is None


class TestSummary:
    def test_an_empty_record_is_all_zeroes_and_does_not_divide_by_zero(self) -> None:
        s = summarise("coyg", [])
        assert s.settled == 0
        assert s.points == 0
        assert s.points_per_pick == 0.0
        assert s.exact_pct == 0.0
        assert s.goal_bias == 0.0

    def test_it_totals_points_and_hits(self) -> None:
        s = summarise(
            "coyg",
            [
                (pick(2, 1), Result(2, 1)),  # exact -> 6
                (pick(1, 0), Result(3, 1)),  # outcome -> 2
                (pick(0, 0), Result(1, 2)),  # nothing -> 0
            ],
        )
        assert s.settled == 3
        assert s.points == 8
        assert s.exact == 1
        assert s.outcomes == 2
        assert s.points_per_pick == round(8 / 3, 2)
        assert s.exact_pct == round(100 / 3, 1)

    def test_streaks_run_forward_through_the_list(self) -> None:
        s = summarise(
            "coyg",
            [
                (pick(1, 0), Result(1, 0)),  # hit
                (pick(1, 0), Result(2, 0)),  # hit
                (pick(1, 0), Result(0, 1)),  # miss, breaks it
                (pick(1, 0), Result(3, 0)),  # hit
            ],
        )
        assert s.best_streak == 2
        assert s.current_streak == 1

    def test_a_broken_streak_at_the_end_reports_zero(self) -> None:
        s = summarise("coyg", [(pick(1, 0), Result(1, 0)), (pick(1, 0), Result(0, 1))])
        assert s.current_streak == 0
        assert s.best_streak == 1

    def test_goal_bias_is_positive_for_an_optimist(self) -> None:
        s = summarise("coyg", [(pick(3, 2), Result(1, 0)), (pick(2, 2), Result(0, 1))])
        assert s.predicted_goals == 4.5
        assert s.actual_goals == 1.0
        assert s.goal_bias == 3.5

    def test_home_bias_is_counted(self) -> None:
        s = summarise(
            "coyg",
            [(pick(2, 0), Result(0, 0)), (pick(1, 0), Result(0, 0)), (pick(0, 1), Result(0, 0))],
        )
        assert s.home_picks == 2
        assert s.home_pct == round(200 / 3, 1)


class TestAgainstTheMarket:
    HOME_FAV: ClassVar[dict[str, float]] = {"odds_home": 1.40, "odds_draw": 4.75, "odds_away": 8.00}
    AWAY_FAV: ClassVar[dict[str, float]] = {"odds_home": 8.50, "odds_draw": 5.00, "odds_away": 1.36}

    def test_following_the_favourite_is_counted_separately_from_defying_it(self) -> None:
        s = summarise(
            "coyg",
            [
                (pick(2, 0, **self.HOME_FAV), Result(2, 0)),  # followed, right
                (pick(0, 1, **self.HOME_FAV), Result(0, 1)),  # bold, right
                (pick(0, 2, **self.HOME_FAV), Result(3, 0)),  # bold, wrong
            ],
        )
        assert s.with_market == 3
        assert s.followed_favourite == 1
        assert s.bold == 2
        assert s.bold_hits == 1
        assert s.bold_pct == 50.0

    def test_picks_without_a_market_are_left_out_of_the_comparison(self) -> None:
        s = summarise("coyg", [(pick(1, 0), Result(1, 0)), (pick(1, 0, **self.HOME_FAV), Result(1, 0))])
        assert s.settled == 2
        assert s.with_market == 1

    def test_the_edge_is_measured_against_backing_the_favourite_every_time(self) -> None:
        # Match 1: favourite home, finished home. Blindly backing it scores 2.
        #          The person called it exactly, so scores 6.
        # Match 2: favourite home, finished away. The market scores 0; the
        #          person went against it and was right, so scores 2.
        s = summarise(
            "coyg",
            [
                (pick(2, 0, **self.HOME_FAV), Result(2, 0)),
                (pick(0, 1, **self.HOME_FAV), Result(0, 2)),
            ],
        )
        assert s.market_points == 2
        assert s.points_with_market == 8
        assert s.edge == 6

    def test_a_negative_edge_when_the_market_would_have_done_better(self) -> None:
        s = summarise("coyg", [(pick(0, 3, **self.HOME_FAV), Result(1, 0))])
        assert s.market_points == 2
        assert s.points_with_market == 0
        assert s.edge == -2

    def test_an_away_favourite_is_recognised(self) -> None:
        s = summarise("coyg", [(pick(0, 2, **self.AWAY_FAV), Result(0, 2))])
        assert s.followed_favourite == 1
        assert s.bold == 0


class TestRanking:
    def test_points_decide_it(self) -> None:
        a = summarise("aure", [(pick(1, 0, "aure"), Result(1, 0))])
        b = summarise("bulba", [(pick(1, 0, "bulba"), Result(2, 0))])
        assert [s.person for s in rank([b, a])] == ["aure", "bulba"]

    def test_exact_scores_break_a_tie_on_points(self) -> None:
        # Six points each: one exact-and-total, versus three outcome-only.
        a = summarise("aure", [(pick(1, 0, "aure"), Result(1, 0))])
        b = summarise(
            "bulba",
            [(pick(1, 0, "bulba"), Result(2, 0))] * 3,
        )
        assert a.points == b.points == 6
        assert [s.person for s in rank([b, a])] == ["aure", "bulba"]

    def test_it_is_stable_and_alphabetical_at_the_very_end(self) -> None:
        empties = [summarise(p, []) for p in ("twzt", "coyg", "bulba")]
        assert [s.person for s in rank(empties)] == ["bulba", "coyg", "twzt"]
