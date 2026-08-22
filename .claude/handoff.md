# Prediction League 26/27 — handoff

**Live:** https://league-api-i6u5.onrender.com
**Repo:** https://github.com/sgaresfu/epl_chat (`main`, 40 commits)
**Cost:** $0/month
**Tests:** 447 backend, 64 frontend, all green. `./scripts/check.sh` runs every gate.

---

## Start here

```bash
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
cp .env.example .env          # fill the four code words + SESSION_SECRET
./.venv/bin/alembic upgrade head
./.venv/bin/python -m uvicorn services.api.main:app --port 8000
```

The api serves the React app, so `http://localhost:8000` is the whole site. For
frontend work, `cd apps/web && npm run dev` gives hot reload on :5173 and proxies
`/api` to :8000.

**Before every commit: `./scripts/check.sh`.** It runs ruff, format, mypy
--strict, pytest, data checks, preflight, tsc, vitest and the build — and reports
real exit codes. Piping a test run into `tail` reports *tail's* status; that let
a red suite through twice early on.

---

## Architecture, and where it departs from the brief

The brief specifies three services plus Redis plus Postgres. That is right for an
app with traffic and wrong for four people: it costs ~$35/month, and the split
buys nothing asyncio does not already provide at this size.

**What runs instead — one free web service:**

| Briefed | Actual | Why |
|---|---|---|
| Static site on a CDN | The api serves the React app | Two origins made the session cookie third-party. Every iOS browser is WebKit, so Safari dropped it and **nobody could sign in from a phone**. |
| Separate poller worker | `POLLER_IN_PROCESS=true`, an asyncio task | Saves $7. asyncio already keeps a slow upstream off other requests. |
| Redis for cache + pub/sub | In-process `MemoryCache` | Saves $10. One process needs no shared cache. |
| Render Postgres | External Neon | Render's free Postgres is **deleted after 30 days**, mid-season. |

**To restore the briefed shape:** set `POLLER_IN_PROCESS=false` and
`SERVE_FRONTEND=false`, add a `worker` service, a `keyvalue` service for
`REDIS_URL`, and a static site with `VITE_API_BASE`/`FRONTEND_ORIGIN`. No
application code changes — the cache layer already prefers Redis whenever
`REDIS_URL` reaches it. `tests/test_deployment_shape.py` asserts the blueprint
and the code agree. But budget for a custom domain, or the phones lock out again.

---

## Layout

```
shared/          scoring, canonical clubs, timezones, projection, models, config
  clubs.py       the canonical 20, with per-source aliases. Everything maps through this.
  scoring.py     pure functions. One implementation of the rules, called by every consumer.
  timezones.py   IANA only. Never an offset.
  projection.py  last season's results -> projected table
services/api/    routes, auth, SPA serving
services/poller/ the only code that calls an upstream
services/scheduler/  cron entrypoints (weekly, daily, hourly)
apps/web/        React app
scripts/         check.sh, preflight.py, check_data.py, export_openapi.py, verify_stream.py
```

---

## Decisions worth knowing

- **Projected table, promoted clubs** — 272 of 380 fixtures resolve to last
  season's identical match-up; the other 108 involve a promoted club and are
  modelled as 1-1 draws. Only rows where modelling *dominates* carry the badge
  (the promoted three) — every club plays them, so flagging any row with one
  modelled fixture would flag all twenty and mean nothing.
- **Leaderboard tie-break** — total, then exact hits, then champion correct, then
  earliest submission.
- **Calendar source** — a maintained JSON file. F1's only free option is
  community-run with no stability guarantee. *(Not built yet.)*
- **Last season's data** — FPL serves only the current season, so
  `scripts/build_last_season.py` builds `shared/data/season_2025_26.json` from
  openfootball. The computed table matches the published one on all 20 rows.
- **The Athletic** — not included. No public feed, paywalled, and the brief
  permits headlines only. Replaced by BBC Sport and the Guardian.
- **Type drift** — `apps/web/src/api/contract.ts` asserts every hand-written type
  is mutually assignable with the generated OpenAPI schema. It has caught four
  real drifts. Regenerate with `scripts/export_openapi.py` then `npm run gen:api`.

---

## Bugs found and fixed (the ones that would recur)

| Bug | Cost if unfixed |
|---|---|
| `Ø` does not NFKD-decompose | `Ødegaard` → `degaard`; a seeded award pick unsearchable |
| Alberta leaves DST 2026-11-01 (tzdata 2026c) | every TWZT kickoff an hour wrong from November |
| **FPL's `finished` flag lags full time by hours** | board said "live" an hour after full time; winner on 0 points |
| `parsedate_to_datetime` does not know `BST` | every headline stamped with the server's own offset |
| An alphabetical table is not a standing | somebody led the leaderboard by six before a ball was kicked |
| `fromService … property: host` yields the service *name* | frontend called `https://league-api-i6u5/...`; and an empty CORS list |
| Rate limit counted *successes* | four friends on one connection locked themselves out |
| Bench Boost ignored | two managers' totals understated by their whole bench |
| Guardian signs image URLs | resizing returned 401 on every Guardian photo |
| Inline `<span>` with `height` | progress bar rendered as a blob |

`scripts/preflight.py` now guards the deploy-config class of these. It rejects
invalid service types, paid-only fields on free plans, `property: host`, a
missing migration hook, and a driverless Postgres URL.

---

## What is built

Auth (code word → signed httpOnly cookie), the cache/pub-sub layer, the FPL
poller, the news poller, SSE, three cron jobs, and:

`/` home · `/table` (+ projected + matches) · `/stats` (players and teams) ·
`/predictions` (+ leaderboard + awards, and the picker at `/predictions/build`) ·
`/fpl` (live squads, captains, differentials, chips) · `/watch` · `/news` ·
`/chat` · `/admin`

Installable PWA with an offline shell — verified opening with no network.

---

## What is not built

- `/europe` — needs `FOOTBALL_DATA_KEY`
- Odds and drift — needs `ODDS_API_KEY`
- Line-ups — needs `API_FOOTBALL_KEY`
- `/calendar`, `/archive`
- Web push (VAPID keys exist in config; nothing sends)
- Shareable PNG export (Pillow is installed; nothing renders)
- The awards and Champions League halves of the picker — the 1–20 table is
  built, but award picks still come only from the seed file
- Manager photo tiles (§5 of the brief)

---

## Immediate next steps

1. **Set `YOUTUBE_API_KEY` in Render.** It is in the local `.env` but not on the
   server, which is why the video rail is empty. The six channel ids are already
   resolved and stored in `shared/data/youtube_channels.json`.
2. **Delete `league-web-i6u5`** — an orphaned static site. The api serves the app
   now. Stale bookmarks to it redirect, so nothing breaks either way.
3. **Rotate two credentials.** The Neon password and the YouTube key were both
   pasted into chat; treat them as exposed.
4. **Enable CI.** `gh auth refresh -s workflow && ./scripts/enable_ci.sh` — the
   workflow is preserved in `.ci-pending/` because the token lacked the scope.
5. Consider `plan: starter` (~$7/mo) on `league-api` if the table should stay
   live with nobody watching. On free it sleeps after 15 minutes and the poller
   sleeps with it.

---

## Open question

**Which FPL entry is which person** is stored in `shared/data/fpl_mapping.json`,
confirmed by the owner. If a fifth manager joins, `/api/fpl/standings` reports
them under `unmapped` rather than dropping them — add them to that file.
