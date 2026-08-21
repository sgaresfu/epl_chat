/**
 * API types.
 *
 * `npm run gen:api` regenerates `schema.d.ts` from the FastAPI OpenAPI document
 * so the two sides cannot drift. These aliases give the app stable names to
 * import and are the only place the generated shapes are referenced, so a
 * regeneration is a one-file review rather than a project-wide churn.
 */

export interface Person {
  key: string
  name: string
  city: string
  timezone: string
  country: string
  fpl_entry_id: number | null
}

export interface Me {
  person: Person
  people: Person[]
  season: string
  prediction_lock: string
  locked: boolean
  server_time: string
}

export interface Club {
  short_name: string
  name: string
  full_name: string
  primary: string
  on_primary: string
  fpl_id: number
}

export interface Freshness {
  source: string
  age_seconds: number
  stale: boolean
  available: boolean
  reason: string | null
}

export interface LocalTime {
  place: string
  person: string
  city: string
  timezone: string
  iso: string
  time: string
  weekday: string
  day: string
  offset: string
  abbreviation: string
  is_night: boolean
  day_shift: number
  broadcaster: string | null
  broadcaster_url: string | null
  verified_on: string | null
}

export interface TableRow {
  position: number
  club: Club
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
  goal_difference: number
  points: number
  form: string[]
  modelled: boolean
  note: string | null
}

export interface LeagueTable {
  rows: TableRow[]
  gameweek: number
  matches_played: number
  season_started: boolean
  freshness: Freshness
  empty_message: string | null
}

export interface ProjectedTable extends LeagueTable {
  modelled_rows: string[]
  method: string
}

export interface Odds {
  home: number | null
  draw: number | null
  away: number | null
  bookmaker: string
  captured_at: string | null
  drift: Record<string, number> | null
  available: boolean
  reason: string | null
}

export interface Fixture {
  id: number
  gameweek: number
  kickoff: string | null
  home: Club
  away: Club
  home_score: number | null
  away_score: number | null
  started: boolean
  finished: boolean
  postponed: boolean
  minutes: number
  local_times: LocalTime[]
  odds: Odds | null
  derby: string | null
  watched_by: string[]
  watch_open: boolean
}

export interface FixtureList {
  fixtures: Fixture[]
  freshness: Freshness
  empty_message: string | null
}

export interface TimelineMarker {
  label: string
  date: string
  percent: number
  is_now: boolean
}

export interface Season {
  starts: string
  ends: string
  today: string
  percent: number
  day: number
  total_days: number
  days_remaining: number
  gameweeks_played: number
  gameweeks_total: number
  matches_played: number
  matches_total: number
  matches_remaining: number
  watched: number
  markers: TimelineMarker[]
}

export interface NextMatch {
  fixture: Fixture | null
  countdown_seconds: number | null
  in_play: boolean
  message: string | null
}

export interface Home {
  next_match: NextMatch
  season: Season
  line_of_the_day: string | null
}

export interface AwardPicks {
  golden_boot: string
  golden_glove: string
  defender: string
  playmaker: string
  player_of_the_season: string
}

export interface ChampionsLeaguePicks {
  winner: string
  finalist_a: string
  finalist_b: string
  top_scorer: string
  draft: boolean
}

export interface Prediction {
  person: string
  filed: boolean
  redacted: boolean
  table: string[]
  awards: AwardPicks | null
  champions_league: ChampionsLeaguePicks | null
  submitted_at: string | null
  locked: boolean
  status: 'filed' | 'open' | 'did-not-file'
}

export interface Predictions {
  predictions: Prediction[]
  locked: boolean
  lock_at: string
  seconds_remaining: number
}

export interface Preview {
  total: number
  table_points: number
  award_points: number
  exact_hits: number
  near_hits: number
  top_four_bonus: number
  champion_bonus: number
  against_season: string
  per_club: Array<{ club: string; predicted: number; actual: number | null; points: number }>
}

export interface CacheAge {
  name: string
  source: string
  age_seconds: number
  stale: boolean
}

export interface Quota {
  source: string
  used: number
  budget: number
  remaining: number
  window: string
  note: string
}

export interface CronRun {
  job: string
  started_at: string
  finished_at: string | null
  ok: boolean
  detail: string
}

export interface WatchStats {
  person: string
  watched: number
  total_matches: number
  percent: number
  hours: number
  night_medals: number
  streak: number
  freshness: Freshness
}

export interface LeaderboardRow {
  rank: number
  person: Person
  total: number
  table_points: number
  award_points: number
  exact_hits: number
  filed: boolean
  status: string
  movement: number
  cursed_pick: string | null
  form: number[]
}

export interface Leaderboard {
  rows: LeaderboardRow[]
  leader: string | null
  flop_of_the_week: string | null
  if_season_ended_today: string | null
  freshness: Freshness
  empty_message: string | null
}

export interface H2H {
  a: Person
  b: Person
  agreements: Array<{ club: Club; position: number }>
  gaps: Array<{ club: Club; a_position: number; b_position: number; distance: number }>
  agreement_count: number
  empty_message: string | null
}

export interface FplStandingRow {
  entry_id: number
  entry_name: string
  player_name: string
  person: string | null
  rank: number | null
  total: number
  event_total: number
  pending: boolean
}

export interface FplStandings {
  league_id: number
  league_name: string
  rows: FplStandingRow[]
  gameweek: number
  freshness: Freshness
  empty_message: string | null
  unmapped: number[]
}

export interface AdminStatus {
  caches: CacheAge[]
  quotas: Quota[]
  cron: CronRun[]
  missing_keys: string[]
  environment: string
}
