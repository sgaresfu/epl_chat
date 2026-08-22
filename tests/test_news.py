"""News tests.

Sky's RSS needs no key, so this panel must work on a clean clone. The parser is
tested against a real captured feed, including the shapes that break a naive
regex: CDATA, entities, and an item missing its link.
"""

from __future__ import annotations

from httpx import AsyncClient
from services.poller.news import parse_rss

from tests.conftest import sign_in

FEED = """<?xml version="1.0" encoding="utf-8" ?>
<rss version='2.0'><channel>
  <title>SkySports | News</title>
  <item>
    <title>The Premier League is back! Arsenal vs Coventry LIVE</title>
    <description><![CDATA[<p>Everything you need for the opener.</p>]]></description>
    <link>https://www.skysports.com/football/arsenal-vs-coventry-city/live/559444</link>
    <pubDate>Fri, 21 Aug 2026 15:00:00 BST</pubDate>
  </item>
  <item>
    <title><![CDATA[Merson's season preview: Who wins the title?]]></title>
    <description>A view.</description>
    <link>https://www.skysports.com/football/news/11661/13574632/preview</link>
    <pubDate>Wed, 19 Aug 2026 07:17:00 BST</pubDate>
  </item>
  <item>
    <title>Broken item with no link</title>
    <description>Nothing here.</description>
  </item>
</channel></rss>"""


class TestParser:
    def test_it_reads_well_formed_items(self) -> None:
        items = parse_rss(FEED, source="Sky Sports")
        assert len(items) == 2

    def test_an_item_missing_its_link_is_dropped_not_fatal(self) -> None:
        # A feed that changes shape should cost one item, not the whole panel.
        items = parse_rss(FEED, source="Sky Sports")
        assert all(item.url for item in items)
        assert "Broken item" not in [item.title for item in items]

    def test_cdata_is_unwrapped(self) -> None:
        items = parse_rss(FEED, source="Sky Sports")
        assert items[1].title == "Merson's season preview: Who wins the title?"
        assert "CDATA" not in items[1].title

    def test_html_is_stripped_from_summaries(self) -> None:
        items = parse_rss(FEED, source="Sky Sports")
        assert items[0].summary == "Everything you need for the opener."
        assert "<p>" not in items[0].summary

    def test_dates_become_utc_iso(self) -> None:
        items = parse_rss(FEED, source="Sky Sports")
        # 15:00 BST is 14:00 UTC.
        assert items[0].published is not None
        assert items[0].published.startswith("2026-08-21T14:00")

    def test_an_empty_feed_yields_nothing_rather_than_raising(self) -> None:
        assert parse_rss("<rss></rss>", source="Sky Sports") == []

    def test_the_limit_is_respected(self) -> None:
        assert len(parse_rss(FEED, source="Sky Sports", limit=1)) == 1


class TestSorting:
    """RSS makes no ordering promise, and Sky's feed is not chronological.

    It led with a live-match page from the afternoon and put a two-day-old
    preview second, so the page inherited that order.
    """

    def test_items_come_back_newest_first(self) -> None:
        from services.poller.news import newest_first

        items = parse_rss(FEED, source="Sky Sports")
        ordered = newest_first(items)
        dates = [i.published or "" for i in ordered]
        assert dates == sorted(dates, reverse=True)

    def test_the_newest_story_leads(self) -> None:
        from services.poller.news import newest_first

        ordered = newest_first(parse_rss(FEED, source="Sky Sports"))
        assert ordered[0].title.startswith("The Premier League is back")

    def test_an_undated_item_sorts_last_not_first(self) -> None:
        from services.poller.news import Item, newest_first

        dated = Item(title="dated", url="a", source="s", published="2026-08-21T14:00:00+00:00")
        undated = Item(title="undated", url="b", source="s", published=None)
        assert [i.title for i in newest_first([undated, dated])] == ["dated", "undated"]


class TestSources:
    def test_three_free_outlets_are_configured(self) -> None:
        from services.poller.news import FEEDS

        names = {name for name, _, _ in FEEDS}
        assert names == {"Sky Sports", "BBC Sport", "The Guardian"}

    def test_none_of_them_need_a_key(self) -> None:
        from services.poller.news import FEEDS

        for _, base, path in FEEDS:
            assert "key=" not in base + path
            assert base.startswith("https://")


