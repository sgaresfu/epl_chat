"""The fantasy mini-league.

Standings are read from the cache the poller fills, then attributed to people
through the stored mapping in :mod:`shared.fpl_people`.

Two states matter here and both are live right now:

* Before the first deadline FPL keeps members in ``new_entries`` and leaves
  ``standings.results`` empty, so every row is ``pending`` and there are no
  points to show yet. That is reported as a real state, not as an error.
* An entry with no mapping is listed as unattributed rather than dropped, so a
  new manager joining is visible instead of silently missing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from shared import fpl_analytics as analytics
from shared import keys
from shared.clubs import by_fpl_id as club_of
from shared.fpl_people import person_for
from shared.models import (
    CaptainPickOut,
    ForecastOut,
    FplAdviceOut,
    FplChipOut,
    FplPlayerOut,
    FplSquadOut,
    FplSquadsOut,
    FplStandingRow,
    FplStandingsOut,
    ManagerAdviceOut,
    ManagerReportOut,
    TransferIdeaOut,
)

from services.api import views
from services.api.deps import Config, CurrentSession, State
from services.poller.fpl import (
    chips_for,
    current_gameweek,
    is_over,
    live_stats,
    parse_league,
    player_index,
)

router = APIRouter(tags=["fpl"])


@router.get("/api/fpl/standings", response_model=FplStandingsOut)
async def standings(_: CurrentSession, state: State, settings: Config) -> FplStandingsOut:
    entry = await state.cache.get(keys.FPL_LEAGUE)
    payload: dict[str, Any] = entry.value if entry else {}

    boot = await state.cache.get(keys.FPL_BOOTSTRAP)
    event = current_gameweek(boot.value) if boot else None
    gameweek = int(event["id"]) if event else 0

    if not payload:
        return FplStandingsOut(
            league_id=settings.fpl_league_id,
            league_name="",
            rows=[],
            gameweek=gameweek,
            freshness=views.freshness(entry, keys.FPL_LEAGUE),
            empty_message="The mini-league appears once the poller has fetched it.",
        )

    members = parse_league(payload)
    rows: list[FplStandingRow] = []
    unmapped: list[int] = []

    for member in members:
        person = person_for(member.entry_id)
        if person is None:
            unmapped.append(member.entry_id)
        rows.append(
            FplStandingRow(
                entry_id=member.entry_id,
                entry_name=member.entry_name,
                player_name=member.player_name,
                person=person,
                rank=member.rank,
                total=member.total,
                event_total=member.event_total,
                pending=member.pending,
            )
        )

    # Pending entries have no rank yet, so order them by person for a stable
    # list rather than by a rank that does not exist.
    rows.sort(key=lambda r: (r.rank is None, r.rank or 0, r.person or "zz"))

    all_pending = bool(rows) and all(r.pending for r in rows)
    return FplStandingsOut(
        league_id=settings.fpl_league_id,
        league_name=str(payload.get("league", {}).get("name", "")),
        rows=rows,
        gameweek=gameweek,
        freshness=views.freshness(entry, keys.FPL_LEAGUE),
        empty_message=(
            "All four managers are registered. FPL keeps new entries out of the "
            "scored standings until gameweek one is settled, so points appear "
            "after the first round."
            if all_pending
            else None
        ),
        unmapped=unmapped,
    )


# --------------------------------------------------------------------------
# Squads
# --------------------------------------------------------------------------

STARTING_SLOTS = 11

# FPL's own names for the chips. Bench Boost is the one that changes the
# arithmetic: it makes the four bench players score for real, so a total that
# only sums the starting XI is wrong for exactly the weeks somebody plays it.
BENCH_BOOST = "bboost"


@router.get("/api/fpl/squads", response_model=FplSquadsOut)
async def squads(_: CurrentSession, state: State, settings: Config, gw: int | None = None) -> FplSquadsOut:
    """Every squad, live, from the moment teams are picked.

    FPL exposes picks as soon as the deadline passes -- long before the round is
    "scored" -- so there is no reason to withhold them. Points simply read zero
    until players take the pitch, which is the honest state rather than a
    withheld one.
    """
    boot_entry = await state.cache.get(keys.FPL_BOOTSTRAP)
    league_entry = await state.cache.get(keys.FPL_LEAGUE)

    event = current_gameweek(boot_entry.value) if boot_entry else None
    gameweek = gw or (int(event["id"]) if event else 1)

    if boot_entry is None or league_entry is None:
        return FplSquadsOut(
            gameweek=gameweek,
            freshness=views.freshness(league_entry, keys.FPL_LEAGUE),
            empty_message="Squads appear once the poller has fetched the league.",
        )

    players = player_index(boot_entry.value)
    live_entry = await state.cache.get(keys.fpl_live(gameweek))
    live = live_stats(live_entry.value) if live_entry else {}

    members = parse_league(league_entry.value)
    raw: dict[int, dict[str, Any]] = {}
    for member in members:
        cached = await state.cache.get(keys.fpl_picks(member.entry_id, gameweek))
        if cached is not None:
            raw[member.entry_id] = cached.value

    if not raw:
        return FplSquadsOut(
            gameweek=gameweek,
            freshness=views.freshness(league_entry, keys.FPL_LEAGUE),
            empty_message=(
                "Squads are locked until the gameweek deadline. They appear here the moment it passes."
            ),
        )

    # A differential is a player nobody else in the league owns.
    ownership: dict[int, int] = {}
    for picks in raw.values():
        for pick in picks.get("picks", []):
            ownership[int(pick["element"])] = ownership.get(int(pick["element"]), 0) + 1

    built: list[FplSquadOut] = []
    captains: dict[str, str] = {}

    for member in members:
        picks_payload = raw.get(member.entry_id)
        if picks_payload is None:
            continue

        starting: list[FplPlayerOut] = []
        bench: list[FplPlayerOut] = []
        captain: FplPlayerOut | None = None
        vice: FplPlayerOut | None = None

        for pick in picks_payload.get("picks", []):
            element = int(pick["element"])
            info = players.get(element, {"name": f"#{element}", "club": "?", "position": "?"})
            stats = live.get(element, {})
            slot = int(pick.get("position", 0))
            multiplier = int(pick.get("multiplier", 1))
            base = int(stats.get("points", 0))

            player = FplPlayerOut(
                element=element,
                name=str(info["name"]),
                club=str(info["club"]),
                position=str(info["position"]),
                slot=slot,
                is_captain=bool(pick.get("is_captain")),
                is_vice_captain=bool(pick.get("is_vice_captain")),
                multiplier=multiplier,
                on_bench=slot > STARTING_SLOTS,
                # The captain's armband doubles what they score.
                points=base * (multiplier if slot <= STARTING_SLOTS else 1),
                minutes=int(stats.get("minutes", 0)),
                goals=int(stats.get("goals", 0)),
                assists=int(stats.get("assists", 0)),
                bonus=int(stats.get("bonus", 0)),
                played=bool(stats.get("played", False)),
                differential=ownership.get(element, 0) == 1,
            )

            if player.is_captain:
                captain = player
            if player.is_vice_captain:
                vice = player
            (bench if player.on_bench else starting).append(player)

        starting.sort(key=lambda p: p.slot)
        bench.sort(key=lambda p: p.slot)

        person = person_for(member.entry_id)
        if person and captain:
            captains[person] = captain.name

        history_entry = await state.cache.get(keys.fpl_history(member.entry_id))
        chips = (
            [
                FplChipOut(
                    code=c.code,
                    name=c.name,
                    half=c.half,
                    played_in=c.played_in,
                    played=c.played,
                )
                for c in chips_for(boot_entry.value, history_entry.value)
            ]
            if history_entry is not None
            else []
        )

        chip = picks_payload.get("active_chip")
        boosted = chip == BENCH_BOOST
        bench_points = sum(p.points for p in bench)
        counted = starting + bench if boosted else starting

        built.append(
            FplSquadOut(
                person=person,
                entry_id=member.entry_id,
                entry_name=member.entry_name,
                starting=starting,
                bench=bench,
                captain=captain,
                vice_captain=vice,
                chip=chip,
                # With Bench Boost the bench counts; without it, those points
                # are the ones left behind.
                live_points=sum(p.points for p in counted),
                bench_points=bench_points,
                bench_counts=boosted,
                chips=chips,
                players_played=sum(1 for p in counted if p.played),
                players_to_play=sum(1 for p in counted if not p.played),
            )
        )

    built.sort(key=lambda s: (-s.live_points, s.person or "zz"))

    return FplSquadsOut(
        gameweek=gameweek,
        squads=built,
        captains=captains,
        freshness=views.freshness(live_entry, keys.FPL_LEAGUE),
        note=(
            "Points update every 30 seconds while matches are in play. A player "
            "who has not kicked off yet reads zero rather than being hidden."
        ),
    )


@router.get("/api/fpl/advice", response_model=FplAdviceOut)
async def advice(_: CurrentSession, state: State) -> FplAdviceOut:
    """Projections, captaincy and transfers for all four squads.

    Everything is computed from the cache the poller already fills -- the
    bootstrap for player form and availability, the fixture list for
    difficulty, the stored picks for who owns whom. No upstream call, so this
    stays on the same footing as every other read in the app.
    """
    boot_entry = await state.cache.get(keys.FPL_BOOTSTRAP)
    league_entry = await state.cache.get(keys.FPL_LEAGUE)
    fixtures_entry = await state.cache.get(keys.FPL_FIXTURES)

    event = current_gameweek(boot_entry.value) if boot_entry else None
    gameweek = int(event["id"]) if event else 1

    if boot_entry is None or league_entry is None or fixtures_entry is None:
        return FplAdviceOut(
            gameweek=gameweek,
            freshness=views.freshness(boot_entry, keys.FPL_BOOTSTRAP),
            empty_message="Advice appears once the poller has fetched the squads and fixtures.",
        )

    boot = boot_entry.value
    fixtures = fixtures_entry.value if isinstance(fixtures_entry.value, list) else []

    # The round being advised on is the next one to be played.
    next_gw = gameweek if not _round_complete(fixtures, gameweek) else gameweek + 1
    difficulty = analytics.difficulty_by_club(fixtures, next_gw, horizon=1)

    club_short: dict[int, str] = {}
    for element in boot.get("elements", []):
        team = int(element.get("team", 0))
        if team not in club_short:
            try:
                club_short[team] = club_of(team).short_name
            except Exception:  # pragma: no cover - unknown club id
                club_short[team] = str(team)

    # Forecast every player once; the squads then index into it.
    market: dict[int, analytics.Forecast] = {}
    for element in boot.get("elements", []):
        team = int(element.get("team", 0))
        market[int(element["id"])] = analytics.forecast(
            element, difficulty.get(team, 3), club_short.get(team, "?")
        )

    members = parse_league(league_entry.value)
    managers: list[ManagerAdviceOut] = []
    reports: list[analytics.ManagerReport] = []

    squads_payload = await squads(_, state, state.settings)
    by_person = {s.person: s for s in squads_payload.squads if s.person}

    for member in members:
        person = person_for(member.entry_id)
        if person is None:
            continue
        squad_out = by_person.get(person)
        if squad_out is None:
            continue

        reports.append(analytics.manager_report(squad_out.model_dump()))

        owned_ids = [p.element for p in squad_out.starting] + [p.element for p in squad_out.bench]
        squad_forecasts = [market[e] for e in owned_ids if e in market]
        xi_forecasts = [market[p.element] for p in squad_out.starting if p.element in market]

        bank = await _bank_for(state, member.entry_id)
        ideas = analytics.transfer_ideas(squad_forecasts, list(market.values()), bank=bank)
        captains = analytics.captain_options(xi_forecasts)

        # Every usable forecast counts toward the total; the shrinkage has
        # already discounted the thin ones, so excluding them would understate
        # the squad rather than qualify it.
        usable = [f for f in xi_forecasts if f.basis != "thin"]
        projected = round(sum(f.expected_points for f in usable), 1)
        observed = sum(1 for f in xi_forecasts if f.basis == "observed")

        managers.append(
            ManagerAdviceOut(
                person=person,
                entry_name=squad_out.entry_name,
                bank=bank,
                captain_now=squad_out.captain.name if squad_out.captain else None,
                captains=[
                    CaptainPickOut(rank=c.rank, doubled=c.doubled, player=_forecast_out(c.forecast))
                    for c in captains
                ],
                transfers=[
                    TransferIdeaOut(
                        out_player=_forecast_out(i.out_player),
                        in_player=_forecast_out(i.in_player),
                        gain=i.gain,
                        reasoning=i.reasoning,
                    )
                    for i in ideas
                ],
                projected_points=projected,
                projected_from=observed,
                squad_size=len(xi_forecasts),
                note=(
                    ""
                    if observed == len(xi_forecasts)
                    else (
                        f"{len(xi_forecasts) - observed} of the XI have played too little to judge on "
                        "their own record, so those lean on the league's expectation."
                    )
                ),
            )
        )

    worst = analytics.worst_managed(reports)

    return FplAdviceOut(
        gameweek=next_gw,
        managers=managers,
        reports=[
            ManagerReportOut(
                person=r.person,
                live_points=r.live_points,
                bench_points=r.bench_points,
                bench_wasted=r.bench_wasted,
                captain=r.captain,
                captain_points=r.captain_points,
                best_captain=r.best_captain,
                best_captain_points=r.best_captain_points,
                captain_cost=r.captain_cost,
                players_to_play=r.players_to_play,
                verdict=r.verdict,
            )
            for r in reports
        ],
        worst=worst.person if worst else None,
        worst_reason=worst.verdict if worst else None,
        freshness=views.freshness(boot_entry, keys.FPL_BOOTSTRAP),
        empty_message=None if managers else "No squads to advise on yet.",
        method=(
            "Expected points are points-per-game and recent form, discounted for "
            "availability and scaled by fixture difficulty. Nothing is projected "
            f"from fewer than {analytics.MIN_APPEARANCES} full matches of minutes."
        ),
    )


def _forecast_out(f: analytics.Forecast) -> ForecastOut:
    return ForecastOut(
        element=f.element,
        name=f.name,
        club=f.club,
        position=f.position,
        price=f.price,
        expected_points=f.expected_points,
        appearances=f.appearances,
        confident=f.confident,
        availability=f.availability,
        difficulty=f.difficulty,
        basis=f.basis,
        reasons=f.reasons,
    )


def _round_complete(fixtures: list[dict[str, Any]], gameweek: int) -> bool:
    rows = [r for r in fixtures if r.get("event") == gameweek]
    return bool(rows) and all(is_over(r) for r in rows)


async def _bank_for(state: State, entry_id: int) -> float:
    """Money in hand, from the manager's own history.

    Falls back to zero rather than guessing: recommending a transfer the
    person cannot afford is worse than recommending a cheaper one.
    """
    entry = await state.cache.get(keys.fpl_history(entry_id))
    if entry is None or not isinstance(entry.value, dict):
        return 0.0
    rounds = entry.value.get("current") or []
    if not rounds:
        return 0.0
    return float(rounds[-1].get("bank", 0)) / 10
