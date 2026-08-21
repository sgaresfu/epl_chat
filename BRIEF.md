# Build: Prediction League 26/27

A production web app for four friends who run a Premier League prediction competition and
an FPL mini-league together. It ships working, with real data from real APIs, on day one.

Read this whole brief before writing code. Then reply with a short plan — stack, route
list, build order, and anything here you think is wrong — and start building. Don't ask
permission between phases; work through them and report at the end of each.

---

## 1. The people

| Person | Code word | City | IANA timezone |
|---|---|---|---|
| COYG | `coyg` | Lviv, Ukraine | `Europe/Kyiv` |
| AURE | `aure` | Michigan, USA | `America/Detroit` |
| TWZT | `twzt` | Alberta, Canada | `America/Edmonton` |
| BULBA | `bulba` | Alaska, USA | `America/Anchorage` |

Everything in the app is aware of who is logged in: which clock is highlighted, whose
watch-log tap it is, whose FPL squad is "mine", which broadcaster listing is theirs.

**Timezones are IANA strings, never fixed offsets.** The US, Canada and Ukraine change
clocks on different dates; a hardcoded offset silently breaks for two weeks each spring
and autumn. All conversion goes through `Intl.DateTimeFormat` with the person's zone.

---

## 2. Stack

Built to feel like a team of senior engineers shipped it: typed end to end, tested where it
matters, observable, and fast because of architecture rather than tricks.

**Frontend** — React 18 + TypeScript, Vite, deployed as a **static site** to a CDN
as a **Render Static Site**, so the whole
stack lives in one dashboard with one `render.yaml`. Never served from the Python process.
- TanStack Query for server state, cache and invalidation
- TanStack Router or React Router with typed routes and code splitting per route
- Hand-written CSS with custom properties. No CSS framework.
- Recharts for the two charts (leader over time, cumulative goals)
- Vitest + Testing Library

**Backend** — **Python 3.12 + FastAPI** on **Render**, as three services from one repo:

| Service | Type | Job |
|---|---|---|
| `api` | Render Web Service, always on | REST + SSE. Serves from cache; never calls an upstream on a user request |
| `poller` | Render Background Worker | The only process that talks to upstream APIs. Writes cache, publishes changes |
| `scheduler` | Render Cron Jobs | Weekly snapshots, Monday summaries, daily line-of-the-day |

- **Postgres** (Render) for state — SQLAlchemy 2.0 typed ORM, Alembic migrations
- **Redis / Render Key Value** for the cache and for pub/sub between poller and api
- **Cloudflare R2** for uploaded images, S3-compatible via boto3, signed URLs
- Pydantic v2 models at every boundary; `httpx.AsyncClient` with pooling, timeouts and
  `tenacity` retries for upstreams
- `structlog` JSON logging, Sentry for errors, `/healthz` and `/readyz`
- `pytest` + `pytest-asyncio` + `respx` for mocked upstreams
- `ruff` + `mypy --strict` + `pre-commit`; GitHub Actions runs lint, types and tests on
  every push and blocks merge on failure
- `Dockerfile` per service, `render.yaml` blueprint so the whole stack deploys from one file

**Always-on matters.** Use Render's paid Starter tier for `api` and `poller` — the free
tier sleeps, and a cold start on a page showing live scores is exactly the failure this
architecture exists to avoid.

**Why not one Python process serving everything:** if the API also polls upstreams, a slow
FPL response blocks user requests, and four browsers open on match day means four times the
upstream calls. Splitting the poller out is what keeps the site instant and the quotas
intact.

### Shared logic across two languages

The scoring engine is the one piece both sides need. It lives in Python
(`shared/scoring.py`) as the single source of truth, fully unit tested. The frontend does
not reimplement it — it renders what `/api/leaderboard` returns. Where the UI needs an
instant preview (the prediction picker showing "this would have scored 34 last season"),
call a dedicated `POST /api/predictions/preview` rather than duplicating the rules in
TypeScript. **Two implementations of the scoring rules is a bug waiting to happen.**