class TestEndpoint:
    async def test_it_reports_the_wait_before_the_poller_has_run(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/news")).json()
        assert body["sky"] == []
        assert body["empty_message"]

    async def test_a_missing_youtube_key_names_itself(self, client: AsyncClient) -> None:
        # A missing key degrades one panel with a clear message, not the site.
        await sign_in(client)
        body = (await client.get("/api/news")).json()
        assert "YOUTUBE_API_KEY" in body["youtube_message"]

    async def test_the_athletic_is_explained_not_scraped(self, client: AsyncClient) -> None:
        await sign_in(client)
        body = (await client.get("/api/news")).json()
        assert "paywalled" in body["athletic_message"]
        assert body["athletic"] == []

    async def test_the_replacement_outlets_are_named(self, client: AsyncClient) -> None:
        await sign_in(client)
        message = (await client.get("/api/news")).json()["athletic_message"]
        assert "BBC Sport" in message
        assert "Guardian" in message

    async def test_it_needs_a_session(self, client: AsyncClient) -> None:
        assert (await client.get("/api/news")).status_code == 401


class TestDateParsing:
    """BST is the one that bites: RFC 2822 does not define it numerically.

    ``parsedate_to_datetime`` returns a naive datetime for BST, and calling
    ``astimezone`` on a naive value reinterprets it as the *server's* local
    zone. Sky stamps its whole feed in BST, so on a machine three hours off UTC
    every headline was three hours wrong.
    """

    def test_bst_is_one_hour_ahead_of_utc(self) -> None:
        from services.poller.news import parse_date

        moment = parse_date("Fri, 21 Aug 2026 15:00:00 BST")
        assert moment is not None
        assert moment.isoformat() == "2026-08-21T14:00:00+00:00"

    def test_bst_is_not_treated_as_utc(self) -> None:
        from services.poller.news import parse_date

        moment = parse_date("Fri, 21 Aug 2026 15:00:00 BST")
        assert moment is not None
        assert moment.hour == 14, "BST must shift by an hour, not be taken at face value"

    def test_a_numeric_offset_still_works(self) -> None:
        from services.poller.news import parse_date

        moment = parse_date("Fri, 21 Aug 2026 15:00:00 +0100")
        assert moment is not None
        assert moment.isoformat() == "2026-08-21T14:00:00+00:00"

    def test_gmt_is_utc(self) -> None:
        from services.poller.news import parse_date

        moment = parse_date("Fri, 21 Aug 2026 15:00:00 GMT")
        assert moment is not None
        assert moment.isoformat() == "2026-08-21T15:00:00+00:00"

    def test_the_result_is_always_timezone_aware(self) -> None:
        from services.poller.news import parse_date

        for raw in (
            "Fri, 21 Aug 2026 15:00:00 BST",
            "Fri, 21 Aug 2026 15:00:00 GMT",
            "Fri, 21 Aug 2026 15:00:00 +0000",
        ):
            moment = parse_date(raw)
            assert moment is not None
            assert moment.tzinfo is not None, raw

    def test_an_unparseable_date_is_none_not_an_exception(self) -> None:
        from services.poller.news import parse_date

        assert parse_date("not a date at all") is None
        assert parse_date("") is None

    def test_an_unknown_zone_falls_back_to_utc_not_the_host(self) -> None:
        from services.poller.news import parse_date

        moment = parse_date("Fri, 21 Aug 2026 15:00:00 XYZ")
        assert moment is not None
        assert moment.isoformat() == "2026-08-21T15:00:00+00:00"


class TestPayloadIsSerialisable:
    """The poller writes JSON to the cache, so every item must convert cleanly.

    ``Item`` is a slots dataclass and therefore has no ``__dict__``; reaching for
    one silently emptied the whole panel while the RSS fetch itself succeeded.
    """

    async def test_the_payload_contains_the_fetched_items(self) -> None:
        from dataclasses import asdict

        items = parse_rss(FEED, source="Sky Sports")
        rows = [asdict(item) for item in items]
        assert len(rows) == 2
        assert rows[0]["title"].startswith("The Premier League is back")

    def test_an_item_has_no_dunder_dict(self) -> None:
        items = parse_rss(FEED, source="Sky Sports")
        assert not hasattr(items[0], "__dict__")

    def test_the_payload_survives_a_json_round_trip(self) -> None:
        import json
        from dataclasses import asdict

        rows = [asdict(item) for item in parse_rss(FEED, source="Sky Sports")]
        assert json.loads(json.dumps(rows)) == rows


class TestHtmlEntities:
    """YouTube returns titles HTML-escaped; left alone they render literally."""

    def test_entities_are_decoded_in_titles(self) -> None:
        from services.poller.news import _text

        assert _text("Arteta&#39;s FULL interview") == "Arteta's FULL interview"
        assert _text("&quot;Arsenal have a chance&quot;") == '"Arsenal have a chance"'

    def test_ampersands_survive(self) -> None:
        from services.poller.news import _text

        assert _text("Brighton &amp; Hove Albion") == "Brighton & Hove Albion"

    def test_tags_are_still_stripped(self) -> None:
        from services.poller.news import _text

        assert _text("<p>Everything you need.</p>") == "Everything you need."


class TestYouTubeChannels:
    def test_all_six_channels_from_the_brief_are_resolved(self) -> None:
        from services.poller.news import channels

        names = {c["name"] for c in channels()}
        assert names == {
            "The Overlap",
            "The Rest Is Football",
            "Sky Sports Premier League",
            "Premier League",
            "Let's Talk FPL",
            "Єврофутбол",
        }

    def test_every_id_looks_like_a_youtube_channel_id(self) -> None:
        from services.poller.news import channels

        for channel in channels():
            assert channel["channel_id"].startswith("UC")
            assert len(channel["channel_id"]) == 24

    def test_the_ambiguous_ukrainian_channel_records_why_it_was_chosen(self) -> None:
        """Several channels match the name; only one is Ukrainian-language."""
        from services.poller.news import channels

        euro = next(c for c in channels() if c["name"] == "Єврофутбол")
        assert euro["language"] == "uk"
        assert "note" in euro

    def test_ids_are_unique(self) -> None:
        from services.poller.news import channels

        ids = [c["channel_id"] for c in channels()]
        assert len(ids) == len(set(ids))


class TestImages:
    """Outlets publish several renditions; the first one listed is the smallest.

    The Guardian lists 140, 460 and 700, each signed separately. Taking the
    first got a 140px thumbnail; rewriting its width to something usable
    invalidated the signature and the CDN answered 401 for every Guardian
    story on the page.
    """

    GUARDIAN = """<item>
      <media:content width="140" url="https://i.guim.co.uk/img/a/master/140.jpg?s=abc"/>
      <media:content width="460" url="https://i.guim.co.uk/img/a/master/460.jpg?s=def"/>
      <media:content width="700" url="https://i.guim.co.uk/img/a/master/700.jpg?s=ghi"/>
      <title>x</title><link>https://example.com/a</link>
    </item>"""

    BBC = """<item>
      <media:thumbnail width="240" height="134" url="https://ichef.bbci.co.uk/ace/standard/240/x.jpg"/>
      <title>x</title><link>https://example.com/b</link>
    </item>"""

    SKY = """<item>
      <enclosure type="image/jpg" url="https://e1.365dm.com/26/08/1920x1080/x.jpg"/>
      <title>x</title><link>https://example.com/c</link>
    </item>"""

    def test_the_largest_published_variant_wins(self) -> None:
        from services.poller.news import extract_image

        assert extract_image(self.GUARDIAN) == "https://i.guim.co.uk/img/a/master/700.jpg?s=ghi"

    def test_a_signed_url_is_never_rewritten(self) -> None:
        """Changing a parameter breaks the signature and the CDN returns 401."""
        from services.poller.news import extract_image

        url = extract_image(self.GUARDIAN)
        assert url is not None
        assert "s=ghi" in url
        assert "width=" not in url

    def test_the_bbc_path_width_is_upgraded(self) -> None:
        # The BBC's size sits in the path and is not signed, so it can be asked
        # for larger without breaking anything.
        from services.poller.news import extract_image

        assert extract_image(self.BBC) == "https://ichef.bbci.co.uk/ace/standard/976/x.jpg"

    def test_an_enclosure_is_used_when_there_is_no_media_tag(self) -> None:
        from services.poller.news import extract_image

        assert extract_image(self.SKY) == "https://e1.365dm.com/26/08/1920x1080/x.jpg"

    def test_an_item_with_no_image_yields_none(self) -> None:
        from services.poller.news import extract_image

        assert extract_image("<item><title>x</title></item>") is None

    def test_a_relative_url_is_ignored(self) -> None:
        from services.poller.news import extract_image

        assert extract_image('<item><media:content url="/local.jpg"/></item>') is None

    def test_parsed_items_carry_their_image(self) -> None:
        items = parse_rss(f"<rss>{self.BBC}</rss>", source="BBC Sport")
        assert items[0].image == "https://ichef.bbci.co.uk/ace/standard/976/x.jpg"
