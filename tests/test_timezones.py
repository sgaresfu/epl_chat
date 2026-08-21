"""Timezone tests, with the DST boundaries the brief warns about.

The four zones change clocks on *different* dates: the EU moves on the last
Sunday in March and October, North America on the second Sunday in March and
the first in November. Between those dates the offset between Lviv and Detroit
is not what it is the rest of the year, which is exactly the fortnight a
hardcoded offset gets wrong.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

import pytest
from shared.timezones import (
    BY_KEY,
    PLACES,
    abbreviation,
    all_kickoffs,
    is_night,
    local_hour,
    local_kickoff,
    offset_label,
    to_zone,
)

UTC = UTC


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)  # type: ignore[arg-type]


class TestPlaces:
    def test_all_four_people_have_a_place(self) -> None:
        assert {p.person for p in PLACES} == {"COYG", "AURE", "TWZT", "BULBA"}

    def test_zones_are_iana_names_not_offsets(self) -> None:
        for place in PLACES:
            assert "/" in place.timezone, place.timezone
            assert not place.timezone.startswith("UTC")

    def test_each_zone_loads(self) -> None:
        for place in PLACES:
            assert place.zone is not None


class TestBasicConversion:
    def test_the_opening_match_renders_in_all_four_cities(self) -> None:
        # Arsenal v Coventry, the real GW1 opener: 2026-08-21 19:00 UTC.
        kickoff = utc(2026, 8, 21, 19, 0)
        times = {k.place: k.time for k in all_kickoffs(kickoff)}
        assert times == {
            "coyg": "22:00",  # Lviv, UTC+3 in summer
            "aure": "15:00",  # Michigan, UTC-4 in summer
            "twzt": "13:00",  # Alberta, UTC-6 in summer
            "bulba": "11:00",  # Alaska, UTC-8 in summer
        }

    def test_those_match_the_design_mockup(self) -> None:
        # The mockup's four-city block shows 22:00 / 15:00 / 13:00 / 11:00.
        kickoff = utc(2026, 8, 21, 19, 0)
        assert [k.time for k in all_kickoffs(kickoff)] == ["22:00", "15:00", "13:00", "11:00"]

    def test_a_naive_datetime_is_treated_as_utc_not_local_machine_time(self) -> None:
        naive = datetime(2026, 8, 21, 19, 0)  # noqa: DTZ001 - naive on purpose
        aware = utc(2026, 8, 21, 19, 0)
        assert to_zone(naive, "Europe/Kyiv") == to_zone(aware, "Europe/Kyiv")


class TestDaylightSavingBoundaries:
    """The fortnight where Europe and North America disagree."""

    def test_lviv_is_utc_plus_three_in_summer_and_two_in_winter(self) -> None:
        assert offset_label(utc(2026, 8, 21, 12), "Europe/Kyiv") == "UTC+3"
        assert offset_label(utc(2026, 12, 26, 12), "Europe/Kyiv") == "UTC+2"

    def test_michigan_is_minus_four_in_summer_and_five_in_winter(self) -> None:
        assert offset_label(utc(2026, 8, 21, 12), "America/Detroit") == "UTC-4"
        assert offset_label(utc(2026, 12, 26, 12), "America/Detroit") == "UTC-5"

    def test_the_lviv_to_michigan_gap_is_seven_hours_in_summer(self) -> None:
        moment = utc(2026, 8, 21, 19)
        gap = local_hour(moment, "Europe/Kyiv") - local_hour(moment, "America/Detroit")
        assert gap == 7

    def test_the_gap_narrows_to_six_between_the_two_changeover_dates(self) -> None:
        # Europe fell back on 25 Oct 2026; the US does not until 1 Nov 2026.
        # For that week the gap is six hours, not the usual seven. A stored
        # offset is wrong for every kickoff in this window.
        moment = utc(2026, 10, 28, 19)
        gap = local_hour(moment, "Europe/Kyiv") - local_hour(moment, "America/Detroit")
        assert gap == 6

    def test_the_gap_returns_to_seven_after_north_america_changes(self) -> None:
        moment = utc(2026, 11, 4, 19)
        gap = local_hour(moment, "Europe/Kyiv") - local_hour(moment, "America/Detroit")
        assert gap == 7

    def test_a_boxing_day_kickoff_lands_correctly_in_all_four_cities(self) -> None:
        # Deep winter. Note Alberta is UTC-6, not the UTC-7 that "Mountain Time"
        # would suggest -- see TestAlbertaDropsDaylightSaving below.
        kickoff = utc(2026, 12, 26, 15, 0)
        times = {k.place: k.time for k in all_kickoffs(kickoff)}
        assert times == {
            "coyg": "17:00",  # UTC+2, EET
            "aure": "10:00",  # UTC-5, EST
            "twzt": "09:00",  # UTC-6, CST
            "bulba": "06:00",  # UTC-9, AKST
        }

    def test_spring_forward_is_handled_for_each_zone_on_its_own_date(self) -> None:
        # 15 March 2026: North America has sprung forward, Europe has not.
        moment = utc(2026, 3, 15, 18)
        assert offset_label(moment, "America/Detroit") == "UTC-4"  # already EDT
        assert offset_label(moment, "Europe/Kyiv") == "UTC+2"  # still EET
        # 29 March 2026: Europe has now sprung forward too.
        later = utc(2026, 3, 29, 18)
        assert offset_label(later, "Europe/Kyiv") == "UTC+3"

    def test_abbreviations_track_the_season(self) -> None:
        assert abbreviation(utc(2026, 8, 21, 12), "America/Detroit") == "EDT"
        assert abbreviation(utc(2026, 12, 26, 12), "America/Detroit") == "EST"


class TestNightMedal:
    def test_a_late_kickoff_is_night_in_alaska_but_not_in_lviv(self) -> None:
        # 09:00 UTC: 02:00 in Anchorage (night), 12:00 in Lviv (not).
        moment = utc(2026, 11, 8, 10, 0)
        assert is_night(moment, "America/Anchorage") is True
        assert is_night(moment, "Europe/Kyiv") is False

    @pytest.mark.parametrize(
        ("hour", "expected"),
        [(0, True), (1, True), (4, True), (5, False), (6, False), (23, False)],
    )
    def test_night_window_is_midnight_to_five(self, hour: int, expected: bool) -> None:
        # Build a UTC instant that lands on the given local hour in Lviv (UTC+3 in August).
        moment = utc(2026, 8, 22, (hour - 3) % 24)
        assert is_night(moment, "Europe/Kyiv") is expected

    def test_the_night_medal_is_recorded_per_person_not_per_match(self) -> None:
        # One match, four people, different answers -- which is the whole point.
        moment = utc(2026, 11, 8, 10, 0)
        flags = {k.person: k.is_night for k in all_kickoffs(moment)}
        assert flags["BULBA"] is True
        assert flags["COYG"] is False


class TestDayShift:
    def test_a_late_uk_kickoff_is_the_same_day_in_lviv(self) -> None:
        k = local_kickoff(utc(2026, 8, 21, 19), BY_KEY["coyg"])
        assert k.day_shift == 0
        assert k.weekday == "Fri"

    def test_an_early_utc_kickoff_is_the_previous_day_in_alaska(self) -> None:
        # 03:00 UTC Sunday is 18:00 Saturday in Anchorage.
        k = local_kickoff(utc(2026, 8, 23, 3), BY_KEY["bulba"])
        assert k.day_shift == -1
        assert k.weekday == "Sat"

    def test_a_very_late_kickoff_rolls_into_tomorrow_in_lviv(self) -> None:
        # 22:00 UTC is 01:00 the next day in Kyiv.
        k = local_kickoff(utc(2026, 8, 21, 22), BY_KEY["coyg"])
        assert k.day_shift == 1
        assert k.is_night is True


class TestRealFixtureTimes:
    """Every real GW1 kickoff, converted for all four cities."""

    GW1: ClassVar[list[tuple[str, str]]] = [
        ("2026-08-21T19:00:00Z", "ARS v COV"),
        ("2026-08-22T11:30:00Z", "HUL v MUN"),
        ("2026-08-22T14:00:00Z", "EVE v CRY"),
        ("2026-08-23T15:30:00Z", "NEW v LIV"),
        ("2026-08-24T19:00:00Z", "FUL v CHE"),
    ]

    @pytest.mark.parametrize(("iso", "label"), GW1)
    def test_every_gw1_kickoff_renders_for_four_cities(self, iso: str, label: str) -> None:
        moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        kickoffs = all_kickoffs(moment)
        assert len(kickoffs) == 4
        for k in kickoffs:
            hh, mm = k.time.split(":")
            assert 0 <= int(hh) <= 23, label
            assert 0 <= int(mm) <= 59, label
            assert k.offset.startswith("UTC")

    def test_the_saturday_1130_kickoff_is_early_morning_in_alaska(self) -> None:
        # 11:30 UTC is 03:30 in Anchorage -- the mockup's "Watched 03:30 in Alaska".
        moment = datetime.fromisoformat("2026-08-22T11:30:00+00:00")
        k = local_kickoff(moment, BY_KEY["bulba"])
        assert k.time == "03:30"
        assert k.is_night is True


class TestAlbertaDropsDaylightSaving:
    """Alberta stops changing its clocks on 1 November 2026 -- mid-season.

    tzdata 2026c has ``America/Edmonton`` remaining at UTC-6 from that date and
    relabelling to CST, rather than falling back to MST at UTC-7 the way true
    Mountain Time (``America/Denver``) still does. The change lands between
    matchweeks, so every TWZT kickoff in the second half of the season is an
    hour away from what "Alberta is Mountain Time" would give you.

    This is the concrete reason the brief insists on IANA zones over offsets,
    and these tests fail loudly if a future tzdata reverts the rule.
    """

    def test_alberta_and_mountain_time_agree_before_the_change(self) -> None:
        moment = utc(2026, 10, 20, 19)
        assert offset_label(moment, "America/Edmonton") == "UTC-6"
        assert offset_label(moment, "America/Denver") == "UTC-6"

    def test_alberta_and_mountain_time_diverge_after_the_change(self) -> None:
        moment = utc(2026, 11, 15, 19)
        assert offset_label(moment, "America/Edmonton") == "UTC-6"  # stays put
        assert offset_label(moment, "America/Denver") == "UTC-7"  # falls back

    def test_alberta_keeps_one_offset_across_the_whole_winter(self) -> None:
        for month, day in ((11, 15), (12, 26), (1, 20), (2, 14)):
            year = 2026 if month >= 11 else 2027
            moment = utc(year, month, day, 19)
            assert offset_label(moment, "America/Edmonton") == "UTC-6", f"{year}-{month}"

    def test_a_boxing_day_kickoff_is_an_hour_later_than_mountain_time_would_say(self) -> None:
        kickoff = utc(2026, 12, 26, 15, 0)
        assert local_kickoff(kickoff, BY_KEY["twzt"]).time == "09:00"
        assert to_zone(kickoff, "America/Denver").strftime("%H:%M") == "08:00"

    def test_the_michigan_to_alberta_gap_changes_mid_season(self) -> None:
        """Two North American cities, and the gap between them is not constant.

        Michigan and Alberta sit two hours apart for the opening months. On
        1 November 2026 Michigan falls back an hour and Alberta does not, so
        from then on they are one hour apart -- until Michigan springs forward
        again on 14 March 2027 and the gap widens back to two. It flips twice
        inside a single season, so any code caching "AURE is two hours ahead of
        TWZT" is wrong for four and a half months of it.
        """

        def gap(iso: str) -> int:
            moment = datetime.fromisoformat(iso).replace(tzinfo=UTC)
            return local_hour(moment, "America/Detroit") - local_hour(moment, "America/Edmonton")

        assert gap("2026-08-21T19:00") == 2  # opening night
        assert gap("2026-10-20T19:00") == 2  # still two apart
        assert gap("2026-11-15T19:00") == 1  # Michigan fell back, Alberta did not
        assert gap("2026-12-26T15:00") == 1  # Boxing Day
        assert gap("2027-03-20T15:00") == 2  # Michigan sprang forward again
        assert gap("2027-05-30T15:00") == 2  # final day
