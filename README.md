# Prediction League 26/27

Premier League predictions, a fantasy mini-league and a watch log, for four
friends in four timezones. Real data from real APIs, shipped working.

```
apps/web            React app (static site, deployed to a CDN)
services/api        FastAPI: routes, SSE, auth  — reads cache only
services/poller     upstream clients, cache writer, publisher — the only process that calls an upstream
services/scheduler  cron entrypoints
shared/             scoring, canonical clubs, timezones, projection, models
migrations/         Alembic
scripts/            data builders and verification
```

---

## Quick start

```bash
# 1. Backend
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
cp .env.example .env          # fill in the four code words and a session secret
./.venv/bin/alembic upgrade head

# 2. Run the api with a one-off cache warm (local only; see note below)
echo "SEED_ON_START=true" >> .env
./.venv/bin/uvicorn services.api.main:app --port 8000

# 3. Frontend, in another terminal
cd apps/web && npm install && npm run dev     # http://localhost:5173
```

Or the whole backend at once:

```bash
docker compose up             # api, poller, Postgres and Redis
```

`SEED_ON_START` exists only so a clean clone shows real data without running a
second process. It refuses to run outside `ENVIRONMENT=local`, because the
architecture depends on the api never calling an upstream.

---

## Every secret, and where to get it

Set these in a Render **environment group** shared by all three services. The
`.env.example` file mirrors them for local work. Work down the list in order.

