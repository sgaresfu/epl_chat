"""News sources.

Sky Sports publishes RSS, which needs no key and no quota -- so the news panel
works on a clean clone with nothing configured. YouTube needs a key and degrades
to a clear message without one.

The Athletic is deliberately not scraped. It has no public feed, its content is
paywalled, and the brief is explicit that only headlines and links may be shown
and never mirrored. Rather than scrape a paywalled site, that panel reports the
gap honestly until a licensed source exists.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import structlog

from services.poller.http import Upstream, UpstreamError

log = structlog.get_logger(__name__)

# Sky Sports' Premier League feed. 12040 is the wider sports feed.
SKY_PREMIER_LEAGUE = "https://www.skysports.com/rss/11661"

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"

# BRIEF section 6. Channel ids are resolved via the API at setup and stored;
# none are hardcoded here, because an unverified id silently returns somebody
# else's uploads.
CHANNELS: tuple[str, ...] = (
    "The Overlap",
    "The Rest Is Football",
    "Sky Sports Premier League",
    "Premier League",
    "Let's Talk FPL",
    "Єврофутбол",
)


@dataclass(frozen=True, slots=True)
class Item:
    title: str
    url: str
    source: str
    published: str | None = None
    summary: str = ""


def sky_client() -> Upstream:
    return Upstream(name="sky-rss", base_url="https://www.skysports.com")


_TAG = re.compile(r"<[^>]+>")

# RFC 2822 defines only a handful of alphabetic zones, and BST is not among
# them -- ``parsedate_to_datetime`` returns a *naive* datetime for it. Calling
# ``astimezone`` on that silently reinterprets the time as the server's own
# local zone, so every Sky headline would be off by whatever the host happens
# to be set to. Sky stamps its entire feed in BST, so this is every item.
_ZONES: dict[str, int] = {
    "GMT": 0,
    "UT": 0,
    "UTC": 0,
    "Z": 0,
    "BST": 3600,  # British Summer Time, which is what Sky publishes
    "IST": 3600,  # Irish Standard Time
    "CET": 3600,
    "CEST": 7200,
    "EST": -18000,
    "EDT": -14400,
    "CST": -21600,
    "CDT": -18000,
    "MST": -25200,
    "MDT": -21600,
    "PST": -28800,
    "PDT": -25200,
}


def parse_date(raw: str) -> datetime | None:
    """Parse an RSS date to a UTC instant, or ``None``.

    A naive result is treated as UTC rather than as the host's local time --
    guessing the server's zone is how a feed's timestamps drift by an hour, or
    by three.
    """
    if not raw:
        return None

    trailing = raw.strip().rsplit(" ", 1)[-1].upper()
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        offset = _ZONES.get(trailing)
        if offset is None:
            log.debug("news.unknown_timezone", value=trailing)
            offset = 0
        parsed = parsed.replace(tzinfo=timezone(timedelta(seconds=offset)))

    return parsed.astimezone(UTC)


def _text(raw: str) -> str:
    """Strip tags and CDATA from an RSS field."""
    cleaned = raw.replace("<![CDATA[", "").replace("]]>", "")
    return _TAG.sub("", cleaned).strip()


def parse_rss(xml: str, source: str, limit: int = 20) -> list[Item]:
    """Parse an RSS 2.0 feed.

    Deliberately tolerant: a feed that changes shape should drop the item it
    cannot read, not the whole panel.
    """
    items: list[Item] = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)[:limit]:

        def field(name: str, text: str = block) -> str:
            match = re.search(rf"<{name}[^>]*>(.*?)</{name}>", text, re.DOTALL)
            return _text(match.group(1)) if match else ""

        title, link = field("title"), field("link")
        if not title or not link:
            continue

        moment = parse_date(field("pubDate"))
        iso = moment.isoformat() if moment else None

        items.append(
            Item(
                title=title,
                url=link,
                source=source,
                published=iso,
                summary=field("description")[:280],
            )
        )
    return items


async def fetch_sky(up: Upstream) -> list[Item]:
    """Sky Sports' Premier League headlines. No key, no quota."""
    xml = await up.get_text("/rss/11661")
    items = parse_rss(xml, source="Sky Sports")
    log.info("news.sky_fetched", count=len(items))
    return items


def youtube_client(api_key: str) -> Upstream:
    return Upstream(name="youtube", base_url=YOUTUBE_API, headers={})


async def resolve_channel(up: Upstream, api_key: str, name: str) -> list[dict[str, str]]:
    """Find candidate channel ids for a name.

    Returns every plausible match rather than picking one. The brief is explicit
    that an unverified id must not be hardcoded, and for Єврофутбол in particular
    several channels may match -- those candidates belong in the README for a
    human to choose, not in a guess.
    """
    payload = await up.get_json(
        "/search",
        params={"part": "snippet", "type": "channel", "q": name, "maxResults": 5, "key": api_key},
    )
    return [
        {
            "channel_id": row["snippet"]["channelId"],
            "title": row["snippet"]["title"],
            "description": row["snippet"].get("description", "")[:160],
        }
        for row in payload.get("items", [])
    ]


async def fetch_uploads(up: Upstream, api_key: str, channel_id: str, limit: int = 5) -> list[Item]:
    """Recent uploads for a stored channel id."""
    payload = await up.get_json(
        "/search",
        params={
            "part": "snippet",
            "channelId": channel_id,
            "order": "date",
            "type": "video",
            "maxResults": limit,
            "key": api_key,
        },
    )
    items: list[Item] = []
    for row in payload.get("items", []):
        video_id = row.get("id", {}).get("videoId")
        if not video_id:
            continue
        snippet = row["snippet"]
        items.append(
            Item(
                title=snippet["title"],
                url=f"https://www.youtube.com/watch?v={video_id}",
                source=snippet.get("channelTitle", "YouTube"),
                published=snippet.get("publishedAt"),
            )
        )
    return items


async def poll_news(up: Upstream) -> dict[str, Any]:
    """The whole news payload, degrading per source rather than as a whole."""
    out: dict[str, Any] = {"sky": [], "youtube": [], "athletic": [], "errors": {}}
    try:
        # asdict, not __dict__: Item is a slots dataclass and has no __dict__.
        out["sky"] = [asdict(item) for item in await fetch_sky(up)]
    except UpstreamError as exc:
        out["errors"]["sky"] = str(exc)
        log.warning("news.sky_failed", error=str(exc))
    out["fetched_at"] = datetime.now(UTC).isoformat()
    return out
