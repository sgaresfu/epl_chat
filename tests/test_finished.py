"""FPL's `finished` flag lags full time by hours.

The real payload for Arsenal 3-0 Coventry, an hour after the final whistle:

    finished: false
    finished_provisional: true
    minutes: 90
    team_h_score: 3

Trusting `finished` alone made the site call that match live, and left Arsenal
on zero points in the table while they had actually won. Every place that asks
"is this match over?" now goes through one function.
"""

from __future__ import annotations

from typing import Any

import pytest
from services.poller.fpl import compute_table, has_result, is_in_play, is_over

# The exact shape FPL returned after full time, before bonus was confirmed.
PROVISIONAL: dict[str, Any] = {
    "id": 1,
    "event": 1,
    "kickoff_time": "2026-08-21T19:00:00Z",
    "started": True,
    "finished": False,
    "finished_provisional": True,
    "minutes": 90,
    "team_h": 1,
    "team_a": 7,
    "team_h_score": 3,
    "team_a_score": 0,
}

CONFIRMED = {**PROVISIONAL, "finished": True}
IN_PLAY = {
    **PROVISIONAL,
    "finished_provisional": False,
    "minutes": 63,
    "team_h_score": 2,
    "team_a_score": 0,
}
NOT_STARTED = {
    **PROVISIONAL,
    "started": False,
    "finished_provisional": False,
    "minutes": 0,
    "team_h_score": None,
    "team_a_score": None,
}


class TestIsOver:
    def test_a_provisionally_finished_match_is_over(self) -> None:
        # This is the case that was wrong for an hour after every match.
        assert is_over(PROVISIONAL) is True

    def test_a_confirmed_match_is_over(self) -> None:
        assert is_over(CONFIRMED) is True

    def test_a_match_in_play_is_not_over(self) -> None:
        assert is_over(IN_PLAY) is False

    def test_an_unplayed_match_is_not_over(self) -> None:
        assert is_over(NOT_STARTED) is False

    def test_ninety_minutes_with_a_score_counts_even_if_both_flags_lag(self) -> None:
        stubborn = {**PROVISIONAL, "finished_provisional": False}
        assert is_over(stubborn) is True

    def test_ninety_minutes_without_a_score_does_not(self) -> None:
        # A postponed or abandoned match must not be counted as a result.
        odd = {**PROVISIONAL, "finished_provisional": False, "team_h_score": None}
        assert is_over(odd) is False


class TestIsInPlay:
    def test_a_match_at_sixty_three_minutes_is_live(self) -> None:
        assert is_in_play(IN_PLAY) is True

    def test_a_finished_match_is_not_live(self) -> None:
        """The reported bug: the board said LIVE an hour after full time."""
        assert is_in_play(PROVISIONAL) is False

    def test_an_unplayed_match_is_not_live(self) -> None:
        assert is_in_play(NOT_STARTED) is False


class TestTheTableCountsIt:
    def test_the_winner_gets_three_points_before_bonus_is_confirmed(self) -> None:
        """The reported bug: Arsenal had won and still showed zero."""
        table = compute_table([PROVISIONAL])
        arsenal = next(r for r in table if r.club == "ARS")
        assert arsenal.points == 3
        assert arsenal.played == 1
        assert arsenal.goals_for == 3

    def test_the_loser_is_counted_too(self) -> None:
        table = compute_table([PROVISIONAL])
        coventry = next(r for r in table if r.club == "COV")
        assert coventry.points == 0
        assert coventry.played == 1
        assert coventry.goals_against == 3

    def test_the_winner_tops_the_table(self) -> None:
        assert compute_table([PROVISIONAL])[0].club == "ARS"

    def test_a_match_still_in_play_is_not_counted(self) -> None:
        # Points must not be awarded while it can still change.
        table = compute_table([IN_PLAY])
        assert all(r.played == 0 for r in table)

    def test_has_result_requires_both_over_and_a_score(self) -> None:
        assert has_result(PROVISIONAL) is True
        assert has_result(IN_PLAY) is False
        assert has_result({**PROVISIONAL, "team_h_score": None}) is False


class TestEverythingAgrees:
    """One question, one answer, everywhere it is asked."""

    @pytest.mark.parametrize(
        ("module", "name"),
        [
            ("shared.projection", "is_over"),
            ("services.api.views", "is_over"),
            ("services.api.routes.football", "is_over"),
            ("services.api.routes.football", "is_in_play"),
            ("services.api.routes.watch", "is_over"),
        ],
    )
    def test_each_caller_uses_the_shared_helper(self, module: str, name: str) -> None:
        import importlib

        from services.poller import fpl

        imported = getattr(importlib.import_module(module), name)
        assert imported is getattr(fpl, name)

    def test_the_season_timeline_counts_it_as_played(self) -> None:
        from shared import season

        built = season.build([PROVISIONAL], [{"id": 1, "finished": False}])
        assert built.matches_played == 1

    def test_the_projection_does_not_re_project_it(self) -> None:
        from shared.projection import project

        result = project([PROVISIONAL])
        assert result.derived_fixtures == 0
        assert result.modelled_fixtures == 0
