"""News: Sky headlines, YouTube uploads, Athletic links.

Each source degrades on its own. Sky needs no key and works everywhere; YouTube
needs one and says so without it; The Athletic is reported as unavailable rather
than scraped, because it is paywalled and the brief permits headlines and links
only, never mirrored text.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from shared import keys
from shared.config import Settings
from shared.models import NewsItemOut, NewsOut

from services.api import views
from services.api.deps import Config, CurrentSession, State

router = APIRouter(tags=["news"])


@router.get("/api/news", response_model=NewsOut)
async def news(_: CurrentSession, state: State, settings: Config) -> NewsOut:
    entry = await state.cache.get(keys.NEWS_SKY)
    payload: dict[str, Any] = entry.value if entry else {}

    sky = [
        NewsItemOut(
            title=str(row.get("title", "")),
            url=str(row.get("url", "")),
            source=str(row.get("source", "Sky Sports")),
            published=row.get("published"),
            summary=str(row.get("summary", "")),
        )
        for row in payload.get("sky", [])
    ]

    return NewsOut(
        sky=sky,
        youtube=[
            NewsItemOut(
                title=str(row.get("title", "")),
                url=str(row.get("url", "")),
                source=str(row.get("source", "YouTube")),
                published=row.get("published"),
                summary=str(row.get("summary", "")),
            )
            for row in payload.get("youtube", [])
        ],
        athletic=[],
        freshness=views.freshness(entry, keys.NEWS_SKY),
        empty_message=(None if sky else "Headlines appear once the poller has read the Sky feed."),
        youtube_message=_youtube_message(settings),
        sources=list(payload.get("sources", [])),
        athletic_message=(
            "Headlines come from Sky Sports, BBC Sport and the Guardian — all "
            "free, public feeds. The Athletic is not included: it has no public "
            "feed and its articles are paywalled, and scraping one to fill a "
            "panel is not a trade worth making."
        ),
    )


def _youtube_message(settings: Settings) -> str:
    if not settings.youtube_api_key:
        return (
            "Video uploads need YOUTUBE_API_KEY. Set it and the six channels "
            "resolve at next poll; nothing else on the site is affected."
        )
    return "No uploads fetched yet."
