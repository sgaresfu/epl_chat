"""Canonical club table for the 2026/27 Premier League season.

Every upstream names clubs differently: FPL says ``Spurs``, the Odds API says
``Tottenham Hotspur``, API-Football says ``Tottenham``. Each of those resolves
through this module to one canonical :class:`Club`, keyed by the FPL
``short_name``. Nothing else in the codebase is allowed to compare club names
directly -- that is the failure that goes unnoticed until November.

Colours are the club's primary shirt colour and the only non-token colour the
design permits. ``on_primary`` carries the text colour that meets contrast on
that ground, so light-shirted clubs (Coventry, Hull, City, Leeds) get dark
monograms rather than unreadable white ones.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True, slots=True)
class Club:
    """One Premier League club, canonical across every data source."""

    fpl_id: int
    short_name: str
    name: str
    full_name: str
    primary: str
    on_primary: str
    aliases: tuple[str, ...] = field(default=())

    @property
    def monogram(self) -> str:
        """The three-letter disc label used by every crest in the UI."""
        return self.short_name.upper()


# Ordered by FPL team id, which is alphabetical by full club name.
CLUBS: Final[tuple[Club, ...]] = (
    Club(1, "ARS", "Arsenal", "Arsenal", "#EF0107", "#FFFFFF", ("Arsenal FC", "The Arsenal")),
    Club(2, "AVL", "Aston Villa", "Aston Villa", "#670E36", "#FFFFFF", ("Aston Villa FC", "Villa")),
    Club(
        3,
        "BOU",
        "Bournemouth",
        "AFC Bournemouth",
        "#DA291C",
        "#FFFFFF",
        ("AFC Bournemouth", "Bournemouth FC"),
    ),
    Club(4, "BRE", "Brentford", "Brentford", "#E30613", "#FFFFFF", ("Brentford FC",)),
    Club(
        5,
        "BHA",
        "Brighton",
        "Brighton & Hove Albion",
        "#0057B8",
        "#FFFFFF",
        ("Brighton & Hove Albion", "Brighton and Hove Albion", "Brighton Hove Albion", "Brighton FC"),
    ),
    Club(6, "CHE", "Chelsea", "Chelsea", "#034694", "#FFFFFF", ("Chelsea FC",)),
    Club(7, "COV", "Coventry", "Coventry City", "#7BC5EC", "#003087", ("Coventry City", "Coventry City FC")),
    Club(8, "CRY", "Crystal Palace", "Crystal Palace", "#1B458F", "#FFFFFF", ("Crystal Palace FC", "Palace")),
    Club(9, "EVE", "Everton", "Everton", "#003399", "#FFFFFF", ("Everton FC",)),
    Club(10, "FUL", "Fulham", "Fulham", "#1A1A1A", "#FFFFFF", ("Fulham FC",)),
    Club(
        11, "HUL", "Hull City", "Hull City", "#F5A12D", "#3B2100", ("Hull", "Hull City AFC", "Hull City FC")
    ),
    Club(12, "IPS", "Ipswich", "Ipswich Town", "#0044A9", "#FFFFFF", ("Ipswich Town", "Ipswich Town FC")),
    Club(
        13,
        "LEE",
        "Leeds",
        "Leeds United",
        "#FFCD00",
        "#1D428A",
        ("Leeds United", "Leeds Utd", "Leeds United FC"),
    ),
    Club(14, "LIV", "Liverpool", "Liverpool", "#C8102E", "#FFFFFF", ("Liverpool FC",)),
    Club(
        15,
        "MCI",
        "Man City",
        "Manchester City",
        "#6CABDD",
        "#0B2A5B",
        ("Manchester City", "Manchester City FC", "Man. City"),
    ),
    Club(
        16,
        "MUN",
        "Man Utd",
        "Manchester United",
        "#DA020E",
        "#FFFFFF",
        ("Manchester United", "Man United", "Manchester Utd", "Man. United", "Manchester United FC"),
    ),
    Club(
        17,
        "NEW",
        "Newcastle",
        "Newcastle United",
        "#241F20",
        "#FFFFFF",
        ("Newcastle United", "Newcastle Utd", "Newcastle United FC"),
    ),
    Club(
        18,
        "NFO",
        "Nott'm Forest",
        "Nottingham Forest",
        "#DD0000",
        "#FFFFFF",
        ("Nottingham Forest", "Notts Forest", "Nott'm Forest", "Nottingham Forest FC", "Forest"),
    ),
    Club(
        19,
        "TOT",
        "Spurs",
        "Tottenham Hotspur",
        "#132257",
        "#FFFFFF",
        ("Tottenham Hotspur", "Tottenham", "Tottenham Hotspur FC"),
    ),
    Club(20, "SUN", "Sunderland", "Sunderland", "#EB172B", "#FFFFFF", ("Sunderland AFC", "Sunderland FC")),
)

BY_SHORT_NAME: Final[dict[str, Club]] = {c.short_name: c for c in CLUBS}
BY_FPL_ID: Final[dict[int, Club]] = {c.fpl_id: c for c in CLUBS}

_SUFFIXES: Final[tuple[str, ...]] = ("fc", "afc", "cf")

# Latin letters that carry no combining mark to strip, so NFKD leaves them
# whole and a naive alphanumeric filter deletes them outright. Odegaard is the
# case that matters here -- he is one of the seeded award picks, and folding
# "Odegaard" to "degaard" would quietly break player search for him.
_TRANSLITERATE: Final[dict[str, str]] = {
    "ø": "o",
    "đ": "d",
    "ð": "d",
    "ł": "l",
    "ß": "ss",
    "æ": "ae",
    "œ": "oe",
    "þ": "th",
    "ı": "i",
    "ħ": "h",
    "ŋ": "n",
    "ĸ": "k",
}

# Removed rather than replaced with a space, so "Nott'm" and "NOTTM" agree and
# "F.C." collapses to the strippable suffix "fc" instead of two stray tokens.
_ELIDED: Final[str] = "'\u2019\u02bc.\u00b7"


def normalise(value: str) -> str:
    """Fold a club or player name to a comparable key.

    Strips diacritics, transliterates atomic Latin letters, elides apostrophes
    and periods, and drops common club suffixes, so that ``Nott'm Forest``,
    ``NOTTM FOREST`` and ``Nottingham Forest FC`` all reduce to a stable token.

    Used for lookup only -- never for display, which always renders the original
    characters intact, diacritics and all.
    """
    lowered = value.casefold()
    mapped = "".join(_TRANSLITERATE.get(ch, ch) for ch in lowered)
    decomposed = unicodedata.normalize("NFKD", mapped)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    elided = "".join(ch for ch in stripped if ch not in _ELIDED)
    expanded = elided.replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", expanded)
    tokens = [t for t in cleaned.split() if t]
    while tokens and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _build_index() -> dict[str, Club]:
    index: dict[str, Club] = {}
    for club in CLUBS:
        candidates = {club.short_name, club.name, club.full_name, *club.aliases}
        for candidate in candidates:
            index.setdefault(normalise(candidate), club)
    return index


_ALIAS_INDEX: Final[dict[str, Club]] = _build_index()


class UnknownClubError(LookupError):
    """Raised when a source name cannot be resolved to a canonical club."""

    def __init__(self, value: str) -> None:
        super().__init__(f"No canonical club matches {value!r}")
        self.value = value


def find(value: str) -> Club | None:
    """Resolve any source's club name to a canonical club, or ``None``."""
    if not value:
        return None
    return _ALIAS_INDEX.get(normalise(value))


def resolve(value: str) -> Club:
    """Resolve a club name, raising :class:`UnknownClubError` if it is unknown.

    The poller uses this deliberately: a name it cannot map is a data problem
    worth surfacing loudly, not a row to drop quietly.
    """
    club = find(value)
    if club is None:
        raise UnknownClubError(value)
    return club


def by_fpl_id(fpl_id: int) -> Club:
    """Resolve an FPL team id to a canonical club."""
    try:
        return BY_FPL_ID[fpl_id]
    except KeyError as exc:
        raise UnknownClubError(f"fpl_id={fpl_id}") from exc