```
/apps/web            React app
/services/api        FastAPI: routes, SSE, auth
/services/poller     upstream clients, cache writer, publisher
/services/scheduler  cron entrypoints
/shared              scoring, canonical club table, timezone helpers, Pydantic models
/migrations          Alembic
render.yaml
README.md            every secret, where to get it, exact deploy steps, how to seed
```

---

## 3. Auth

One login screen, one field: a code word. Compare against the environment secrets
`CODE_COYG`, `CODE_AURE`, `CODE_TWZT`, `CODE_BULBA` using a constant-time comparison.
Rate-limit 10 attempts per IP per hour. On success set an httpOnly, Secure session cookie,
90 days, signed with `SESSION_SECRET`. Every route except login requires it, and the
session resolves the person for every read and write.

**The cookie is the one thing that will bite you**, because the frontend is on a CDN and
the API is on Render — two origins. Solve it the clean way: serve both from one parent
domain (`league.<domain>` and `api.<domain>`), set `Domain=.<domain>` and `SameSite=Lax`,
and the cookie just works. Only if that isn't possible, fall back to `SameSite=None;
Secure` with CORS `allow_credentials=True` and an explicit origin allow-list — never `*`,
which browsers reject with credentials anyway.

`EventSource` sends cookies only with `withCredentials: true`, and the SSE response needs
the same CORS credentials headers. Test the stream while logged in from the deployed
frontend before assuming it works — it behaves differently from `fetch` in local dev.

---

## 4. Data sources

All fetched by the `poller` service. The API and the browser only ever read the cache.

| Source | Provides | Auth | Cache |
|---|---|---|---|
| `fantasy.premierleague.com/api/` | table, fixtures, player stats, live points, mini-league | none | 60s live / 10m static |
| football-data.org v4 | Champions League | `X-Auth-Token` | 15m |
| API-Football v3 | confirmed line-ups, live match events | `x-apisports-key` | 5m |
| The Odds API v4 | bet365 prices (`soccer_epl`, `h2h`) | `apiKey` param | 30m |
| Sky Sports RSS | news | none | 15m |
| The Athletic | headlines + links only (paywalled — never mirror text) | none | 30m |
| YouTube Data API v3 | new uploads | API key | 30m |

**Full environment list** — put these in a Render environment group shared by all three
services, and mirror them in `.env.example`:

```
DATABASE_URL              Render Postgres
REDIS_URL                 Render Key Value
SESSION_SECRET            random 32+ bytes
CODE_COYG CODE_AURE CODE_TWZT CODE_BULBA
FOOTBALL_DATA_KEY         football-data.org, free tier
API_FOOTBALL_KEY          api-football.com, free tier
ODDS_API_KEY              the-odds-api.com, free tier
YOUTUBE_API_KEY           Google Cloud console, YouTube Data API v3 enabled
VAPID_PUBLIC_KEY VAPID_PRIVATE_KEY
R2_ACCOUNT_ID R2_ACCESS_KEY R2_SECRET_KEY R2_BUCKET
SENTRY_DSN                optional
FRONTEND_ORIGIN           for CORS and cookie domain
```

The README says where each one comes from, in order, so setup is a checklist and not a
scavenger hunt.

### Quota discipline — a hard requirement

- **API-Football: 100 calls/day.** One call per matchday to resolve fixture IDs. Line-ups
  fetched only when a user opens a specific match. Live events polled **only while a match
  is actually in play** — never on a schedule when nothing is live.
- **The Odds API: 500 calls/month.** One call fetches the whole round; never one per match.
  Filter `bookmakers` to **bet365** and show only its prices. If bet365 is absent for a
  region, say so rather than silently showing another book. Surface
  `x-requests-remaining` on an admin page.
- **The poller writes the cache; the api and the frontend only read it.** No user action
  triggers an upstream fetch except opening a match for line-ups.
- If an upstream is down, serve the last good payload with a visible staleness note. A
  blank screen because someone's API had a bad afternoon is a bug, not an edge case.
- Missing key ⇒ that panel shows a clear message; the rest of the site works.
- Log every upstream call with source, latency and quota headers, so the admin page shows
  real consumption rather than an estimate.

### Integration traps — handle these first

- **Club names differ across every source.** FPL says `Spurs`, Odds API says
  `Tottenham Hotspur`, API-Football says `Tottenham`. Build **one canonical club table** in
  `/shared`, keyed by FPL `short_name`, with an alias list per source and per-club colours.
  Everything maps through it. Build this before anything else — it's what breaks silently
  in November otherwise.
- **Fixture IDs differ across sources.** Match on kickoff date + canonical club IDs, never
  on name equality.
- FPL returns 503 around deadlines and at season rollover. Retry with backoff, serve cache.
- Player names carry diacritics (Ødegaard, Magalhães, Guimarães). Normalise for search,
  render with them intact.

---

## 5. Design

The reference is **premierleague.com for structure** and **Apple for visual language**.
A shipped mockup, `design-mockup.html`, is the direction — match its type scale, spacing
and restraint. Improve on it; do not regress from it.

### Tokens

```
--ink        #1D1D1F    primary text
--ink-2      #6E6E73    secondary
--ink-3      #86868B    tertiary, labels
--bg         #FFFFFF
--bg-2       #F5F5F7    tiles, panels, inset surfaces
--line       #D2D2D7    borders
--line-2     #E8E8ED    hairline separators
--blue       #0071E3    the only action colour
--green      #30D158    win
--red        #FF3B30    loss
--amber      #FF9F0A    warning
radius       9px controls · 14px inset blocks · 22px tiles · 28px large panels
shadow       0 4px 24px rgba(0,0,0,.06) — used sparingly
```

Club colours are the **only** other colour on the page, and they appear only in crests.

### Type

System stack — `-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
"Helvetica Neue", Arial, sans-serif`. On the phones these people use, that resolves to SF
Pro. **Do not load a webfont.**

Scale, with intent:
- Hero 64/1.05, weight 600, tracking −0.028em
- Section heading 32/1.1, weight 600, tracking −0.024em
- Lead paragraph 21/1.38, weight 400, colour `--ink-2`
- Body 17/1.47
- Data cell 16, secondary cell 15
- Label 12–13, colour `--ink-3`, uppercase only for eyebrows
- All numerals tabular

### Layout and components

- Max width 980px, 22px gutters, sections separated by 64px and a hairline rule
- Table rows 58px, hairline separators, **no zebra striping, no gridlines, no boxes**
- Crests: solid colour discs, 32px in tables, 44px in the match board, three-letter
  monogram, white text (dark text on light club colours)
- Form: 8px coloured dots, not lettered squares
- Segmented control for Actual / Projected — the iOS pattern
- Buttons: 44px, pill radius, filled blue for primary, plain blue text for secondary
- Chips: 1px border, pill, white ground; filled dark when active; green tinted when done
- Nav: 48px, sticky, translucent with `backdrop-filter: saturate(180%) blur(20px)`

### Anti-brief — none of this ships

- Gradient heroes, glassmorphism, neon, glow, drop shadows on everything
- Gold-and-purple ornament, bevels, glossy gradients, text shadows
- Emoji as iconography
- Every module wrapped in the same bordered card with the same coloured header
- Webfonts standing in for SF Pro
- Decorative colour anywhere colour isn't carrying information

### Photography

A tile row featuring Arsène Wenger (2004), José Mourinho at Chelsea (2006) and Rafa Benítez
at Liverpool (2005) — the one nod to the era, and the only place the site is allowed to feel
nostalgic. **Freely licensed images only** (Wikimedia Commons or equivalent). Never hotlink
press-agency photos. Store attribution with each image and render a credit. If no properly
licensed photo exists from that year, use the closest licensed one and state the year
honestly rather than substituting a modern shot.

### Quality floor

Mobile first — three of the four watch matches on a phone. Semantic `<table>` for tabular
data. Keyboard navigable, visible focus rings, WCAG AA contrast, `prefers-reduced-motion`
respected. Apple's language is minimal, so it lives or dies on spacing and alignment
precision; there's no ornament to hide behind.

---

## 6. Routes

### `/` Home
- Hero: the next match, countdown in the logged-in person's timezone, broadcaster for each
  of the four cities beside each city's kickoff time
- During a match: live score and minute. After: result and what it did to the standings
- **Season timeline**: progress bar 21 Aug 2026 → 30 May 2027 with day count, gameweeks
  played of 38, matches remaining of 380, and that person's own watched count. Mark Boxing
  Day, February deadline day, final day. **Computed from fixture data and the current
  date** — a stale hardcoded counter is worse than none
- Line of the day: one generated sentence tying the table to someone's prediction
- Standings tiles: prediction leaderboard and live FPL
- Manager photo tiles
- Latest: news, newest video, On This Day (2004–2008)

### `/predictions`
- Build a full 1–20 table from scratch. **The picker is the most important screen on the
  site at season start and must be genuinely pleasant**: searchable dropdown per position
  with crest and club name, already-picked clubs disabled and annotated with where they
  sit, drag to reorder once populated, keyboard and touch equal citizens. No duplicates.
  No submitting with gaps.
- Awards: Golden Boot, Golden Glove, Defender, Playmaker, Player of the Season — player
  search backed by the FPL player list, not free text
- Champions League: winner, both finalists, top scorer
- **Hard lock at 2026-08-21T19:00:00Z**, enforced server-side. Editable before, read-only
  forever after, submission timestamp displayed. A client-side check is not a lock.

Seed these two:

**COYG** — Arsenal, Man City, Liverpool, Chelsea, Man Utd, Aston Villa, Bournemouth,
Spurs, Crystal Palace, Brentford, Newcastle, Brighton, Fulham, Sunderland, Nott'm Forest,
Ipswich, Leeds, Hull, Everton, Coventry.
Awards: Haaland, Raya, Gabriel, Ødegaard, Rice. CL: Arsenal to win, Arsenal v Real Madrid,
Gyökeres top scorer (marked draft until confirmed).

**AURE** — Arsenal, Man City, Chelsea, Liverpool, Spurs, Man Utd, Brighton, Bournemouth,
Aston Villa, Newcastle, Nott'm Forest, Sunderland, Brentford, Leeds, Everton, Crystal
Palace, Fulham, Coventry, Ipswich, Hull.
Awards: Isak, Raya, Jérémy Jacquet, Cherki, Rice. CL: Man City to win, Man City v Bayern,
Mbappé top scorer (draft).

TWZT and BULBA are unfiled. Their slots stay open until the lock, then close empty.

### `/table`
- Live table computed from finished fixtures
- Form guide, last five, all 20
- **Projected table**: every remaining fixture resolved to last season's result for the
  identical match-up, added to current points. Segmented toggle against the actual table.
- **Top scorer race**: live goal standings plus a cumulative-goals curve per player over
  the season, so you can see who is accelerating
- **Transfer feed** during the window — official completed moves, club and fee where known
- Discipline table; table without penalties
- Fixture difficulty, next six rounds

### `/fixtures`
- Auto-updating list; reflect schedule changes when a match moves
- **Every fixture shows kickoff in all four cities**, each with its broadcaster
- bet365 1X2 prices with drift ("Arsenal 1.40 → 1.65 this week") from stored hourly history
- Tap a match: confirmed line-ups with formation, live events, full odds
- **"I watched this"** — opens at kickoff, closes 12 hours after full time
- Derby badge on the big ones

### `/watch`
- Counts, percentage of matches, estimated hours (matches × 2)
- Night medal: matches watched after midnight in that person's own timezone
- Streak: consecutive rounds without missing your club
- Who's watching right now

### `/fpl`
Mini-league **412955**. Read entry IDs from the league standings endpoint — do not ask for
them separately. Map FPL entries to the four people on first sync; store the mapping.
- Live standings and live gameweek points
- Every squad live: XI, bench, captain, per-player points
- Captain comparison for the round
- Differentials — players unique to one manager
- Team value, transfers made, gameweeks since last transfer
- Chips used and remaining
- Bench points wasted, running total
- Best gameweek per person and the league record
- **Projected points**: project each squad's round from every player's mean points per
  gameweek this season. Show the sample size; don't project from fewer than three
  appearances. Early-season means are noisy and the UI must say so.
- **Suggested transfers**: flag players weak on points per million, facing a hard fixture
  run, or trending down on minutes. For each, propose a replacement at a similar price
  that fits the manager's actual remaining budget and free transfers. Show the reasoning,
  not just the name. Label it as a suggestion, not a guarantee.

### `/leaderboard`
Scoring: **3** per exact position, **1** for within one place, **5** per correct award,
**10** for a perfect top four, **15** for champion plus all three relegated.
- Live standings, current leader
- Leader-over-time chart from weekly snapshots
- Prediction form — points gained over the last five rounds
- Flop of the week — whose prediction diverged most this round
- Cursed pick — your highest-placed club currently in the relegation zone
- "If the season ended today"
- Head to head between any two people: agreements and biggest gaps

### `/europe`
Champions League standings, fixtures in four timezones, everyone's CL calls.

### `/news`
Sky Sports items, Athletic headlines with outbound links, YouTube uploads.

Channels: **The Overlap**, **The Rest Is Football**, **Sky Sports Premier League**,
**Premier League** (official), **Let's Talk FPL**, and **Єврофутбол** (Ukrainian-language
football channel). Resolve every channel ID via the YouTube API at setup and store the IDs
in the database — do not hardcode IDs you haven't verified. For Єврофутбол, search by name; if
several plausible channels return, list the candidates in the README rather than guessing.

### `/calendar`
F1 race weekends, major boxing and UFC cards, big finals — each in all four timezones. Use
a free API if a good one exists; otherwise a maintained JSON file in the repo. Say which
you chose and why.

### `/chat`
- Quote of the day; quotes pinned to a club, player or match and resurfaced later
- Weekly poll, four votes, archived permanently
- Settled-bets scoreboard — no money, just a record
- Moments: screenshots and clips in R2, with captions and who posted
- Season timeline: every vote, quote, record and milestone in one feed
- **Shareable image**: render the current league table or leaderboard to a PNG sized for a
  chat message, in the site's own visual language. Generate it server-side in Python
  (Pillow, or render SVG and convert); do not screenshot the DOM.

### `/archive`
26/27 as the first season. Structure so 27/28 slots in without a rewrite.

### `/admin`
Odds credits remaining, cache ages per source, cron run log, broadcaster editor.

---

## 7. API surface

Implement exactly these on the `api` service. Everything the frontend needs comes from this
list; the browser never calls an upstream directly, and neither does `api` — it reads the
cache the poller fills.

```
POST   /api/session                 { code }  -> sets cookie, returns { person }
DELETE /api/session                 sign out
GET    /api/me                      person, timezone, city, preferences
GET    /api/stream                  SSE: live scores, FPL points, odds moves

