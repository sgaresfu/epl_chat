"""Expected points, captaincy and transfer advice.

Everything here is a pure function over plain dictionaries — the FPL bootstrap
and fixture payloads exactly as the poller cached them. No network, no
database, no clock. That is what makes it testable, and a projection nobody
can test is a horoscope.

**The model.** Expected points for one player in one gameweek is

    xP = base * minutes * fixture

where *base* blends this season's points per game with recent form, *minutes*
is the probability they are on the pitch at all, and *fixture* scales by how
hard the opponent is. Three terms, each independently checkable, rather than
one opaque score.

**On thin samples.** BRIEF section 6 is explicit that a projection from fewer
than three appearances is noise and the interface has to say so. Refusing to
answer at all, though, makes the feature dead for the first month of every
season -- in gameweek 1 *no* player in the league has three appearances.

So this shrinks toward a prior instead. FPL publishes its own expected points
for the coming round as ``ep_next``, available from day one, and a player's
own mean is blended toward it with a weight of ``apps / (apps + 4)``. With no
minutes played the projection is entirely the prior; by ten appearances it is
mostly the player. That is standard empirical-Bayes shrinkage and it is the
honest answer to a small sample -- far better than either a two-game mean
presented as fact or a blank panel.

Every forecast still carries its sample size and says which of the three it
is resting on, so the interface can be explicit about how much is observation
and how much is prior.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

# BRIEF section 6: below this, a mean is noise and the interface must say so.
MIN_APPEARANCES = 3

# Shrinkage half-weight. At four appearances a player's own mean and the prior
# count equally; below that the prior dominates, above it the player does.
SHRINKAGE_K = 4.0

# FPL difficulty runs 1 (easiest) to 5. The spread is deliberately gentle:
# fixture matters, but a good player against a hard opponent still beats a
# poor one against an easy opponent, and a wider spread stops being true.
FIXTURE_FACTOR: dict[int, float] = {1: 1.20, 2: 1.10, 3: 1.00, 4: 0.90, 5: 0.78}

# Recent form against season-long average. Form moves first and lies more, so
# it gets the smaller share.
FORM_WEIGHT = 0.4
SEASON_WEIGHT = 0.6

POSITIONS: dict[int, str] = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _f(value: Any, default: float = 0.0) -> float:
    """FPL sends numbers as strings about half the time."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class Availability:
    """How likely a player is to be on the pitch, and why."""

    factor: float
    label: str
    note: str = ""


def availability(player: dict[str, Any]) -> Availability:
    """Turn FPL's status flags into one multiplier.

    ``status`` is "a" available, "d" doubtful, "i" injured, "s" suspended,
    "u" unavailable, "n" on loan or ineligible. ``chance_of_playing_next_round``
    is the percentage FPL publishes when there is a doubt, and null when there
    is not — null therefore means *no doubt*, not *unknown*, which is the
    opposite of how it reads.
    """
    status = str(player.get("status", "a"))
    if status in {"i", "s", "u", "n"}:
        reason = {"i": "injured", "s": "suspended", "u": "unavailable", "n": "ineligible"}[status]
        return Availability(0.0, "out", reason)

    chance = player.get("chance_of_playing_next_round")
    if chance is not None:
        pct = _f(chance) / 100
        if pct <= 0:
            return Availability(0.0, "out", "ruled out")
        if pct < 1:
            return Availability(pct, "doubt", f"{int(pct * 100)}% chance of playing")

    # Fit, but a fit substitute is still not a starter. Starts per appearance
    # is the honest discount.
    minutes = _f(player.get("minutes"))
    starts = _f(player.get("starts"))
    if minutes <= 0:
        return Availability(0.35, "unproven", "no minutes yet this season")
    appearances = max(1.0, minutes / 90)
    share = min(1.0, starts / appearances) if appearances else 1.0
    if share < 0.5:
        return Availability(max(0.35, share), "rotation", "started fewer than half their appearances")
    return Availability(min(1.0, 0.6 + 0.4 * share), "fit", "")


@dataclass(frozen=True, slots=True)
class Forecast:
    element: int
    name: str
    club: str
    position: str
    price: float
    expected_points: float
    appearances: int
    confident: bool
    availability: str
    difficulty: int
    # "observed" once there is a real sample, "blended" while shrinking toward
    # the prior, "prior" when the player has not kicked a ball this season.
    basis: str = "observed"
    reasons: list[str] = field(default_factory=list)


