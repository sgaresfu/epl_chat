"""Match picks: one scoreline per fixture, and everything that follows from it.

**Why a single scoreline rather than a form with four markets.** A pick of
2-1 already contains the outcome (home win), the total (three goals), the
margin (one) and whether both teams scored. Asking separately for each invites
contradiction -- somebody picks "draw" and "2-1" and the app has to decide
which they meant -- and triples the interface for information already given.
One number pair in, five markets out.

Scoring follows the shape used by office pools everywhere, because it is
already understood and it rewards the right thing: getting the result is worth
something, calling the exact score is worth much more, and the total-goals
bonus is independent so a 3-1 pick on a 1-3 result still earns something for
reading the game.

The market comparison is the part worth having. Every pick stores the bet365
prices *as they were when it was made*, so "did you beat the bookmaker" is
measured against what the bookmaker actually thought at the moment of the
decision, not against a price that moved afterwards. Following the favourite
every week is a real strategy with a real return; this says whether anybody is
beating it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

# Points. Deliberately not configurable: one scheme everybody plays.
EXACT_SCORE = 5
CORRECT_OUTCOME = 2
CORRECT_TOTAL = 1
MAX_POINTS = EXACT_SCORE + CORRECT_TOTAL


class Outcome(StrEnum):
    HOME = "H"
    DRAW = "D"
    AWAY = "A"


OutcomeLike = Literal["H", "D", "A"]


def outcome_of(home_goals: int, away_goals: int) -> Outcome:
    if home_goals > away_goals:
        return Outcome.HOME
    if home_goals < away_goals:
        return Outcome.AWAY
    return Outcome.DRAW


@dataclass(frozen=True, slots=True)
class Pick:
    """One person's call on one fixture, with the market at the time."""

    person: str
    fixture_id: int
    home_goals: int
    away_goals: int
    # bet365's 1X2 prices when the pick was saved. Absent when the poller had
    # no price for that match, which is normal for a fixture picked early.
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None

    @property
    def outcome(self) -> Outcome:
        return outcome_of(self.home_goals, self.away_goals)

    @property
    def total(self) -> int:
        return self.home_goals + self.away_goals

    @property
    def favourite(self) -> Outcome | None:
        """The shortest of the three prices, or ``None`` with no market."""
        prices = {
            Outcome.HOME: self.odds_home,
            Outcome.DRAW: self.odds_draw,
            Outcome.AWAY: self.odds_away,
        }
        priced = {k: v for k, v in prices.items() if v is not None and v > 1.0}
        if len(priced) < 3:
            return None
        return min(priced, key=lambda k: priced[k])


@dataclass(frozen=True, slots=True)
class Result:
    home_goals: int
    away_goals: int

    @property
    def outcome(self) -> Outcome:
        return outcome_of(self.home_goals, self.away_goals)

    @property
    def total(self) -> int:
        return self.home_goals + self.away_goals


@dataclass(frozen=True, slots=True)
class PickScore:
    points: int
    exact: bool
    outcome_hit: bool
    total_hit: bool


def score_pick(pick: Pick, result: Result) -> PickScore:
    """Score one settled pick.

    The exact-score award subsumes the outcome award rather than stacking with
    it -- 2-1 on a 2-1 is worth five, not seven -- but the total-goals bonus is
    independent, so calling three goals in a 3-0 that finished 1-2 still earns
    a point for reading the shape of the game.
    """
    exact = pick.home_goals == result.home_goals and pick.away_goals == result.away_goals
    outcome_hit = pick.outcome == result.outcome
    total_hit = pick.total == result.total

    points = EXACT_SCORE if exact else (CORRECT_OUTCOME if outcome_hit else 0)
    if total_hit:
        points += CORRECT_TOTAL
    return PickScore(points=points, exact=exact, outcome_hit=outcome_hit, total_hit=total_hit)


