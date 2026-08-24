"""Match picks: a scoreline per fixture, and the all-time record that follows.

Two rules the server enforces rather than trusting the client with:

**A pick closes at kick-off.** Not at the client's idea of kick-off, and not
by hiding the control -- the ``PUT`` refuses. Anything else is an honour
system, and the whole point of a prediction is that it was made in advance.

**Nobody sees anybody else's pick until the whistle.** Same reason the season
tables are redacted before the lock: a pick you can copy is not a prediction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from shared import keys
from shared.clubs import by_fpl_id
from shared.models import (
    FixturePicksOut,
    PickIn,
    PickOut,
    PickRoundOut,
    PickStandingsOut,
    PickStatsOut,
)
from shared.picks import Pick, Result, rank, score_pick, summarise
from shared.timezones import PLACES

from services.api import repository, views
from services.api.deps import CurrentSession, Db, State
from services.api.routes.session import person_out
from services.poller.fpl import is_over

log = structlog.get_logger(__name__)
router = APIRouter(tags=["picks"])

SCORING_NOTE = (
    "5 for the exact score, 2 for the right result, and 1 more for the right "
    "number of goals — the goals bonus is separate, so 3–1 on a 1–3 still scores."
)


async def _fixtures(state: State) -> tuple[list[dict[str, Any]], Any]:
    entry = await state.cache.get(keys.FPL_FIXTURES)
    rows = entry.value if entry else None
    return (rows if isinstance(rows, list) else []), entry


def _kicked_off(row: dict[str, Any], now: datetime) -> bool:
    """Whether picking has closed.

    Either the feed says it started, or the clock has passed the kickoff --
    the second half matters because FPL's ``started`` flag lags, and a pick
    accepted during the first ten minutes would be worthless.
    """
    if bool(row.get("started")):
        return True
    raw = row.get("kickoff_time")
    if not raw:
        return False
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")) <= now


def _result_of(row: dict[str, Any]) -> Result | None:
    if not is_over(row):
        return None
    home, away = row.get("team_h_score"), row.get("team_a_score")
    if home is None or away is None:
        return None
    return Result(home_goals=int(home), away_goals=int(away))


@router.get("/api/picks", response_model=PickRoundOut)
async def picks_round(
    session: CurrentSession,
    state: State,
    db: Db,
    gameweek: int | None = Query(None, ge=1, le=38),
) -> PickRoundOut:
    rows, entry = await _fixtures(state)
    if not rows:
        return PickRoundOut(
            gameweek=gameweek or 0,
            freshness=views.freshness(entry, keys.FPL_FIXTURES),
            empty_message="Fixtures appear once the poller has loaded the schedule.",
        )

    target = gameweek
    if target is None:
        # The round people care about is the one being played, or the next
        # one if this week is done.
        upcoming = [r for r in rows if not is_over(r) and r.get("event")]
        target = int(upcoming[0]["event"]) if upcoming else int(rows[-1].get("event") or 1)

    selected = sorted(
        (r for r in rows if r.get("event") == target),
        key=lambda r: (r.get("kickoff_time") or "9999", r.get("id", 0)),
    )
    now = datetime.now(UTC)

    stored = await repository.load_picks(db, (int(r["id"]) for r in selected))
    by_fixture: dict[int, list[tuple[Any, str]]] = {}
    for pick, key in stored:
        by_fixture.setdefault(pick.fixture_id, []).append((pick, key))

    odds_map = await _odds_for(state, db, selected)

    out: list[FixturePicksOut] = []
    for row in selected:
        fixture_id = int(row["id"])
        started = _kicked_off(row, now)
        result = _result_of(row)

        entries: list[PickOut] = []
        mine: PickOut | None = None
        for pick, key in by_fixture.get(fixture_id, []):
            scored = (
                score_pick(
                    Pick(
                        person=key,
                        fixture_id=fixture_id,
                        home_goals=pick.home_goals,
                        away_goals=pick.away_goals,
                    ),
                    result,
                )
                if result
                else None
            )
            item = PickOut(
                person=key,
                fixture_id=fixture_id,
                home_goals=pick.home_goals,
                away_goals=pick.away_goals,
                points=scored.points if scored else None,
                exact=bool(scored and scored.exact),
                outcome_hit=bool(scored and scored.outcome_hit),
                total_hit=bool(scored and scored.total_hit),
            )
            if key == session.person:
                mine = item
            if started:
                entries.append(item)

        out.append(
            FixturePicksOut(
                fixture_id=fixture_id,
                gameweek=int(row.get("event") or 0),
                kickoff=views._parse(row.get("kickoff_time")),
                home=views.club_out(by_fpl_id(int(row["team_h"]))),
                away=views.club_out(by_fpl_id(int(row["team_a"]))),
                home_score=row.get("team_h_score"),
                away_score=row.get("team_a_score"),
                started=started,
                finished=is_over(row),
                open_for_picks=not started,
                revealed=started,
                my_pick=mine,
                picks=sorted(entries, key=lambda p: p.person),
                odds=odds_map.get(fixture_id),
            )
        )

    return PickRoundOut(
        gameweek=target,
        fixtures=out,
        freshness=views.freshness(entry, keys.FPL_FIXTURES),
        empty_message=None if out else f"No fixtures in gameweek {target}.",
    )


async def _odds_for(state: State, db: Db, rows: list[dict[str, Any]]) -> dict[int, Any]:
    odds_entry = await state.cache.get(keys.ODDS_ROUND)
    cache = odds_entry.value if odds_entry and isinstance(odds_entry.value, dict) else None
    history = await repository.odds_drift_bulk(db, (int(r["id"]) for r in rows))
    now = datetime.now(UTC)
    return {
        int(r["id"]): views.build_odds_for_row(r, cache, history.get(int(r["id"]), []), now) for r in rows
    }


@router.put("/api/picks", response_model=PickOut)
async def save_pick(body: PickIn, session: CurrentSession, state: State, db: Db) -> PickOut:
    rows, _ = await _fixtures(state)
    row = next((r for r in rows if int(r["id"]) == body.fixture_id), None)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such fixture.")

    if _kicked_off(row, datetime.now(UTC)):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="That match has kicked off. Picks close at kick-off.",
        )

    # Snapshot the market as it stands, so "did you beat the bookmaker" is
    # judged against the price this person actually had in front of them.
    odds_entry = await state.cache.get(keys.ODDS_ROUND)
    cache = odds_entry.value if odds_entry and isinstance(odds_entry.value, dict) else {}
    home = by_fpl_id(int(row["team_h"])).short_name
    away = by_fpl_id(int(row["team_a"])).short_name
    market = cache.get(f"{home}-{away}") if isinstance(cache, dict) else None
    snapshot: tuple[float | None, float | None, float | None] = (None, None, None)
    if isinstance(market, dict) and market.get("available"):
        snapshot = (market.get("home"), market.get("draw"), market.get("away"))

    saved = await repository.save_pick(
        db, session.person, body.fixture_id, body.home_goals, body.away_goals, snapshot
    )
    return PickOut(
        person=session.person,
        fixture_id=saved.fixture_id,
        home_goals=saved.home_goals,
        away_goals=saved.away_goals,
    )


@router.get("/api/picks/stats", response_model=PickStandingsOut)
async def pick_stats(_: CurrentSession, state: State, db: Db) -> PickStandingsOut:
    """All-time, recomputed on read.

    There is no nightly job and no stored aggregate: the record is a fold over
    picks and results, both of which are already here, so it cannot drift out
    of date and there is no cache to invalidate when a match finishes.
    """
    rows, _entry = await _fixtures(state)
    results: dict[int, Result] = {}
    order: dict[int, str] = {}
    for row in rows:
        result = _result_of(row)
        if result is not None:
            results[int(row["id"])] = result
            order[int(row["id"])] = str(row.get("kickoff_time") or "")

    stored = await repository.load_picks(db)
    # Oldest first, because the streak counters walk the list in order.
    by_person: dict[str, list[tuple[Pick, Result]]] = {p.key: [] for p in PLACES}
    for pick, key in sorted(stored, key=lambda pr: order.get(pr[0].fixture_id, "")):
        result = results.get(pick.fixture_id)
        if result is None or key not in by_person:
            continue
        by_person[key].append(
            (
                Pick(
                    person=key,
                    fixture_id=pick.fixture_id,
                    home_goals=pick.home_goals,
                    away_goals=pick.away_goals,
                    odds_home=pick.odds_home,
                    odds_draw=pick.odds_draw,
                    odds_away=pick.odds_away,
                ),
                result,
            )
        )

    stats = rank([summarise(key, settled) for key, settled in by_person.items()])
    total = sum(s.settled for s in stats)

    return PickStandingsOut(
        rows=[
            PickStatsOut(
                person=person_out(s.person),
                settled=s.settled,
                points=s.points,
                points_per_pick=s.points_per_pick,
                exact=s.exact,
                exact_pct=s.exact_pct,
                outcomes=s.outcomes,
                outcome_pct=s.outcome_pct,
                totals=s.totals,
                total_pct=s.total_pct,
                current_streak=s.current_streak,
                best_streak=s.best_streak,
                predicted_goals=s.predicted_goals,
                actual_goals=s.actual_goals,
                goal_bias=s.goal_bias,
                home_pct=s.home_pct,
                with_market=s.with_market,
                followed_favourite=s.followed_favourite,
                bold=s.bold,
                bold_hits=s.bold_hits,
                bold_pct=s.bold_pct,
                market_points=s.market_points,
                edge=s.edge,
            )
            for s in stats
        ],
        total_settled=total,
        scoring=SCORING_NOTE,
        empty_message=(
            None
            if total
            else "No picks have been settled yet. Pick a scoreline on any match before it kicks off."
        ),
    )
