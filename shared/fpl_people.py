"""Which FPL entry belongs to which person.

Nothing in either dataset links them: FPL knows real names and team names, this
league knows four code words. So the mapping is supplied once, stored, and
editable from ``/admin`` -- never inferred, because a wrong guess silently
attributes somebody's squad, captain and bench points to the wrong person for a
whole season.

An entry that appears in the league but is not mapped is reported rather than
dropped, so a fifth manager joining shows up as something to fix instead of
quietly vanishing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent / "data" / "fpl_mapping.json"


@dataclass(frozen=True, slots=True)
class EntryMapping:
    person: str
    entry_id: int
    entry_name: str
    player_name: str


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    if not DATA.exists():  # pragma: no cover
        return {"entries": []}
    data = json.loads(DATA.read_text())
    assert isinstance(data, dict)
    return data


@lru_cache(maxsize=1)
def by_entry_id() -> dict[int, EntryMapping]:
    return {
        int(e["entry_id"]): EntryMapping(
            person=str(e["person"]),
            entry_id=int(e["entry_id"]),
            entry_name=str(e.get("entry_name", "")),
            player_name=str(e.get("player_name", "")),
        )
        for e in _raw().get("entries", [])
    }


@lru_cache(maxsize=1)
def by_person() -> dict[str, EntryMapping]:
    return {m.person: m for m in by_entry_id().values()}


def person_for(entry_id: int) -> str | None:
    mapping = by_entry_id().get(entry_id)
    return mapping.person if mapping else None


def entry_for(person: str) -> int | None:
    mapping = by_person().get(person)
    return mapping.entry_id if mapping else None


def confirmed_on() -> str:
    return str(_raw().get("confirmed_on", ""))