@dataclass(frozen=True, slots=True)
class PickStats:
    """Everything worth knowing about one person's record."""

    person: str
    settled: int
    points: int
    exact: int
    outcomes: int
    totals: int

    # Streaks over correct outcomes, newest pick last.
    current_streak: int
    best_streak: int

    # Mean goals predicted against mean goals scored. A person who reliably
    # predicts 3-2 in a league that averages 2.7 goals is readable, and this
    # is the number that says so.
    predicted_goals: float
    actual_goals: float

    home_picks: int

    # Against the bookmaker, over the subset of picks that had a market.
    with_market: int
    followed_favourite: int
    bold: int
    bold_hits: int
    market_points: int

    @property
    def points_per_pick(self) -> float:
        return round(self.points / self.settled, 2) if self.settled else 0.0

    @property
    def exact_pct(self) -> float:
        return _pct(self.exact, self.settled)

    @property
    def outcome_pct(self) -> float:
        return _pct(self.outcomes, self.settled)

    @property
    def total_pct(self) -> float:
        return _pct(self.totals, self.settled)

    @property
    def home_pct(self) -> float:
        return _pct(self.home_picks, self.settled)

    @property
    def bold_pct(self) -> float:
        """How often a pick against the favourite came off."""
        return _pct(self.bold_hits, self.bold)

    @property
    def goal_bias(self) -> float:
        """Positive means they expect more goals than the league produces."""
        return round(self.predicted_goals - self.actual_goals, 2)

    @property
    def edge(self) -> int:
        """Points above what backing the favourite every week would have scored.

        Only meaningful over ``with_market`` picks, which is what both sides
        of the subtraction are computed from.
        """
        return self.points_with_market - self.market_points

    # Points earned on exactly the picks that had a market, so the comparison
    # is like for like.
    points_with_market: int = 0


def _pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def summarise(person: str, settled: Sequence[tuple[Pick, Result]]) -> PickStats:
    """Fold one person's settled picks into a record.

    ``settled`` must be ordered oldest first: the streak counters walk it in
    order and would otherwise report the streak backwards.
    """
    points = exact = outcomes = totals = home_picks = 0
    predicted = actual = 0
    current = best = 0
    with_market = followed = bold = bold_hits = market_points = points_with_market = 0

    for pick, result in settled:
        score = score_pick(pick, result)
        points += score.points
        exact += score.exact
        outcomes += score.outcome_hit
        totals += score.total_hit
        predicted += pick.total
        actual += result.total
        if pick.outcome is Outcome.HOME:
            home_picks += 1

        current = current + 1 if score.outcome_hit else 0
        best = max(best, current)

        favourite = pick.favourite
        if favourite is not None:
            with_market += 1
            points_with_market += score.points
            if pick.outcome is favourite:
                followed += 1
            else:
                bold += 1
                if score.outcome_hit:
                    bold_hits += 1
            # What backing the favourite blindly would have earned on this
            # match: the outcome award only, since a price implies no score.
            if favourite is result.outcome:
                market_points += CORRECT_OUTCOME

    n = len(settled)
    return PickStats(
        person=person,
        settled=n,
        points=points,
        exact=exact,
        outcomes=outcomes,
        totals=totals,
        current_streak=current,
        best_streak=best,
        predicted_goals=round(predicted / n, 2) if n else 0.0,
        actual_goals=round(actual / n, 2) if n else 0.0,
        home_picks=home_picks,
        with_market=with_market,
        followed_favourite=followed,
        bold=bold,
        bold_hits=bold_hits,
        market_points=market_points,
        points_with_market=points_with_market,
    )


def rank(stats: Sequence[PickStats]) -> list[PickStats]:
    """Best first.

    Points, then exact scores, then outcome accuracy, then name -- the same
    shape as the season leaderboard's tie-break, so the two tables in this app
    break ties the same way rather than each inventing its own rule.
    """
    return sorted(
        stats,
        key=lambda s: (-s.points, -s.exact, -s.outcomes, s.person),
    )
