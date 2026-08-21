"""Pydantic v2 models for every API boundary.

FastAPI generates the OpenAPI schema from these, and the frontend's TypeScript
types are generated from that schema with ``openapi-typescript``, so the two
sides cannot drift. Nothing here is hand-mirrored in TypeScript.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    """Base for every request and response model.

    ``json_schema_serialization_defaults_required`` is the setting that makes
    the published contract honest. Without it, any field carrying a default is
    marked optional in the OpenAPI schema -- so ``Freshness.available``, which
    the api sends on every single response, is typed as possibly-absent on the
    client. FastAPI always serialises these fields, so declaring them required
    in the *serialization* schema describes what actually goes over the wire,
    and lets the generated TypeScript be checked against the hand-written types
    rather than being uselessly permissive.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_serialization_defaults_required=True,
    )


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------


class PersonOut(Model):
    key: str
    name: str
    city: str
    timezone: str
    country: str
    fpl_entry_id: int | None = None


class MeOut(Model):
    person: PersonOut
    people: list[PersonOut]
    season: str
    prediction_lock: datetime
    locked: bool
    server_time: datetime


class LoginIn(Model):
    code: str = Field(min_length=1, max_length=64)


# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


class ClubOut(Model):
    """A club, with everything a crest needs and nothing it does not."""

    short_name: str
    name: str
    full_name: str
    primary: str
    on_primary: str
    fpl_id: int


class Freshness(Model):
    """How old a cached payload is, so a panel can say so rather than lie."""

    source: str
    age_seconds: float
    stale: bool
    available: bool = True
    reason: str | None = None


class LocalTimeOut(Model):
    """One kickoff rendered for one city."""

    place: str
    person: str
    city: str
    timezone: str
    iso: datetime
    time: str
    weekday: str
    day: str
    offset: str
    abbreviation: str
    is_night: bool
    day_shift: int
    broadcaster: str | None = None
    broadcaster_url: str | None = None
    verified_on: str | None = None


# --------------------------------------------------------------------------
# Table
# --------------------------------------------------------------------------


class TableRowOut(Model):
    position: int
    club: ClubOut
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    form: list[str] = Field(default_factory=list)
    modelled: bool = False
    note: str | None = None


class TableOut(Model):
    rows: list[TableRowOut]
    gameweek: int
    matches_played: int
    season_started: bool
    freshness: Freshness
    empty_message: str | None = None


class ProjectedTableOut(TableOut):
    modelled_rows: list[str] = Field(default_factory=list)
    method: str = ""


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


class OddsPrice(Model):
    home: float | None = None
    draw: float | None = None
    away: float | None = None
    bookmaker: str = "bet365"
    captured_at: datetime | None = None
    drift: dict[str, float] | None = None
    available: bool = True
    reason: str | None = None


class FixtureOut(Model):
    id: int
    gameweek: int
    kickoff: datetime | None
    home: ClubOut
    away: ClubOut
    home_score: int | None = None
    away_score: int | None = None
    started: bool = False
    finished: bool = False
    postponed: bool = False
    minutes: int = 0
    local_times: list[LocalTimeOut] = Field(default_factory=list)
    odds: OddsPrice | None = None
    derby: str | None = None
    watched_by: list[str] = Field(default_factory=list)
    watch_open: bool = False


class FixtureListOut(Model):
    fixtures: list[FixtureOut]
    freshness: Freshness
    empty_message: str | None = None


# --------------------------------------------------------------------------
# Predictions
# --------------------------------------------------------------------------


class AwardPicks(Model):
    golden_boot: str = ""
    golden_glove: str = ""
    defender: str = ""
    playmaker: str = ""
    player_of_the_season: str = ""


class ChampionsLeaguePicks(Model):
    winner: str = ""
    finalist_a: str = ""
    finalist_b: str = ""
    top_scorer: str = ""
    draft: bool = False


class PredictionIn(Model):
    table: list[str] = Field(default_factory=list)
    awards: AwardPicks = Field(default_factory=AwardPicks)
    champions_league: ChampionsLeaguePicks = Field(default_factory=ChampionsLeaguePicks)


class PredictionOut(Model):
    person: str
    filed: bool
    redacted: bool = False
    table: list[str] = Field(default_factory=list)
    awards: AwardPicks | None = None
    champions_league: ChampionsLeaguePicks | None = None
    submitted_at: datetime | None = None
    locked: bool = False
    status: Literal["filed", "open", "did-not-file"] = "open"


class PredictionsOut(Model):
    predictions: list[PredictionOut]
    locked: bool
    lock_at: datetime
    seconds_remaining: float


class PreviewIn(Model):
    table: list[str]
    awards: AwardPicks | None = None
    against_season: str = "2025-26"


class PreviewOut(Model):
    total: int
    table_points: int
    award_points: int
    exact_hits: int
    near_hits: int
    top_four_bonus: int
    champion_bonus: int
    against_season: str
    per_club: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Leaderboard
# --------------------------------------------------------------------------


class LeaderboardRowOut(Model):
    rank: int
    person: PersonOut
    total: int
    table_points: int
    award_points: int
    exact_hits: int
    filed: bool
    status: str
    movement: int = 0
    cursed_pick: str | None = None
    form: list[int] = Field(default_factory=list)


class H2HAgreement(Model):
    """A club both people placed in the same position."""

    club: ClubOut
    position: int


