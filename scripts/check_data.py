"""Data integrity checks that run in CI.

These guard the committed data files against the failures that are silent
rather than loud: a prediction that no longer names 20 valid clubs, a broadcast
listing that lost its verification date, a last-season dataset that stopped
adding up.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared import broadcasters
from shared.clubs import CLUBS, find
from shared.projection import final_table, last_season
from shared.scoring import InvalidTableError, validate_table

ROOT = Path(__file__).resolve().parents[1]
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        failures.append(message)


def main() -> int:
    print("canonical clubs")
    check(len(CLUBS) == 20, "exactly 20 clubs")
    check(len({c.short_name for c in CLUBS}) == 20, "short names unique")
    check(all(len(c.short_name) == 3 for c in CLUBS), "every short name is three letters")

    print("\nseeded predictions")
    seed = json.loads((ROOT / "shared" / "data" / "seed_predictions.json").read_text())
    allowed = [c.short_name for c in CLUBS]
    for prediction in seed["predictions"]:
        person = prediction["person"]
        try:
            validate_table(prediction["table"], allowed)
            print(f"  ok   {person}: a valid 20-club table")
        except InvalidTableError as exc:
            print(f"  FAIL {person}: {exc}")
            failures.append(f"{person} table")
        check(len(prediction["awards"]) == 5, f"{person}: five award picks")

    print("\nbroadcast listings")
    for country in ("UA", "US", "CA"):
        listing = broadcasters.for_country(country)
        check(listing is not None, f"{country}: a listing exists")
        if listing:
            check(bool(listing.provider), f"{country}: names a provider")
            check(bool(listing.verified_on), f"{country}: carries a verification date")

    print("\nlast season")
    data = last_season()
    table = data.get("table", [])
    check(len(table) == 20, "20 rows in last season's table")
    check(sum(r["played"] for r in table) == 760, "760 club-appearances (380 matches)")
    check(all(r["played"] == 38 for r in table), "every club played 38")
    goals_for = sum(r["goals_for"] for r in table)
    goals_against = sum(r["goals_against"] for r in table)
    check(goals_for == goals_against, "goals for and against balance")
    check(len(final_table()) == 17, "17 clubs carry over into this season")
    check(len(data.get("head_to_head", {})) == 272, "272 head-to-head results (17 x 16)")

    unmapped = [r["name"] for r in table if not r["in_league"]]
    check(len(unmapped) == 3, f"3 relegated clubs correctly unmapped: {', '.join(unmapped)}")
    for name in unmapped:
        check(find(name) is None, f"{name} does not resolve to a 26/27 club")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("All data checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
