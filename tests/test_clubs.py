"""Club-name mapper tests.

The brief calls this out as one of three places bugs will be, because every
upstream spells clubs differently and a mismatch fails silently rather than
loudly. These tests use the exact names each source actually emits.
"""

from __future__ import annotations

import json
import pathlib
from typing import ClassVar

import pytest
from shared.clubs import (
    BY_FPL_ID,
    BY_SHORT_NAME,
    CLUBS,
    UnknownClubError,
    by_fpl_id,
    find,
    normalise,
    resolve,
)
from shared.scoring import InvalidTableError, validate_table


class TestCanonicalTable:
    def test_there_are_twenty_clubs(self) -> None:
        assert len(CLUBS) == 20

    def test_short_names_are_unique(self) -> None:
        assert len({c.short_name for c in CLUBS}) == 20

    def test_fpl_ids_are_unique_and_contiguous(self) -> None:
        assert sorted(c.fpl_id for c in CLUBS) == list(range(1, 21))

    def test_every_club_has_a_three_letter_monogram(self) -> None:
        for club in CLUBS:
            assert len(club.monogram) == 3, club.short_name
            assert club.monogram.isupper()

    def test_every_club_has_a_valid_hex_colour_pair(self) -> None:
        for club in CLUBS:
            for colour in (club.primary, club.on_primary):
                assert colour.startswith("#"), club.short_name
                assert len(colour) == 7, club.short_name
                int(colour[1:], 16)  # raises if it is not real hex


class TestTheToNamingTrap:
    """The exact example from the brief: Spurs / Tottenham Hotspur / Tottenham."""

    @pytest.mark.parametrize(
        "source_name",
        ["Spurs", "Tottenham Hotspur", "Tottenham", "Tottenham Hotspur FC", "TOT", "tottenham hotspur"],
    )
    def test_every_spelling_of_spurs_resolves_to_one_club(self, source_name: str) -> None:
        assert resolve(source_name).short_name == "TOT"


class TestCrossSourceNames:
    # Left: how a source spells it. Right: the canonical short name.
    CASES: ClassVar[list[tuple[str, str]]] = [
        # FPL bootstrap-static short_name and name
        ("Man Utd", "MUN"),
        ("Man City", "MCI"),
        ("Nott'm Forest", "NFO"),
        ("Spurs", "TOT"),
        ("Brighton", "BHA"),
        ("Leeds", "LEE"),
        # The Odds API full names
        ("Manchester United", "MUN"),
        ("Manchester City", "MCI"),
        ("Nottingham Forest", "NFO"),
        ("Tottenham Hotspur", "TOT"),
        ("Brighton and Hove Albion", "BHA"),
        ("Leeds United", "LEE"),
        ("AFC Bournemouth", "BOU"),
        ("Ipswich Town", "IPS"),
        # football-data.org / API-Football styles
        ("Tottenham", "TOT"),
        ("Newcastle Utd", "NEW"),
        ("Man United", "MUN"),
        ("Brighton & Hove Albion", "BHA"),
        ("Crystal Palace FC", "CRY"),
        ("Coventry City", "COV"),
        ("Hull City", "HUL"),
        ("Sunderland AFC", "SUN"),
    ]

    @pytest.mark.parametrize(("source_name", "expected"), CASES)
    def test_source_names_map_to_canonical_clubs(self, source_name: str, expected: str) -> None:
        assert resolve(source_name).short_name == expected

    def test_matching_is_case_and_punctuation_insensitive(self) -> None:
        assert resolve("nottingham forest").short_name == "NFO"
        assert resolve("NOTTM FOREST").short_name == "NFO"
        assert resolve("Nott'm  Forest").short_name == "NFO"

    def test_club_suffixes_are_ignored(self) -> None:
        assert resolve("Arsenal FC").short_name == "ARS"
        assert resolve("Everton F.C.").short_name == "EVE"


class TestNormalise:
    def test_diacritics_fold_for_lookup(self) -> None:
        # Player names carry diacritics; the same folding backs player search.
        assert normalise("Ødegaard") == normalise("Odegaard")
        assert normalise("Magalhães") == normalise("Magalhaes")
        assert normalise("Guimarães") == normalise("Guimaraes")
        assert normalise("Gyökeres") == normalise("Gyokeres")

    def test_ampersand_expands_to_and(self) -> None:
        assert normalise("Brighton & Hove Albion") == normalise("Brighton and Hove Albion")

    def test_empty_string_is_handled(self) -> None:
        assert normalise("") == ""


class TestFailureIsLoud:
    def test_an_unmappable_name_raises_rather_than_guessing(self) -> None:
        # A club we cannot map is a data problem to surface, not a row to drop.
        with pytest.raises(UnknownClubError):
            resolve("Real Madrid")

    def test_find_returns_none_instead_of_raising(self) -> None:
        assert find("Real Madrid") is None
        assert find("") is None

    def test_a_relegated_club_no_longer_resolves(self) -> None:
        # Leicester are not in the 26/27 division; mapping them would be wrong.
        assert find("Leicester City") is None

    def test_unknown_fpl_id_raises(self) -> None:
        with pytest.raises(UnknownClubError):
            by_fpl_id(99)


class TestAgainstRealFplData:
    """Every club FPL actually returns must resolve. This is the real contract."""

    FIXTURE = pathlib.Path(__file__).parent / "data" / "fpl_teams_2026_27.json"

    def test_every_live_fpl_team_maps_to_a_canonical_club(self) -> None:
        teams = json.loads(self.FIXTURE.read_text())
        assert len(teams) == 20
        for team in teams:
            club = by_fpl_id(team["id"])
            assert club.short_name == team["short_name"]
            # The long name FPL ships must resolve through the alias index too.
            assert resolve(team["name"]).short_name == team["short_name"]

    def test_the_canonical_table_matches_fpl_exactly(self) -> None:
        teams = json.loads(self.FIXTURE.read_text())
        assert {t["short_name"] for t in teams} == set(BY_SHORT_NAME)
        assert {t["id"] for t in teams} == set(BY_FPL_ID)


class TestTableValidation:
    ALL: ClassVar[list[str]] = [c.short_name for c in CLUBS]

    def test_a_complete_table_validates(self) -> None:
        validate_table(self.ALL, self.ALL)

    def test_a_short_table_is_rejected(self) -> None:
        with pytest.raises(InvalidTableError, match="all 20"):
            validate_table(self.ALL[:19], self.ALL)

    def test_a_duplicate_is_rejected(self) -> None:
        table = list(self.ALL)
        table[5] = table[0]
        with pytest.raises(InvalidTableError, match="twice") as exc:
            validate_table(table, self.ALL)
        assert exc.value.detail == (table[0],)

    def test_a_gap_is_rejected(self) -> None:
        table = list(self.ALL)
        table[7] = ""
        with pytest.raises(InvalidTableError, match="must name a club"):
            validate_table(table, self.ALL)

    def test_an_unknown_club_is_rejected(self) -> None:
        table = list(self.ALL)
        table[3] = "LEI"
        with pytest.raises(InvalidTableError, match="unknown club"):
            validate_table(table, self.ALL)