GET    /api/table                   live table + form, from cache
GET    /api/table/projected         projected table + which rows are modelled
GET    /api/fixtures?from&to        fixtures, kickoffs in UTC, broadcaster block per city
GET    /api/fixtures/:id            one match: odds, events, watch state for all four
GET    /api/fixtures/:id/lineups    on demand only, 5m cache
GET    /api/odds                    whole round, bet365 only, with drift history
GET    /api/stats/scorers           goal standings + cumulative series
GET    /api/stats/discipline
GET    /api/stats/no-penalties
GET    /api/stats/difficulty        next six rounds per club
GET    /api/transfers               completed moves in the current window

GET    /api/predictions             all four, redacted before lock for anyone but the owner
PUT    /api/predictions             owner only, 403 after the lock
POST   /api/predictions/preview     score a draft table against a given season
GET    /api/leaderboard             standings, form, flop of the week, cursed picks
GET    /api/leaderboard/history     weekly snapshots for the chart
GET    /api/h2h?a=&b=               agreements and gaps between two people

GET    /api/fpl/standings           mini-league 412955
GET    /api/fpl/squads?gw=          all four squads, live points
GET    /api/fpl/projection?gw=      projected points + sample sizes
GET    /api/fpl/suggestions         flagged players + replacements + reasoning

