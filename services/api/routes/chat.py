"""The group's own record: quotes, a weekly poll, settled bets, a timeline.

None of this needs an upstream, so it works with nothing configured. Everything
is persisted, because the point of a quote pinned to a match is that it can be
resurfaced months later.

Every mutation resolves the person from the session. Nothing trusts a `who`
field, here least of all — a scoreboard nobody can forge is the whole appeal of
a bets ledger with no money in it.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from shared.db import Bet, Person, Poll, PollVote, Quote
from shared.models import (
    BetIn,
    BetOut,
    BetsOut,
    PollOptionOut,
    PollOut,
    PollsOut,
    QuoteIn,
    QuoteOut,
    SettleBetIn,
    TimelineEntryOut,
    TimelineOut,
    VoteIn,
)
from shared.timezones import BY_KEY
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth import require_csrf
from services.api.deps import CurrentSession, Db
from services.api.repository import ensure_people, load_predictions

log = structlog.get_logger(__name__)
router = APIRouter(tags=["chat"])

QUOTE_LIMIT = 100


async def _people_by_id(db: AsyncSession) -> dict[int, str]:
    rows = (await db.execute(select(Person.id, Person.key))).all()
    return {int(pid): str(key) for pid, key in rows}


# --------------------------------------------------------------------------
# Quotes
# --------------------------------------------------------------------------


@router.get("/api/chat/quotes", response_model=list[QuoteOut])
async def quotes(_: CurrentSession, db: Db) -> list[QuoteOut]:
    names = await _people_by_id(db)
    rows = (await db.scalars(select(Quote).order_by(Quote.created_at.desc()).limit(QUOTE_LIMIT))).all()
    return [
        QuoteOut(
            id=q.id,
            person=names.get(q.person_id, "unknown"),
            body=q.body,
            subject_type=q.subject_type,
            subject_id=q.subject_id,
            created_at=q.created_at,
        )
        for q in rows
    ]


@router.post(
    "/api/chat/quotes",
    response_model=QuoteOut,
    dependencies=[Depends(require_csrf)],
)
async def add_quote(body: QuoteIn, session: CurrentSession, db: Db) -> QuoteOut:
    people = await ensure_people(db)
    quote = Quote(
        person_id=people[session.person],
        body=body.body.strip(),
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        created_at=datetime.now(UTC),
    )
    db.add(quote)
    await db.flush()
    log.info("chat.quote_added", person=session.person)
    return QuoteOut(
        id=quote.id,
        person=session.person,
        body=quote.body,
        subject_type=quote.subject_type,
        subject_id=quote.subject_id,
        created_at=quote.created_at,
    )


# --------------------------------------------------------------------------
# Poll
# --------------------------------------------------------------------------


def _poll_out(poll: Poll, votes: list[PollVote], names: dict[int, str], me: str) -> PollOut:
    now = datetime.now(UTC)
    counts: Counter[str] = Counter(v.choice for v in votes)
    voters: dict[str, list[str]] = {}
    for vote in votes:
        voters.setdefault(vote.choice, []).append(names.get(vote.person_id, "?"))

    options = [
        PollOptionOut(choice=str(c), votes=counts.get(str(c), 0), voters=voters.get(str(c), []))
        for c in (poll.options or [])
    ]
    mine = next((v.choice for v in votes if names.get(v.person_id) == me), None)

    opens = poll.opens_at if poll.opens_at.tzinfo else poll.opens_at.replace(tzinfo=UTC)
    closes = poll.closes_at if poll.closes_at.tzinfo else poll.closes_at.replace(tzinfo=UTC)

    return PollOut(
        id=poll.id,
        question=poll.question,
        options=options,
        opens_at=opens,
        closes_at=closes,
        open=opens <= now < closes,
        my_vote=mine,
        total_votes=len(votes),
    )


@router.get("/api/chat/poll", response_model=PollsOut)
async def poll(session: CurrentSession, db: Db) -> PollsOut:
    names = await _people_by_id(db)
    polls = (await db.scalars(select(Poll).order_by(Poll.opens_at.desc()))).all()
    if not polls:
        return PollsOut(empty_message="No poll yet. One opens each week and is archived for ever after.")

    all_votes = (await db.scalars(select(PollVote))).all()
    by_poll: dict[int, list[PollVote]] = {}
    for vote in all_votes:
        by_poll.setdefault(vote.poll_id, []).append(vote)

    rendered = [_poll_out(p, by_poll.get(p.id, []), names, session.person) for p in polls]
    current = next((p for p in rendered if p.open), None)
    return PollsOut(
        current=current,
        archive=[p for p in rendered if p is not current],
    )


@router.post("/api/chat/poll", response_model=PollOut, dependencies=[Depends(require_csrf)])
async def vote(body: VoteIn, session: CurrentSession, db: Db) -> PollOut:
    poll_row = await db.get(Poll, body.poll_id)
    if poll_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such poll.")

    closes = poll_row.closes_at if poll_row.closes_at.tzinfo else poll_row.closes_at.replace(tzinfo=UTC)
    if datetime.now(UTC) >= closes:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="That poll has closed.")

    if body.choice not in (poll_row.options or []):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Not one of the options.")

    people = await ensure_people(db)
    person_id = people[session.person]

    existing = await db.scalar(
        select(PollVote).where(PollVote.poll_id == body.poll_id, PollVote.person_id == person_id)
    )
    if existing is not None:
        existing.choice = body.choice  # changing your mind is allowed while open
        existing.voted_at = datetime.now(UTC)
    else:
        db.add(
            PollVote(
                poll_id=body.poll_id,
                person_id=person_id,
                choice=body.choice,
                voted_at=datetime.now(UTC),
            )
        )
    await db.flush()

    names = await _people_by_id(db)
    votes = list(await db.scalars(select(PollVote).where(PollVote.poll_id == body.poll_id)))
    return _poll_out(poll_row, votes, names, session.person)


# --------------------------------------------------------------------------
# Bets
# --------------------------------------------------------------------------


@router.get("/api/chat/bets", response_model=BetsOut)
async def bets(_: CurrentSession, db: Db) -> BetsOut:
    names = await _people_by_id(db)
    rows = (await db.scalars(select(Bet).order_by(Bet.created_at.desc()))).all()

    out = [
        BetOut(
            id=b.id,
            proposer=names.get(b.proposer_id, "?"),
            opponent=names.get(b.opponent_id, "?"),
            terms=b.terms,
            created_at=b.created_at,
            settled_at=b.settled_at,
            winner=names.get(b.winner_id) if b.winner_id else None,
            settled=b.settled_at is not None,
        )
        for b in rows
    ]

    scoreboard: dict[str, int] = dict.fromkeys(BY_KEY, 0)
    for bet in out:
        if bet.winner:
            scoreboard[bet.winner] = scoreboard.get(bet.winner, 0) + 1

    return BetsOut(
        bets=out,
        scoreboard=scoreboard,
        empty_message=(
            None if out else "No bets yet. No money either — this is only a record of who was right."
        ),
    )


@router.post("/api/chat/bets", response_model=BetOut, dependencies=[Depends(require_csrf)])
async def propose_bet(body: BetIn, session: CurrentSession, db: Db) -> BetOut:
    if body.opponent not in BY_KEY:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such person.")
    if body.opponent == session.person:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="You cannot bet against yourself.")

    people = await ensure_people(db)
    bet = Bet(
        proposer_id=people[session.person],
        opponent_id=people[body.opponent],
        terms=body.terms.strip(),
        created_at=datetime.now(UTC),
    )
    db.add(bet)
    await db.flush()
    log.info("chat.bet_proposed", person=session.person, opponent=body.opponent)
    return BetOut(
        id=bet.id,
        proposer=session.person,
        opponent=body.opponent,
        terms=bet.terms,
        created_at=bet.created_at,
        settled=False,
    )


@router.put("/api/chat/bets", response_model=BetOut, dependencies=[Depends(require_csrf)])
async def settle_bet(body: SettleBetIn, session: CurrentSession, db: Db) -> BetOut:
    bet = await db.get(Bet, body.bet_id)
    if bet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such bet.")
    if bet.settled_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="That bet is already settled.")

    names = await _people_by_id(db)
    people = await ensure_people(db)

    # Only the two people involved may settle it, and only in favour of one of
    # them -- otherwise the scoreboard means nothing.
    involved = {names.get(bet.proposer_id), names.get(bet.opponent_id)}
    if session.person not in involved:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the two of you can settle it.")
    if body.winner not in involved:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="The winner must be one of the two."
        )

    bet.winner_id = people[body.winner]
    bet.settled_at = datetime.now(UTC)
    await db.flush()
    log.info("chat.bet_settled", person=session.person, winner=body.winner)

    return BetOut(
        id=bet.id,
        proposer=names.get(bet.proposer_id, "?"),
        opponent=names.get(bet.opponent_id, "?"),
        terms=bet.terms,
        created_at=bet.created_at,
        settled_at=bet.settled_at,
        winner=body.winner,
        settled=True,
    )


# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------


@router.get("/api/timeline", response_model=TimelineOut)
async def timeline(_: CurrentSession, db: Db) -> TimelineOut:
    """Every vote, quote, bet and prediction in one feed, newest first."""
    names = await _people_by_id(db)
    entries: list[TimelineEntryOut] = []

    for quote in await db.scalars(select(Quote)):
        entries.append(
            TimelineEntryOut(
                kind="quote",
                at=quote.created_at,
                person=names.get(quote.person_id),
                title="Quote",
                detail=quote.body[:160],
            )
        )

    for bet in await db.scalars(select(Bet)):
        entries.append(
            TimelineEntryOut(
                kind="bet",
                at=bet.created_at,
                person=names.get(bet.proposer_id),
                title=f"Bet with {names.get(bet.opponent_id, '?').upper()}",
                detail=bet.terms[:160],
            )
        )
        if bet.settled_at and bet.winner_id:
            entries.append(
                TimelineEntryOut(
                    kind="bet-settled",
                    at=bet.settled_at,
                    person=names.get(bet.winner_id),
                    title="Bet settled",
                    detail=f"{names.get(bet.winner_id, '?').upper()} was right: {bet.terms[:120]}",
                )
            )

    stored = await load_predictions(db)
    for person, record in stored.items():
        submitted = record.get("submitted_at")
        if not submitted:
            continue
        entries.append(
            TimelineEntryOut(
                kind="prediction",
                at=datetime.fromisoformat(str(submitted).replace("Z", "+00:00")),
                person=person,
                title="Prediction filed",
                detail=f"{record['table'][0]} to win it, {record['table'][-1]} bottom",
            )
        )

    entries.sort(key=lambda e: e.at, reverse=True)
    return TimelineOut(
        entries=entries,
        empty_message=(None if entries else "The feed fills up as quotes, bets and votes are added."),
    )


def default_poll(question: str, options: list[str], days: int = 7) -> dict[str, Any]:
    """Shape for a weekly poll, used by the scheduler and by seeding."""
    now = datetime.now(UTC)
    return {
        "question": question,
        "options": options,
        "opens_at": now,
        "closes_at": now + timedelta(days=days),
    }
