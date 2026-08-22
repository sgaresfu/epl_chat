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

import html
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import structlog

from services.poller.http import Upstream, UpstreamError

log = structlog.get_logger(__name__)

# Free, public, key-less Premier League feeds.
#
# The Athletic is deliberately absent: it has no public feed, its articles are
# paywalled, and the brief permits headlines and links only. Scraping a
# paywalled site to fill a panel is not a trade worth making, so these three
# take its place -- all of them full-text-free RSS from major outlets.
FEEDS: tuple[tuple[str, str, str], ...] = (
    ("Sky Sports", "https://www.skysports.com", "/rss/11661"),
    ("BBC Sport", "https://feeds.bbci.co.uk", "/sport/football/premier-league/rss.xml"),
    ("The Guardian", "https://www.theguardian.com", "/football/premierleague/rss"),
)

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"

# BRIEF section 6. Ids were resolved through the API and checked by hand, then
# stored -- an unverified id silently returns somebody else's uploads, and for
# Єврофутбол several channels match the name.
CHANNELS_FILE = Path(__file__).parents[2] / "shared" / "data" / "youtube_channels.json"


def channels() -> list[dict[str, str]]:
    if not CHANNELS_FILE.exists():  # pragma: no cover
        return []
    data = json.loads(CHANNELS_FILE.read_text())
    return list(data.get("channels", []))


@dataclass(frozen=True, slots=True)
class Item:
    title: str
    url: str
    source: str
    published: str | None = None
    summary: str = ""


def sky_client() -> Upstream:
    """Kept for the poller's single shared client; base_url is per-request."""
    return Upstream(name="rss", base_url="https://www.skysports.com")


def feed_clients() -> list[tuple[str, Upstream, str]]:
    """One client per outlet, since they are different hosts."""
    return [(name, Upstream(name=f"rss:{name}", base_url=base), path) for name, base, path in FEEDS]


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
    """Strip tags and CDATA from a feed field, and decode HTML entities.

    YouTube returns titles HTML-escaped -- "Arteta&#39;s" and "&quot;Arsenal" --
    and RSS descriptions often carry entities too. Left alone they render
    literally, which looks like a broken encoding.
    """
    cleaned = raw.replace("<![CDATA[", "").replace("]]>", "")
    return html.unescape(_TAG.sub("", cleaned)).strip()


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


def newest_first(items: list[Item]) -> list[Item]:
    """Sort by publication time, most recent first.

    RSS makes no ordering promise and Sky's feed is not chronological -- it led
    with a live-match page from the afternoon and put a two-day-old preview
    second. Anything undated sorts last rather than jumping to the top.
    """
    return sorted(items, key=lambda i: i.published or "", reverse=True)


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
                title=html.unescape(str(snippet["title"])),
                url=f"https://www.youtube.com/watch?v={video_id}",
                source=snippet.get("channelTitle", "YouTube"),
                published=snippet.get("publishedAt"),
            )
        )
    return items


async def fetch_all_uploads(api_key: str, per_channel: int = 4) -> tuple[list[Item], dict[str, str]]:
    """Recent uploads across every stored channel.

    One search call per channel, six channels, every 30 minutes -- about 300
    calls a day against a 10,000-unit quota, so there is room to spare.
    """
    if not api_key:
        return [], {}

    collected: list[Item] = []
    errors: dict[str, str] = {}
    up = Upstream(name="youtube", base_url=YOUTUBE_API)
    try:
        for channel in channels():
            try:
                found = await fetch_uploads(up, api_key, channel["channel_id"], per_channel)
                collected.extend(found)
            except UpstreamError as exc:
                errors[channel["name"]] = str(exc)
                log.warning("news.youtube_failed", channel=channel["name"], error=str(exc))
    finally:
        await up.close()
    return newest_first(collected), errors


async def poll_news(api_key: str = "") -> dict[str, Any]:
    """Every feed, merged and sorted, degrading one outlet at a time.

    One outlet going down must cost only its own headlines, so each is fetched
    and recorded separately and the failure is reported alongside the rest.
    """
    collected: list[Item] = []
    errors: dict[str, str] = {}

    for name, client, path in feed_clients():
        try:
            xml = await client.get_text(path)
            found = parse_rss(xml, source=name)
            collected.extend(found)
            log.info("news.fetched", source=name, count=len(found))
        except UpstreamError as exc:
            errors[name] = str(exc)
            log.warning("news.feed_failed", source=name, error=str(exc))
        except Exception as exc:
            errors[name] = str(exc)
            log.warning("news.feed_error", source=name, error=str(exc))
        finally:
            await client.close()

    # De-duplicate by URL: outlets syndicate, and the same story arriving twice
    # reads as a bug.
    seen: set[str] = set()
    unique: list[Item] = []
    for item in newest_first(collected):
        if item.url in seen:
            continue
        seen.add(item.url)
        unique.append(item)

    uploads, upload_errors = await fetch_all_uploads(api_key)
    errors.update(upload_errors)

    # asdict, not __dict__: Item is a slots dataclass and has no __dict__.
    return {
        "sky": [asdict(item) for item in unique[:40]],
        "youtube": [asdict(item) for item in uploads[:12]],
        "athletic": [],
        "errors": errors,
        "sources": [name for name, _, _ in FEEDS],
        "fetched_at": datetime.now(UTC).isoformat(),
    }
