"""Postgres schema, as SQLAlchemy 2.0 typed ORM models.

Shape follows BRIEF section 9. Timestamps are ``timestamptz`` stored in UTC and
converted at the edge -- with one deliberate exception: ``watch_log.local_hour``
is written at insert time in the person's own zone, so the night medal stays
correct for ever even if a government later changes that zone's rules. Alberta
does exactly that on 1 November 2026, mid-season, which is why the column exists.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base. ``JSON`` is portable across Postgres and SQLite."""

    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSON, list[Any]: JSON}


def _ts(**kw: Any) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), **kw)


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(32))
    city: Mapped[str] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64))
    country: Mapped[str] = mapped_column(String(2))
    # The code word is never stored in plaintext; comparison at login is
    # constant-time against the environment secret.
    code_hash: Mapped[str] = mapped_column(String(128), default="")
    fpl_entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    push_subscription: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    predictions: Mapped[list[Prediction]] = relationship(back_populates="person")


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("person_id", "kind", name="uq_prediction_person_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # 'table' | 'awards' | 'cl'
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    submitted_at: Mapped[datetime | None] = _ts(nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False)

    person: Mapped[Person] = relationship(back_populates="predictions")


class TableSnapshot(Base):
    __tablename__ = "table_snapshots"
    __table_args__ = (Index("ix_table_snapshots_captured", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    captured_at: Mapped[datetime] = _ts(index=True)
    gameweek: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class LeaderboardRun(Base):
    __tablename__ = "leaderboard_runs"
    __table_args__ = (Index("ix_leaderboard_runs_gw_person", "gameweek", "person_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    computed_at: Mapped[datetime] = _ts(index=True)
    gameweek: Mapped[int] = mapped_column(Integer)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    table_pts: Mapped[int] = mapped_column(Integer, default=0)
    award_pts: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[int] = mapped_column(Integer, default=0)


class WatchLog(Base):
    __tablename__ = "watch_log"
    __table_args__ = (
        UniqueConstraint("person_id", "fixture_id", name="uq_watch_person_fixture"),
        Index("ix_watch_log_person_fixture", "person_id", "fixture_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    fixture_id: Mapped[int] = mapped_column(Integer, index=True)
    watched_at: Mapped[datetime] = _ts()
    gameweek: Mapped[int] = mapped_column(Integer, default=0)
    # Written in the person's own zone at insert time, never recomputed.
    local_hour: Mapped[int] = mapped_column(Integer)
    night_medal: Mapped[bool] = mapped_column(Boolean, default=False)


class OddsHistory(Base):
    __tablename__ = "odds_history"
    __table_args__ = (Index("ix_odds_history_fixture_time", "fixture_id", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(Integer, index=True)
    captured_at: Mapped[datetime] = _ts()
    home: Mapped[float] = mapped_column()
    draw: Mapped[float] = mapped_column()
    away: Mapped[float] = mapped_column()
    bookmaker: Mapped[str] = mapped_column(String(32), default="bet365")


class FplSnapshot(Base):
    __tablename__ = "fpl_snapshots"
    __table_args__ = (Index("ix_fpl_snapshots_gw_person", "gameweek", "person_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    gameweek: Mapped[int] = mapped_column(Integer)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    entry_id: Mapped[int] = mapped_column(Integer, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    captured_at: Mapped[datetime] = _ts()


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    body: Mapped[str] = mapped_column(Text)
    subject_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = _ts(index=True)


class Poll(Base):
    __tablename__ = "polls"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[list[Any]] = mapped_column(JSON, default=list)
    opens_at: Mapped[datetime] = _ts()
    closes_at: Mapped[datetime] = _ts()


class PollVote(Base):
    __tablename__ = "poll_votes"
    __table_args__ = (UniqueConstraint("poll_id", "person_id", name="uq_vote_poll_person"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    choice: Mapped[str] = mapped_column(String(128))
    voted_at: Mapped[datetime] = _ts()


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[int] = mapped_column(primary_key=True)
    proposer_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    opponent_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    terms: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    settled_at: Mapped[datetime | None] = _ts(nullable=True)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"), nullable=True)


class Moment(Base):
    __tablename__ = "moments"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    r2_key: Mapped[str] = mapped_column(String(256))
    caption: Mapped[str] = mapped_column(Text, default="")
    content_type: Mapped[str] = mapped_column(String(64), default="image/jpeg")
    created_at: Mapped[datetime] = _ts(index=True)


class Broadcaster(Base):
    """Where to watch, per country and competition. Editable from /admin."""

    __tablename__ = "broadcasters"
    __table_args__ = (UniqueConstraint("country", "competition", name="uq_broadcaster_country_comp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    competition: Mapped[str] = mapped_column(String(32), default="premier-league")
    provider: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(256), default="")
    verified_on: Mapped[str] = mapped_column(String(10), default="")
    note: Mapped[str] = mapped_column(Text, default="")


class UpstreamCall(Base):
    """Every upstream request, so /admin shows real consumption not an estimate."""

    __tablename__ = "upstream_calls"
    __table_args__ = (Index("ix_upstream_calls_source_time", "source", "called_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    endpoint: Mapped[str] = mapped_column(String(128))
    called_at: Mapped[datetime] = _ts()
    status: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    quota_remaining: Mapped[str] = mapped_column(String(32), default="")
    ok: Mapped[bool] = mapped_column(Boolean, default=True)


class CronRun(Base):
    """Cron job log, rendered on /admin."""

    __tablename__ = "cron_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = _ts()
    finished_at: Mapped[datetime | None] = _ts(nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    detail: Mapped[str] = mapped_column(Text, default="")
