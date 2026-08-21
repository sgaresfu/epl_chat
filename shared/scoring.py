"""The scoring engine -- the single source of truth for both languages.

Pure functions, no I/O. The leaderboard, the "if the season ended today" panel,
the history chart and the picker preview all call :func:`score_prediction`.
The frontend never reimplements these rules; it renders what the API returns,
and the picker's instant preview goes through ``POST /api/predictions/preview``
so there is exactly one implementation of the maths.

Rules (BRIEF section 10):

* 3 points per club predicted in its exact finishing position
* 1 point per club predicted within one place of its finish
* 5 points per correct award pick
* 10 bonus for a perfect top four, in any order
* 15 bonus for the champion plus all three relegated clubs
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

EXACT_POINTS: Final = 3
NEAR_POINTS: Final = 1
AWARD_POINTS: Final = 5
TOP_FOUR_BONUS: Final = 10
CHAMPION_AND_RELEGATED_BONUS: Final = 15

TABLE_SIZE: Final = 20
RELEGATION_PLACES: Final = 3


class Award(StrEnum):
    """The five season awards a prediction can name."""

    GOLDEN_BOOT = "golden_boot"
    GOLDEN_GLOVE = "golden_glove"
    DEFENDER = "defender"
    PLAYMAKER = "playmaker"
    PLAYER_OF_THE_SEASON = "player_of_the_season"


@dataclass(frozen=True, slots=True)
class ClubScore:
    """What one club in a predicted table was worth."""

    club: str
    predicted_position: int
    actual_position: int | None
    points: int

    @property
    def is_exact(self) -> bool:
        return self.points == EXACT_POINTS

    @property
    def is_near(self) -> bool:
        return self.points == NEAR_POINTS


@dataclass(frozen=True, slots=True)
class AwardScore:
    """What one award pick was worth."""

    award: Award
    pick: str
    winners: tuple[str, ...]
    points: int

    @property
    def is_correct(self) -> bool:
        return self.points == AWARD_POINTS


@dataclass(frozen=True, slots=True)
class Bonuses:
    """The two all-or-nothing bonuses, reported separately so the UI can explain them."""

    top_four: int = 0
    champion_and_relegated: int = 0

    @property
    def total(self) -> int:
        return self.top_four + self.champion_and_relegated


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """A complete, explainable score for one person's prediction."""

    clubs: tuple[ClubScore, ...]
    awards: tuple[AwardScore, ...]
    bonuses: Bonuses

    @property
    def table_points(self) -> int:
        """Per-position points plus the two table bonuses."""
        return sum(c.points for c in self.clubs) + self.bonuses.total

    @property
    def award_points(self) -> int:
        return sum(a.points for a in self.awards)

    @property
    def total(self) -> int:
        return self.table_points + self.award_points

    @property
    def exact_hits(self) -> int:
        """Clubs placed exactly right -- the first leaderboard tie-break."""
        return sum(1 for c in self.clubs if c.is_exact)

    @property
    def near_hits(self) -> int:
        return sum(1 for c in self.clubs if c.is_near)


def position_points(predicted_position: int, actual_position: int | None) -> int:
    """Points for a single club: 3 exact, 1 within one place, otherwise 0.

    ``actual_position`` is ``None`` when the club does not appear in the actual
    table at all, which scores nothing rather than raising -- a prediction naming
    a club that was later expelled or replaced should not crash the leaderboard.
    """
    if actual_position is None:
        return 0
    delta = abs(predicted_position - actual_position)
    if delta == 0:
        return EXACT_POINTS
    if delta == 1:
        return NEAR_POINTS
    return 0


def _positions(table: Sequence[str]) -> dict[str, int]:
    """Map club -> 1-indexed position."""
    return {club: index + 1 for index, club in enumerate(table)}


def score_table(
    predicted: Sequence[str],
    actual: Sequence[str],
) -> tuple[tuple[ClubScore, ...], Bonuses]:
    """Score a predicted 1-20 table against the actual one.

    Both sequences are canonical club short names (see :mod:`shared.clubs`).
    Returns the per-club breakdown and the two bonuses.
    """
    actual_positions = _positions(actual)
    scores = tuple(
        ClubScore(
            club=club,
            predicted_position=index + 1,
            actual_position=actual_positions.get(club),
            points=position_points(index + 1, actual_positions.get(club)),
        )
        for index, club in enumerate(predicted)
    )
    return scores, _bonuses(predicted, actual)


def _bonuses(predicted: Sequence[str], actual: Sequence[str]) -> Bonuses:
    """The top-four and champion-plus-relegated bonuses.

    Both are all-or-nothing and they stack: a prediction that nails the top four
    *and* the champion with all three relegated clubs earns both, per the brief's
    worked examples.
    """
    if len(actual) < TABLE_SIZE or len(predicted) < TABLE_SIZE:
        # An unfinished or malformed table cannot settle all-or-nothing bonuses.
        return Bonuses()

    top_four = TOP_FOUR_BONUS if set(predicted[:4]) == set(actual[:4]) else 0

    champion_right = predicted[0] == actual[0]
    relegated_right = set(predicted[-RELEGATION_PLACES:]) == set(actual[-RELEGATION_PLACES:])
    both = CHAMPION_AND_RELEGATED_BONUS if champion_right and relegated_right else 0

    return Bonuses(top_four=top_four, champion_and_relegated=both)