class H2HGap(Model):
    """A club the two people placed furthest apart."""

    club: ClubOut
    a_position: int
    b_position: int
    distance: int


class H2HOut(Model):
    """Where two people agree, and where they disagree most."""

    a: PersonOut
    b: PersonOut
    agreements: list[H2HAgreement] = Field(default_factory=list)
    gaps: list[H2HGap] = Field(default_factory=list)
    agreement_count: int = 0
    empty_message: str | None = None


class LeaderboardOut(Model):
    rows: list[LeaderboardRowOut]
    leader: str | None = None
    flop_of_the_week: str | None = None
    if_season_ended_today: str | None = None
    freshness: Freshness
    empty_message: str | None = None


# --------------------------------------------------------------------------
# FPL
# --------------------------------------------------------------------------


class FplStandingRow(Model):
    entry_id: int
    entry_name: str
    player_name: str
    person: str | None = None
    rank: int | None = None
    total: int = 0
    event_total: int = 0
    pending: bool = False


class FplStandingsOut(Model):
    league_id: int
    league_name: str
    rows: list[FplStandingRow]
    gameweek: int
    freshness: Freshness
    empty_message: str | None = None
    unmapped: list[int] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Season timeline
# --------------------------------------------------------------------------


class TimelineMarker(Model):
    label: str
    date: datetime
    percent: float
    is_now: bool = False


class SeasonOut(Model):
    """Computed from fixture data and the current date, never hardcoded."""

    starts: datetime
    ends: datetime
    today: datetime
    percent: float
    day: int
    total_days: int
    days_remaining: int
    gameweeks_played: int
    gameweeks_total: int
    matches_played: int
    matches_total: int
    matches_remaining: int
    watched: int
    markers: list[TimelineMarker] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Home
# --------------------------------------------------------------------------


class NextMatchOut(Model):
    fixture: FixtureOut | None = None
    countdown_seconds: float | None = None
    in_play: bool = False
    message: str | None = None


class HomeOut(Model):
    next_match: NextMatchOut
    season: SeasonOut
    line_of_the_day: str | None = None


# --------------------------------------------------------------------------
# Watch log
# --------------------------------------------------------------------------


class WatchToggleIn(Model):
    fixture_id: int


class WatchStatsOut(Model):
    person: str
    watched: int
    total_matches: int
    percent: float
    hours: float
    night_medals: int
    streak: int
    freshness: Freshness


class QuoteOut(Model):
    id: int
    person: str
    body: str
    subject_type: str | None = None
    subject_id: str | None = None
    created_at: datetime


class QuoteIn(Model):
    body: str = Field(min_length=1, max_length=500)
    subject_type: Literal["club", "player", "match"] | None = None
    subject_id: str | None = Field(default=None, max_length=32)


class PollOptionOut(Model):
    choice: str
    votes: int
    voters: list[str] = Field(default_factory=list)


class PollOut(Model):
    id: int
    question: str
    options: list[PollOptionOut] = Field(default_factory=list)
    opens_at: datetime
    closes_at: datetime
    open: bool
    my_vote: str | None = None
    total_votes: int = 0


class PollsOut(Model):
    current: PollOut | None = None
    archive: list[PollOut] = Field(default_factory=list)
    empty_message: str | None = None


class VoteIn(Model):
    poll_id: int
    choice: str = Field(min_length=1, max_length=128)


class BetOut(Model):
    id: int
    proposer: str
    opponent: str
    terms: str
    created_at: datetime
    settled_at: datetime | None = None
    winner: str | None = None
    settled: bool = False


class BetIn(Model):
    opponent: str
    terms: str = Field(min_length=1, max_length=500)


class SettleBetIn(Model):
    bet_id: int
    winner: str


class BetsOut(Model):
    bets: list[BetOut] = Field(default_factory=list)
    scoreboard: dict[str, int] = Field(default_factory=dict)
    empty_message: str | None = None


class TimelineEntryOut(Model):
    kind: str
    at: datetime
    person: str | None = None
    title: str
    detail: str | None = None


class TimelineOut(Model):
    entries: list[TimelineEntryOut] = Field(default_factory=list)
    empty_message: str | None = None


class NewsItemOut(Model):
    title: str
    url: str
    source: str
    published: datetime | None = None
    summary: str = ""


class NewsOut(Model):
    sky: list[NewsItemOut] = Field(default_factory=list)
    youtube: list[NewsItemOut] = Field(default_factory=list)
    athletic: list[NewsItemOut] = Field(default_factory=list)
    freshness: Freshness
    empty_message: str | None = None
    youtube_message: str | None = None
    athletic_message: str | None = None


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------


class CacheAge(Model):
    name: str
    source: str
    age_seconds: float
    stale: bool


class QuotaOut(Model):
    source: str
    used: int
    budget: int
    remaining: int
    window: str
    note: str = ""


class CronRunOut(Model):
    """One scheduler run, as shown in the admin cron log."""

    job: str
    started_at: datetime
    finished_at: datetime | None = None
    ok: bool = True
    detail: str = ""


class AdminStatusOut(Model):
    caches: list[CacheAge]
    quotas: list[QuotaOut]
    cron: list[CronRunOut]
    missing_keys: list[str]
    environment: str


class BroadcasterOut(Model):
    country: str
    competition: str
    provider: str
    url: str = ""
    verified_on: str = ""
    note: str = ""


class ErrorOut(Model):
    detail: str