| Variable | Where it comes from | Needed for |
|---|---|---|
| `DATABASE_URL` | Render → New → Postgres → *Internal Connection String* | everything persistent |
| `REDIS_URL` | Render → New → Key Value → *Internal Connection String* | cache and pub/sub |
| `SESSION_SECRET` | `openssl rand -hex 32` | signing the session cookie |
| `CODE_COYG` `CODE_AURE` `CODE_TWZT` `CODE_BULBA` | choose four; treat them as real credentials | login |
| `FOOTBALL_DATA_KEY` | [football-data.org](https://www.football-data.org/client/register) → free tier → the key is emailed | Champions League |
| `API_FOOTBALL_KEY` | [api-football.com](https://dashboard.api-football.com/register) → free tier → Dashboard → API key | confirmed line-ups |
| `ODDS_API_KEY` | [the-odds-api.com](https://the-odds-api.com/#get-access) → free tier → key emailed | bet365 prices |
| `YOUTUBE_API_KEY` | Google Cloud console → new project → enable **YouTube Data API v3** → Credentials → API key | video uploads |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | `npx web-push generate-vapid-keys` | web push |
| `R2_ACCOUNT_ID` `R2_ACCESS_KEY` `R2_SECRET_KEY` `R2_BUCKET` | Cloudflare dashboard → R2 → create bucket → *Manage API tokens* | uploaded images |
| `SENTRY_DSN` | Sentry → project → Settings → Client Keys | error reporting (optional) |
| `FRONTEND_ORIGIN` | the deployed web service's URL | CORS and the cookie domain |

**A missing key is not fatal.** The panel it powers shows a clear message
naming what is missing; everything else keeps working. `/admin` lists them.

---

## Deploying

1. Push the repo to GitHub.
2. Render → **Blueprints** → *New Blueprint Instance* → point it at `render.yaml`.
   This creates the static site, the api, the poller, Redis, Postgres and three
   cron jobs.
3. Fill in the `league-secrets` environment group (the table above).
4. Set `VITE_API_BASE` on `league-web` to the api service's URL, and
   `FRONTEND_ORIGIN` on the api to the web service's URL.
5. Run migrations once: `alembic upgrade head` from the api service's shell.

### Deploying to Render's default hosts

The blueprint wires the two cross-references itself, so nothing is pasted by
hand: the static site receives the api's host as `VITE_API_BASE`, and the api
receives the static site's host as `FRONTEND_ORIGIN`. Render supplies a *host*
rather than a full URL, so both sides prefix `https://` themselves.

With the default `*.onrender.com` hosts the two share no usable parent domain,
so `COOKIE_DOMAIN` stays empty and the session cookie is third-party:
`SameSite=None; Secure`. That works in Chrome and Firefox, but **Safari's
tracking prevention and any "block third-party cookies" setting can drop it**,
which presents as a login that appears to succeed and then immediately forgets
you. If that happens, attach a custom domain to both services and set
`COOKIE_DOMAIN=.yourdomain.com` — the cookie becomes first-party and the
problem disappears.

### The cookie, which is the part that bites

The frontend is on a CDN and the api is a separate service, so they are
cross-origin unless they share a parent domain.

- **The clean way.** Put both under one parent — `league.example.com` and
  `api.example.com`. `SameSite=Lax` then works with no special handling.
- **The fallback.** No shared parent means `SameSite=None; Secure` plus CORS
  `allow_credentials=True` and an explicit origin allow-list. Never `*` —
  browsers reject a wildcard when credentials are sent.

`EventSource` sends cookies only with `withCredentials: true`, and the SSE
response needs the same CORS credential headers. Verify it against the deployed
frontend rather than assuming; it behaves differently from `fetch` in local dev.

```bash
./.venv/bin/python scripts/verify_stream.py    # login, p95, SSE delivery, CORS
```

---

## Quota discipline

Two of the brief's stated intervals overrun their free tiers. Both ceilings are
enforced in code and reported on `/admin`.

| Source | Free tier | Briefed interval would need | What runs instead |
|---|---|---|---|
| The Odds API | 500/month | every 30 min ≈ **1,440/month** | fetched only in a window around each round, hard budget of 450 |
| API-Football | 100/day | live event polling ≈ **240 per match** | scores come from FPL (free, unmetered); this is reserved for on-demand line-ups, budget 85/day |

FPL has no key and no quota, so it carries the table, fixtures, live points and
the mini-league. One upstream poll serves all four people.

---

## Decisions taken

The brief left three open, plus a fourth that emerged.

- **Projected table, promoted clubs.** Coventry, Hull and Ipswich have no
  Premier League record, so those fixtures resolve as 1-1 draws. 272 of 380
  remaining fixtures are *derived* from last season's identical match-up; 108
  are *modelled*. Only rows where modelling dominates (the promoted three) carry
  the `modelled` badge — every club plays the promoted three, so flagging any
  row with a single modelled fixture would flag all twenty and mean nothing.
  The other rows carry an honest "6 of 38 modelled" note instead.
- **Leaderboard tie-break.** Total, then exact positions hit (precision beats
  spreading the risk), then champion called correctly, then earliest submission
  — so filing early is never a disadvantage.
- **Calendar data source.** A maintained JSON file in the repo. F1's only free
  option is the community-run Jolpica/Ergast API with no stability guarantee,
  and boxing and UFC schedules have no free API at all. A file that is honestly
  dated beats an endpoint that disappears mid-season.
- **Last season's data.** The FPL API serves only the current season, so the
  projected table and the prediction preview would have nothing to work from.
  `scripts/build_last_season.py` builds `shared/data/season_2025_26.json` from
  openfootball (Public Domain); the computed table matches the published final
  table on all 20 rows.

---

## Testing

```bash
./.venv/bin/python -m pytest -q          # 269 tests
./.venv/bin/mypy shared services         # strict
./.venv/bin/ruff check shared services tests scripts
./.venv/bin/python scripts/check_data.py # committed-data integrity
cd apps/web && npm test && npm run typecheck
```

The three areas the brief predicted would break are the three with the heaviest
coverage — and all three did break during the build:

| Bug found | What it would have cost |
|---|---|
| `Ø` does not NFKD-decompose, so `Ødegaard` folded to `degaard` | COYG's own Playmaker pick unsearchable |
| Apostrophes and periods split tokens | `NOTTM FOREST` ≠ `Nott'm Forest`; `Everton F.C.` unresolvable |
| Alberta leaves DST on 2026-11-01 (tzdata 2026c) | every TWZT kickoff an hour wrong from November |
| `parsedate_to_datetime` does not know `BST` | every Sky headline stamped with the server's own local offset |
| An alphabetical table is not a standing | somebody led the leaderboard by six before a ball was kicked |

That last one is why `tzdata` is a pinned dependency: a slim container's system
zoneinfo may predate the rule. `America/Edmonton` stays at UTC−6 and relabels to
CST while true Mountain Time falls back to UTC−7, so the Michigan↔Alberta gap
goes 2 → 1 → 2 across a single season.

---

## What is not built

Honest status, rather than a claim of completeness.

**Working end to end:** canonical clubs, scoring engine, timezone conversion,
season timeline, auth with the cross-origin cookie, the cache and pub/sub layer,
the FPL poller, the Sky news poller, SSE, the three cron jobs, `/`, `/table`
(actual and projected), `/fixtures` with the watch toggle, `/predictions`
(all four filed, redacted, server-locked), the picker at `/predictions/build`,
`/leaderboard` with head-to-head, `/fpl` standings, `/watch`, `/news`, `/admin`.

**Shipped, but legitimately empty until football happens:** `/leaderboard`
scores through the real engine and has nothing to score until matches are
played, and says so. `/watch` opens the moment a match kicks off. `/news` shows
Sky headlines now and names the missing YouTube key.

**Not started:** `/europe`, `/calendar`, `/chat`, `/archive`, web push, the PWA
service worker, the shareable PNG export, odds and line-up clients, YouTube
uploads (needs a key), the manager photo tiles, and the awards and Champions
League halves of the picker — the 1-20 table is built, but award picks still
come from the seed file.

**Unverified:** the Docker images have never been built and `render.yaml` has
never been applied — neither Docker nor a Render account was available here.
Both are written against the current Render blueprint spec but should be treated
as a first deploy, not a proven one.