def score_awards(
    picks: Mapping[Award | str, str],
    winners: Mapping[Award | str, Sequence[str]],
) -> tuple[AwardScore, ...]:
    """Score award picks against the final winners.

    ``winners`` maps each award to *every* winner, so a shared Golden Boot counts
    for anyone who named one of the joint winners. An award with no recorded
    winner yet scores zero and is reported with an empty winner list, which is
    what the UI shows mid-season.
    """
    scored: list[AwardScore] = []
    for award_key, pick in picks.items():
        award = Award(award_key)
        award_winners = tuple(winners.get(award, ()) or winners.get(award.value, ()) or ())
        points = AWARD_POINTS if pick and pick in award_winners else 0
        scored.append(AwardScore(award=award, pick=pick, winners=award_winners, points=points))
    scored.sort(key=lambda a: list(Award).index(a.award))
    return tuple(scored)


def score_prediction(
    predicted_table: Sequence[str],
    actual_table: Sequence[str],
    award_picks: Mapping[Award | str, str] | None = None,
    award_winners: Mapping[Award | str, Sequence[str]] | None = None,
) -> ScoreBreakdown:
    """Score one person's complete prediction.

    This is the function every caller uses. ``actual_table`` may be the live
    table mid-season, which is exactly how "if the season ended today" works --
    the rules do not change, only the table they are applied to.
    """
    clubs, bonuses = score_table(predicted_table, actual_table)
    awards = score_awards(award_picks or {}, award_winners or {})
    return ScoreBreakdown(clubs=clubs, awards=awards, bonuses=bonuses)


@dataclass(frozen=True, slots=True)
class Standing:
    """One row of the prediction leaderboard."""

    person: str
    breakdown: ScoreBreakdown
    submitted_at: str | None
    filed: bool
    rank: int = 0

    @property
    def total(self) -> int:
        return self.breakdown.total if self.filed else 0


def rank_standings(standings: Sequence[Standing]) -> tuple[Standing, ...]:
    """Order the leaderboard and assign ranks, sharing a rank on a dead heat.

    Tie-break, in order (a decision the brief left open):

    1. total points
    2. exact positions hit -- rewards precision over spread-the-risk guessing
    3. champion called correctly
    4. earliest submission, so filing early is never a disadvantage

    Anyone who did not file scores zero and sorts last regardless.
    """

    def sort_key(s: Standing) -> tuple[int, int, int, str]:
        champion_right = 0
        if s.filed and s.breakdown.clubs:
            first = s.breakdown.clubs[0]
            champion_right = 1 if first.actual_position == 1 else 0
        return (
            -s.total,
            -(s.breakdown.exact_hits if s.filed else 0),
            -champion_right,
            s.submitted_at or "9999",
        )

    ordered = sorted(standings, key=sort_key)

    ranked: list[Standing] = []
    for index, standing in enumerate(ordered):
        rank = index + 1
        if index and sort_key(ordered[index - 1])[:3] == sort_key(standing)[:3]:
            rank = ranked[index - 1].rank
        ranked.append(
            Standing(
                person=standing.person,
                breakdown=standing.breakdown,
                submitted_at=standing.submitted_at,
                filed=standing.filed,
                rank=rank,
            )
        )
    return tuple(ranked)


class InvalidTableError(ValueError):
    """Raised when a predicted table is not a legal 1-20 ordering."""

    def __init__(self, reason: str, detail: Sequence[str] = ()) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = tuple(detail)


def validate_table(table: Sequence[str], known_clubs: Sequence[str]) -> None:
    """Reject a predicted table that is short, duplicated or unknown.

    The picker enforces "no duplicates, no submitting with gaps" in the UI, but
    the UI is not the guard -- ``PUT /api/predictions`` calls this before it
    writes, because a client-side check is not a constraint.
    """
    if len(table) != TABLE_SIZE:
        raise InvalidTableError(f"a prediction needs all {TABLE_SIZE} positions, got {len(table)}")

    gaps = [club for club in table if not club]
    if gaps:
        raise InvalidTableError("every position must name a club")

    seen: set[str] = set()
    duplicates: list[str] = []
    for club in table:
        if club in seen and club not in duplicates:
            duplicates.append(club)
        seen.add(club)
    if duplicates:
        raise InvalidTableError("a club cannot appear twice", duplicates)

    allowed = set(known_clubs)
    unknown = [club for club in table if club not in allowed]
    if unknown:
        raise InvalidTableError("unknown club in prediction", unknown)
