"""Build ``shared/data/season_2025_26.json`` from openfootball's free dataset.

Last season is needed in two places the FPL API cannot serve, because FPL only
ever exposes the current campaign:

* the **projected table**, which resolves each remaining fixture to last
  season's result for the identical match-up
* the **prediction preview**, which scores a draft table against a finished
  season

The source is openfootball/football.json (Public Domain). Two traps are handled
here rather than at read time:

* 27 of the 380 matches serialise their score as a bare ``[0, 0]`` list instead
  of ``{"ft": [0, 0]}``. Every one of them is a goalless draw, so a parser that
  only understands the dict shape silently discards all 27 -- which is enough to
  move eight clubs in the final table.
* Three clubs in last season's table (West Ham, Burnley, Wolves) were relegated
  and have no canonical 2026/27 entry. They are kept with ``in_league: false``
  so the final table stays honest, and skipped when resolving head-to-heads.

Run: ``python scripts/build_last_season.py``
Verified against the published final table on 2026-08-21; all 20 rows match.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.clubs import find

SOURCE = "https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/en.1.json"
OUT = Path(__file__).resolve().parents[1] / "shared" / "data" / "season_2025_26.json"

# Awards, from the published season records. The Playmaker award is left blank
# rather than guessed -- an invented winner would score somebody 5 points they
# did not earn.
AWARDS: dict[str, list[str]] = {
    "golden_boot": ["Haaland"],
    "golden_glove": ["Raya"],
    "player_of_the_season": ["Bruno Fernandes"],
    "defender": [],
    "playmaker": [],
}


def full_time(match: dict[str, Any]) -> list[int] | None:
    """Read a score in either shape openfootball emits."""
    score = match.get("score")
    if isinstance(score, dict):
        ft = score.get("ft")
        return list(ft) if isinstance(ft, list) and len(ft) == 2 else None
    if isinstance(score, list) and len(score) == 2:
        return list(score)
    return None


def main() -> int:
    import httpx

    print(f"fetching {SOURCE}")
    response = httpx.get(SOURCE, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()

    matches = payload["matches"]
    scored = [(m, full_time(m)) for m in matches]
    usable = [(m, s) for m, s in scored if s]
    print(f"  {len(matches)} matches, {len(usable)} with a full-time score")
    if len(usable) != 380:
        print(f"  ERROR: expected 380 scored matches, got {len(usable)}", file=sys.stderr)
        return 1

    tally: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    for match, score in usable:
        home_name, away_name = match["team1"], match["team2"]
        home_goals, away_goals = score

        for name in (home_name, away_name):
            tally.setdefault(name, {"played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0})

        tally[home_name]["played"] += 1
        tally[away_name]["played"] += 1
        tally[home_name]["gf"] += home_goals
        tally[home_name]["ga"] += away_goals
        tally[away_name]["gf"] += away_goals
        tally[away_name]["ga"] += home_goals

        if home_goals > away_goals:
            tally[home_name]["won"] += 1
            tally[away_name]["lost"] += 1
        elif away_goals > home_goals:
            tally[away_name]["won"] += 1
            tally[home_name]["lost"] += 1
        else:
            tally[home_name]["drawn"] += 1
            tally[away_name]["drawn"] += 1

        home_club, away_club = find(home_name), find(away_name)
        results.append(
            {
                "date": match["date"],
                "home": home_club.short_name if home_club else None,
                "away": away_club.short_name if away_club else None,
                "home_name": home_name,
                "away_name": away_name,
                "home_goals": home_goals,
                "away_goals": away_goals,
            }
        )

    rows = []
    for name, t in tally.items():
        club = find(name)
        rows.append(
            {
                "club": club.short_name if club else None,
                "name": name,
                "in_league": club is not None,
                "played": t["played"],
                "won": t["won"],
                "drawn": t["drawn"],
                "lost": t["lost"],
                "goals_for": t["gf"],
                "goals_against": t["ga"],
                "goal_difference": t["gf"] - t["ga"],
                "points": t["won"] * 3 + t["drawn"],
            }
        )
    rows.sort(key=lambda r: (-r["points"], -r["goal_difference"], -r["goals_for"], r["name"]))
    for index, row in enumerate(rows, start=1):
        row["position"] = index

    head_to_head = {
        f"{r['home']}|{r['away']}": [r["home_goals"], r["away_goals"]]
        for r in results
        if r["home"] and r["away"]
    }

    document = {
        "$comment": (
            "Generated by scripts/build_last_season.py. Do not hand-edit. "
            "Source: openfootball/football.json (Public Domain). "
            "Needed because the FPL API serves only the current season."
        ),
        "season": "2025-26",
        "source": SOURCE,
        "licence": "Public Domain (openfootball)",
        "generated_from_matches": len(usable),
        "relegated": [r["name"] for r in rows if not r["in_league"]],
        "table": rows,
        "head_to_head": head_to_head,
        "awards": AWARDS,
    }

    OUT.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    print(f"  wrote {OUT.relative_to(Path.cwd())}")
    print(f"  table rows: {len(rows)}  head-to-head pairs: {len(head_to_head)}")
    print(f"  champions: {rows[0]['name']} on {rows[0]['points']}")
    print(f"  relegated: {', '.join(document['relegated'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