def appearances_of(player: dict[str, Any]) -> int:
    """Whole matches' worth of minutes, which is the sample the mean rests on."""
    return int(_f(player.get("minutes")) // 90)


def base_points(player: dict[str, Any]) -> float:
    """Blend of season average and recent form, both per appearance."""
    ppg = _f(player.get("points_per_game"))
    form = _f(player.get("form"))
    if form <= 0:
        return ppg
    if ppg <= 0:
        return form
    return SEASON_WEIGHT * ppg + FORM_WEIGHT * form


def forecast(
    player: dict[str, Any],
    difficulty: int,
    club_short: str,
) -> Forecast:
    """One player, one gameweek.

    Two estimates are combined. The *observed* one is the player's own scoring
    rate scaled by how hard this week's fixture is. The *prior* is FPL's own
    published expectation for the round, which already accounts for the
    fixture -- so the difficulty factor is applied to the observed half only,
    or it would be counted twice.
    """
    avail = availability(player)
    apps = appearances_of(player)
    factor = FIXTURE_FACTOR.get(difficulty, 1.0)

    observed_xp = base_points(player) * factor
    prior_xp = _f(player.get("ep_next"))

    if prior_xp > 0:
        weight = apps / (apps + SHRINKAGE_K)
        blended = weight * observed_xp + (1 - weight) * prior_xp
        basis = "observed" if apps >= MIN_APPEARANCES else ("blended" if apps else "prior")
    else:
        blended = observed_xp
        basis = "observed" if apps >= MIN_APPEARANCES else "thin"

    xp = blended * avail.factor

    reasons: list[str] = []
    if avail.note:
        reasons.append(avail.note)
    if difficulty <= 2:
        reasons.append(f"kind fixture (difficulty {difficulty})")
    elif difficulty >= 4:
        reasons.append(f"hard fixture (difficulty {difficulty})")
    if basis == "prior":
        reasons.append("no minutes yet, so this is the league's own expectation")
    elif basis == "blended":
        reasons.append(f"only {apps} full match{'es' if apps != 1 else ''} played, so partly an estimate")
    elif basis == "thin":
        reasons.append("too little to go on")

    return Forecast(
        element=int(player.get("id", 0)),
        name=str(player.get("web_name", "")),
        club=club_short,
        position=POSITIONS.get(int(player.get("element_type", 0)), "?"),
        price=_f(player.get("now_cost")) / 10,
        expected_points=round(xp, 2),
        appearances=apps,
        confident=apps >= MIN_APPEARANCES,
        availability=avail.label,
        difficulty=difficulty,
        basis=basis,
        reasons=reasons,
    )


# --------------------------------------------------------------------------
# Fixture difficulty
# --------------------------------------------------------------------------


def difficulty_by_club(fixtures: Sequence[dict[str, Any]], gameweek: int, horizon: int = 1) -> dict[int, int]:
    """Mean upcoming difficulty per FPL club id, over ``horizon`` gameweeks.

    A club with no fixture in the window — a blank — gets 5, the hardest
    value, because a player who is not playing scores nothing and that is
    strictly worse than a difficult match.
    """
    window = range(gameweek, gameweek + horizon)
    per_club: dict[int, list[int]] = {}
    for row in fixtures:
        event = row.get("event")
        if event is None or int(event) not in window:
            continue
        home, away = row.get("team_h"), row.get("team_a")
        if home is None or away is None:
            continue
        per_club.setdefault(int(home), []).append(int(row.get("team_h_difficulty") or 3))
        per_club.setdefault(int(away), []).append(int(row.get("team_a_difficulty") or 3))

    return {club: round(sum(v) / len(v)) if v else 5 for club, v in per_club.items()}


# --------------------------------------------------------------------------
# Captaincy
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CaptainPick:
    forecast: Forecast
    doubled: float
    rank: int


def captain_options(squad_forecasts: Sequence[Forecast], top: int = 3) -> list[CaptainPick]:
    """The armband candidates, best first.

    Anybody with a usable estimate and a pulse. "Usable" excludes the player
    the model has nothing at all on -- no minutes *and* no published prior --
    because a zero there means "unknown", not "will score nothing".
    """
    eligible = [
        f for f in squad_forecasts if f.availability != "out" and f.basis != "thin" and f.expected_points > 0
    ]
    ranked = sorted(eligible, key=lambda f: (-f.expected_points, f.name))
    return [
        CaptainPick(forecast=f, doubled=round(f.expected_points * 2, 2), rank=i + 1)
        for i, f in enumerate(ranked[:top])
    ]


# --------------------------------------------------------------------------
# Transfers
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TransferIdea:
    out_player: Forecast
    in_player: Forecast
    gain: float
    affordable: bool
    reasoning: list[str]


def transfer_ideas(
    squad: Sequence[Forecast],
    market: Sequence[Forecast],
    bank: float,
    limit: int = 3,
) -> list[TransferIdea]:
    """Weakest links, and who to replace them with.

    Only compares like for like: FPL requires a legal formation, so a
    midfielder can only become a midfielder. The replacement has to be
    affordable out of the selling price plus whatever is in the bank, has to
    have enough appearances to be judged, and has to actually be projected
    higher — a sideways move dressed as advice is worse than silence.
    """
    owned = {f.element for f in squad}
    by_position: dict[str, list[Forecast]] = {}
    for candidate in market:
        if candidate.element in owned or candidate.basis == "thin":
            continue
        if candidate.availability == "out" or candidate.expected_points <= 0:
            continue
        by_position.setdefault(candidate.position, []).append(candidate)
    for group in by_position.values():
        group.sort(key=lambda f: -f.expected_points)

    ideas: list[TransferIdea] = []
    # Worst first.
    for out_player in sorted(squad, key=lambda f: f.expected_points):
        budget = out_player.price + bank
        for candidate in by_position.get(out_player.position, []):
            if candidate.price > budget + 1e-9:
                continue
            gain = round(candidate.expected_points - out_player.expected_points, 2)
            if gain <= 0:
                break  # sorted by xP, so nothing further down will beat it either
            reasoning = _explain(out_player, candidate, gain)
            ideas.append(
                TransferIdea(
                    out_player=out_player,
                    in_player=candidate,
                    gain=gain,
                    affordable=True,
                    reasoning=reasoning,
                )
            )
            break
        if len(ideas) >= limit:
            break
    return ideas


def _explain(out_player: Forecast, in_player: Forecast, gain: float) -> list[str]:
    """Say why, in sentences a person would actually use.

    The brief asks for the reasoning rather than just the name, and a
    recommendation you cannot argue with is one you cannot trust.
    """
    why: list[str] = []
    if in_player.basis != "observed":
        why.append("early season, so this leans on the league's own expectation")
    if out_player.availability == "out":
        why.append(f"{out_player.name} is {out_player.reasons[0] if out_player.reasons else 'unavailable'}")
    elif out_player.availability in {"doubt", "rotation"}:
        why.append(f"{out_player.name} is a {out_player.availability} to start")
    if out_player.difficulty >= 4:
        why.append(f"{out_player.name} faces difficulty {out_player.difficulty}")
    if in_player.difficulty <= 2:
        why.append(f"{in_player.name} has difficulty {in_player.difficulty}")
    if in_player.price < out_player.price:
        why.append(f"frees £{round(out_player.price - in_player.price, 1)}m")
    why.append(f"about {gain} points better this round")
    return why


# --------------------------------------------------------------------------
# How each manager is actually doing
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ManagerReport:
    person: str
    live_points: int
    bench_points: int
    bench_wasted: int
    captain: str | None
    captain_points: int
    best_captain: str | None
    best_captain_points: int
    captain_cost: int
    players_to_play: int
    verdict: str


def manager_report(squad: dict[str, Any]) -> ManagerReport:
    """What this manager got right and wrong this round.

    Two avoidable losses are separated out, because they are the two a manager
    actually controls: points sitting on the bench, and the difference between
    the armband they used and the best one available inside their own squad.
    Neither is hindsight-free advice — both are simply what happened.
    """
    starting = squad.get("starting") or []
    bench_counts = bool(squad.get("bench_counts"))
    bench_points = int(squad.get("bench_points") or 0)

    captain = squad.get("captain") or None
    captain_name = str(captain.get("name")) if captain else None
    # The multiplier is already applied in live_points; the raw score is what
    # the player themselves earned.
    captain_raw = int(captain.get("points") or 0) if captain else 0
    multiplier = int(captain.get("multiplier") or 2) if captain else 2

    best = max(starting, key=lambda p: int(p.get("points") or 0), default=None)
    best_name = str(best.get("name")) if best else None
    best_raw = int(best.get("points") or 0) if best else 0

    # What a perfect armband would have added, over what this one did.
    captain_cost = max(0, (best_raw - captain_raw) * (multiplier - 1))
    wasted = 0 if bench_counts else bench_points

    if wasted == 0 and captain_cost == 0:
        verdict = "Nothing left on the table."
    elif captain_cost >= wasted:
        verdict = f"The armband cost {captain_cost}."
    else:
        verdict = f"{wasted} left on the bench."

    return ManagerReport(
        person=str(squad.get("person") or squad.get("entry_name") or "?"),
        live_points=int(squad.get("live_points") or 0),
        bench_points=bench_points,
        bench_wasted=wasted,
        captain=captain_name,
        captain_points=captain_raw * multiplier,
        best_captain=best_name,
        best_captain_points=best_raw * multiplier,
        captain_cost=captain_cost,
        players_to_play=int(squad.get("players_to_play") or 0),
        verdict=verdict,
    )


def worst_managed(reports: Sequence[ManagerReport]) -> ManagerReport | None:
    """Whoever left the most on the table this round.

    Deliberately *not* whoever scored fewest. A low score can be bad luck; the
    bench and the armband are decisions, and those are the only two things
    this can fairly call somebody out for.
    """
    scored = [r for r in reports if r.bench_wasted or r.captain_cost]
    if not scored:
        return None
    return max(scored, key=lambda r: (r.bench_wasted + r.captain_cost, r.person))
