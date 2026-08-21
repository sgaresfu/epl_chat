"""Resolve a market to its rights holder.

Broadcast rights have no reliable free API, so this reads the maintained file in
``shared/data`` and lets ``/admin`` override an entry at runtime without a
redeploy. Every listing carries ``verified_on`` and is rendered with it, because
a confidently wrong channel is worse than an honestly dated one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent / "data" / "broadcasters.json"


@dataclass(frozen=True, slots=True)
class Listing:
    country: str
    provider: str
    url: str
    verified_on: str
    note: str = ""
    confidence: str = "verified"
    splits_round: bool = False


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    data = json.loads(DATA.read_text())
    assert isinstance(data, dict)
    return data


@lru_cache(maxsize=1)
def _premier_league() -> dict[str, Listing]:
    return {
        m["country"]: Listing(
            country=m["country"],
            provider=m["provider"],
            url=m.get("url", ""),
            verified_on=m.get("verified_on", ""),
            note=m.get("note", ""),
            splits_round=bool(m.get("splits_round")),
        )
        for m in _raw()["markets"]
    }


@lru_cache(maxsize=1)
def _champions_league() -> dict[str, Listing]:
    return {
        c["country"]: Listing(
            country=c["country"],
            provider=c["provider"],
            url=c.get("url", ""),
            verified_on=c.get("verified_on", ""),
            note=c.get("note", ""),
            confidence=c.get("confidence", "verified"),
        )
        for c in _raw().get("champions_league", [])
    }


def for_country(country: str, competition: str = "premier-league") -> Listing | None:
    table = _champions_league() if competition == "champions-league" else _premier_league()
    return table.get(country.upper())


def season_note() -> str:
    return str(_raw().get("note", ""))


def verified_on() -> str:
    return str(_raw().get("verified_on", ""))


def all_listings(competition: str = "premier-league") -> list[Listing]:
    table = _champions_league() if competition == "champions-league" else _premier_league()
    return sorted(table.values(), key=lambda listing: listing.country)