GET    /api/watch                   counts, hours, night medals, streaks
POST   /api/watch                   { fixtureId } toggle, window-checked server-side
POST   /api/presence                heartbeat while a match page is open
GET    /api/presence                who is watching right now

GET    /api/europe/standings
GET    /api/europe/fixtures
GET    /api/news                    Sky items, Athletic headlines, YouTube uploads
GET    /api/calendar                other sport, next 30 days

GET    /api/chat/quotes             POST to add
GET    /api/chat/poll               POST to vote
GET    /api/chat/bets               POST to settle
GET    /api/chat/moments            POST returns a signed R2 upload URL
GET    /api/timeline                merged season feed

GET    /api/admin/status            cache ages, cron log, odds credits remaining
PUT    /api/admin/broadcasters      edit a listing without redeploying
POST   /api/push/subscribe
```

Every request and response is a Pydantic v2 model — FastAPI then generates the OpenAPI
schema, and the frontend's types are generated from it (`openapi-typescript`) so the two
sides can't drift. Every mutation resolves the person from the session server-side; never
trust a `who` field from the client.

---

## 8. Live data — how it actually flows

This is the part that makes the site feel alive. Get it right before adding features.

```
upstream APIs → poller → Redis (cache + pub/sub) → api → SSE → browsers
```

- The **poller** is the only process making upstream calls. It runs a loop per source with
  its own interval: FPL live points every 30s **while matches are in play**, odds every 30
  minutes, news every 15, nothing at all when no match is live.
- After each fetch it writes the normalised payload to Redis and, **only if the payload
  changed**, publishes a diff on a channel (`live:scores`, `live:fpl`, `live:odds`).
- The **api** serves every GET straight from Redis — no upstream call is ever on a user's
  critical path. Target p95 under 100ms.
- `GET /api/stream` is a **Server-Sent Events** endpoint. It subscribes the connection to
  the relevant channels and pushes events as they publish. SSE, not WebSockets: the traffic
  is one-directional, it reconnects automatically, and it survives proxies. Send a comment
  heartbeat every 20s so idle connections don't get culled.
- The frontend consumes the stream with TanStack Query: an event patches the cached query
  rather than triggering a refetch. Scores change under the user's eye with no spinner and
  no full reload.
- Fall back to polling `/api/table` every 60s if the stream drops — and show a small
  reconnecting indicator rather than silently going stale.

One upstream poll serves all four people. That is simultaneously the fast answer and the
quota-safe one.

---

## 9. Data model (Postgres)

Sketch; adjust as needed but keep the shape. Every table gets a primary key, sensible
indexes (`watch_log(person_id, fixture_id)` unique, `odds_history(fixture_id, captured_at)`,
`table_snapshots(captured_at)`), and an Alembic migration. Timestamps are `timestamptz`,
stored UTC, converted at the edge.

```
people            id, code_hash, display_name, city, timezone, push_subscription
predictions       person_id, kind('table'|'awards'|'cl'), payload_json, submitted_at, locked
table_snapshots   captured_at, gameweek, payload_json          -- weekly, drives the chart
leaderboard_runs  computed_at, gameweek, person_id, table_pts, award_pts, total, rank
watch_log         person_id, fixture_id, watched_at, local_hour, night_medal
odds_history      fixture_id, captured_at, home, draw, away    -- hourly, drives drift
fpl_snapshots     gameweek, person_id, entry_id, payload_json
quotes            person_id, body, subject_type, subject_id, created_at
polls             id, question, opens_at, closes_at
poll_votes        poll_id, person_id, choice
bets              proposer_id, opponent_id, terms, settled_at, winner_id
moments           person_id, r2_key, caption, created_at
broadcasters      country, competition, provider, url, verified_on
```

`local_hour` on `watch_log` is written at insert time in the person's own zone — that's what
makes the night medal correct without recomputing history if a timezone rule changes.

---

## 10. Scoring engine — worked examples

Test against these exact cases. Rules: 3 exact, 1 within one place, 5 per award,
10 perfect top four, 15 champion plus all three relegated.

- Predicted Arsenal 1st, finished 1st → 3
- Predicted Chelsea 4th, finished 5th → 1
- Predicted Everton 19th, finished 15th → 0
- Predicted top four Arsenal/City/Liverpool/Chelsea, they finish in any order as the top
  four → 10 bonus on top of per-position points
- Champion correct **and** all three relegated correct → 15 bonus, in addition to the top
  four bonus if that also landed
- Award pick matches the final winner → 5; a shared Golden Boot counts if your player is
  one of the joint winners

Pure functions in `shared/scoring.py`, no I/O, fully unit tested with `pytest`. The
leaderboard, the "if the season ended today" panel, the history chart and the picker
preview all call the same function — never reimplement it, in either language.

---

## 11. States, not just happy paths

Every panel defines three states and the UI ships all three:

- **Loading** — skeleton at the real final dimensions, never a spinner that shifts layout
- **Empty** — says what will appear and when. "Goals appear once the first matches are
  played", not "No data". An empty screen is an instruction, not an apology.
- **Stale or failed** — show the last good data with a quiet line: "Odds last updated 47
  minutes ago." Never a blank panel, never a raw error code, never an alert.

Specific cases to handle explicitly:
- Before the season starts: the table is 20 clubs on zero points, and it says so
- TWZT and BULBA unfiled: their leaderboard rows show as open slots with the countdown;
  after the lock they read "did not file" and score zero for the season
- A fixture postponed: keep it listed, marked postponed, excluded from projections
- bet365 absent for a region: name the gap rather than substituting another bookmaker

---

## 12. Security

- Session cookie httpOnly, Secure, signed with `SESSION_SECRET`; SameSite per §3
- CSRF token on every mutating request
- CORS locked to the frontend origin — not `*`. Same for the SSE endpoint
- Code words compared constant-time, stored hashed if persisted at all
- R2 uploads via signed URLs, images only, 10 MB cap, content-type checked server-side
- Push needs `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` as secrets; the public key is the
  only one that reaches the browser
- All secrets in Render environment groups, never in `render.yaml` or the repo
- Rate-limit the SSE endpoint per session; cap concurrent streams per person
- Nothing in this app is a bank, but four people sharing a link means treating the code
  words as real credentials

---

## 13. Deliberately dropped — do not reintroduce

These came up and were cut. If you think one is a good idea, say so; don't just add it.

- A Barclays-era purple-and-gold skin. Replaced by the Apple direction in §5.
- An era jingle on page load.
- Comments threads under matches — four people already have a group chat.
- Pirate stream links. The broadcaster block in §14 is the answer to "where do I watch".

---

## 14. Where to watch

Every fixture lists the channel or service for each of the four cities beside that city's
kickoff. Michigan and Alaska share a rights holder but not a clock; Alberta and Ukraine are
separate markets.

There is no reliable free API for this, so build it as data: `broadcasters.json` mapping
country → rights holder for 2026/27, plus per-fixture overrides where a country splits a
round across channels (the US moves matches between linear channels and streaming).
**Verify the current rights holders for Ukraine, the United States and Canada before
writing that file** — rights change between seasons and training data may be a cycle out
of date. Record `verified_on` in the file and show it in the UI. Add an admin form to
correct a listing without redeploying. Link out to the service where a link exists. Note
that the UK Saturday 3pm blackout doesn't apply to any of these four markets, so every
match is available to all four.

---

## 15. Automation

**Poller intervals** (background worker, adaptive):
- FPL live points: every 30s while any match is in play, otherwise every 10 minutes
- Fixtures and table: every 5 minutes on a matchday, hourly otherwise
- Odds: every 30 minutes, appending to `odds_history` so drift is real data
- Line-ups: on demand only, when someone opens a match
- News and YouTube: every 15 and 30 minutes

**Render Cron Jobs**:
- Monday 06:00 UTC — snapshot the table, recompute the leaderboard, flop of the week,
  round summary, then fan out push notifications
- Daily 05:00 UTC — line of the day, On This Day
- Hourly — prune caches, log quota usage

**Web push**, opt-in per person:
- One hour before kickoff, in that person's own timezone
- Prediction deadline reminders
- "Your prediction is under threat" — a club you put top four drops out of it
- Monday round summary

PWA: installable, offline shell, cached last-known data, service worker handles push.

---

## 16. Decisions you make

Pick a sensible default, implement it, tell me what you chose:
- **Projected table, promoted clubs** — Coventry, Hull and Ipswich have no fixture from
  last season. Default: treat those matches as draws, and label the affected rows as
  modelled rather than derived.
- **Leaderboard tie-break.**
- **Calendar data source.**

---

## 17. Build order

Work through these in order; each must actually work before the next starts.

1. Canonical club table, scoring engine, timezone helpers — with unit tests
2. FastAPI skeleton, auth (including the cross-origin cookie, verified against a deployed
   frontend), Postgres schema and migrations, Redis, the poller loop, and the SSE stream
   working end to end with real FPL data. Wire `openapi-typescript` into the frontend build
   so API types are generated, never hand-written.
3. Home, table, fixtures with four-city times and broadcasters — the core, shipped
4. Predictions with the picker, seeded data, server-side lock
5. Leaderboard, snapshots, derived stats
6. FPL: live squads, projections, suggested transfers
7. Watch log, odds and line-ups, Champions League
8. News, calendar, chat, archive, admin
9. Push, PWA, shareable image export

---

## 18. Definition of done

- `docker compose up` runs api, poller, Postgres and Redis locally from a clean clone
- `render.yaml` deploys all three services plus the databases
- CI is green: ruff, mypy --strict, pytest, vitest
- Live scores update in the browser without a refresh, through SSE, and reconnect if dropped
- p95 on cached GETs is under 100ms
- README lists every secret, where to get it, and exact deploy steps
- Login accepts the four code words and rejects everything else
- GW1 fixtures show real kickoff times, correct in all four cities, with broadcasters
- The prediction picker builds a full 1–20 table on a phone without frustration
- COYG's and AURE's predictions are seeded, displayed and locked
- Missing API keys degrade to clear messages; no white screens
- The season timeline computes from the current date
- Nothing in the UI would look out of place in an Apple product page
- Typecheck and lint clean
- Every panel has a real loading, empty and stale state — check them by killing a key
- **Unit tests on the scoring engine (against the §10 examples), the club-name mapper and
  timezone conversion across a DST boundary** — those three are where the bugs will be

Build it. Ask only if something here is genuinely ambiguous.
