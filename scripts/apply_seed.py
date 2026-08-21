"""Write the seeded predictions into a live database, overwriting existing rows.

Distinct from the seeding the api does on start, which deliberately never
overwrites: that protects a table somebody filed through the picker. This is
the deliberate override, for when the seed file itself is the correction --
a table submitted out of band, or one filed with an error that has since been
resolved.

Run: ``python scripts/apply_seed.py [person ...]``  (all four if none named)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.api.repository import save_prediction
from shared.clubs import CLUBS
from shared.scoring import validate_table
from shared.session import dispose, session

SEED = Path(__file__).resolve().parents[1] / "shared" / "data" / "seed_predictions.json"
ALL_CLUBS = [c.short_name for c in CLUBS]


def award_names(awards: dict[str, object]) -> dict[str, str]:
    """Seed awards carry the resolved FPL id; storage keeps the display name."""
    out: dict[str, str] = {}
    for key, value in awards.items():
        out[key] = str(value.get("name", "")) if isinstance(value, dict) else str(value or "")
    return out


async def main(only: list[str]) -> int:
    payload = json.loads(SEED.read_text())
    wanted = set(only)
    applied = 0

    for entry in payload.get("predictions", []):
        person = entry["person"]
        if wanted and person not in wanted:
            continue

        try:
            validate_table(entry["table"], ALL_CLUBS)
        except Exception as exc:
            print(f"  FAIL  {person}: {exc}")
            return 1

        async with session() as db:
            await save_prediction(
                db,
                person,
                entry["table"],
                award_names(entry.get("awards", {})),
                entry.get("champions_league", {}),
            )
        placeholder = any(
            isinstance(v, dict) and v.get("placeholder") for v in entry.get("awards", {}).values()
        )
        note = "  (awards are placeholders)" if placeholder else ""
        print(f"  ok    {person}: {entry['table'][0]} first, {entry['table'][-1]} last{note}")
        applied += 1

    await dispose()
    print(f"\nApplied {applied} prediction(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
