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
  market_max: Record<string, number> | null
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

export interface FixtureOdds {
  fixture_id: number
  home: Club
  away: Club
  odds: Odds
}

export interface OddsRound {
  fixtures: FixtureOdds[]
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

export interface PlayerStat {
  id: number
  name: string
  full_name: string
  club: string
  club_name: string
  position: string
  minutes: number
  starts: number
  goals: number
  assists: number
  goal_involvements: number
  clean_sheets: number
  saves: number
  yellow_cards: number
  red_cards: number
  bonus: number
  xg: number
  xa: number
  xgi: number
  goals_minus_xg: number
  per_90_goals: number
  per_90_assists: number
  ict: number
  form: number
  points: number
  points_per_game: number
  price: number
  selected_by: number
  status: string
  news: string
}

export interface PlayerStats {
  players: PlayerStat[]
  gameweek: number
  matches_played: number
  freshness: Freshness
  empty_message: string | null
}

export interface TeamStat {
  club: Club
  position: number
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
  goal_difference: number
  points: number
  clean_sheets: number
  failed_to_score: number
  goals_per_game: number
  conceded_per_game: number
  form: string[]
  squad_xg: number
  squad_xga: number
}

export interface TeamStats {
  teams: TeamStat[]
  matches_played: number
  freshness: Freshness
  empty_message: string | null
}

export interface Quote {
  id: number
  person: string
  body: string
  subject_type: string | null
  subject_id: string | null
  created_at: string
}

export interface PollOption {
  choice: string
  votes: number
  voters: string[]
}

export interface Poll {
  id: number
  question: string
  options: PollOption[]
  opens_at: string
  closes_at: string
  open: boolean
  my_vote: string | null
  total_votes: number
}

export interface Polls {
  current: Poll | null
  archive: Poll[]
  empty_message: string | null
}

export interface Bet {
  id: number
  proposer: string
  opponent: string
  terms: string
  created_at: string
  settled_at: string | null
  winner: string | null
  settled: boolean
}

export interface Bets {
  bets: Bet[]
  scoreboard: Record<string, number>
  empty_message: string | null
}

export interface TimelineEntry {
  kind: string
  at: string
  person: string | null
  title: string
  detail: string | null
}

export interface Timeline {
  entries: TimelineEntry[]
  empty_message: string | null
}

export interface NewsItem {
  title: string
  url: string
  source: string
  published: string | null
  summary: string
  image: string | null
}

export interface News {
  sky: NewsItem[]
  sources: string[]
  youtube: NewsItem[]
  athletic: NewsItem[]
  freshness: Freshness
  empty_message: string | null
  youtube_message: string | null
  athletic_message: string | null
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

export interface FplPlayer {
  element: number
  name: string
  club: string
  position: string
  slot: number
  is_captain: boolean
  is_vice_captain: boolean
  multiplier: number
  on_bench: boolean
  points: number
  minutes: number
  goals: number
  assists: number
  bonus: number
  played: boolean
  differential: boolean
}

export interface FplChip {
  code: string
  name: string
  half: number
  played_in: number | null
  played: boolean
}

export interface FplSquad {
  person: string | null
  entry_id: number
  entry_name: string
  starting: FplPlayer[]
  bench: FplPlayer[]
  captain: FplPlayer | null
  vice_captain: FplPlayer | null
  chip: string | null
  live_points: number
  bench_points: number
  bench_counts: boolean
  chips: FplChip[]
  players_played: number
  players_to_play: number
}

export interface FplSquads {
  gameweek: number
  squads: FplSquad[]
  captains: Record<string, string>
  freshness: Freshness
  empty_message: string | null
  note: string | null
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

export interface LineupPlayer {
  name: string
  number: number | null
  position: string
}

export interface LineupSide {
  formation: string
  starting: LineupPlayer[]
  bench: LineupPlayer[]
}

export interface Lineups {
  available: boolean
  confirmed: boolean
  basis: string
  reason: string | null
  home: LineupSide | null
  away: LineupSide | null
}

export interface Pick {
  person: string
  fixture_id: number
  home_goals: number
  away_goals: number
  points: number | null
  exact: boolean
  outcome_hit: boolean
  total_hit: boolean
}

export interface FixturePicks {
  fixture_id: number
  gameweek: number
  kickoff: string | null
  home: Club
  away: Club
  home_score: number | null
  away_score: number | null
  started: boolean
  finished: boolean
  open_for_picks: boolean
  revealed: boolean
  my_pick: Pick | null
  picks: Pick[]
  odds: Odds | null
}

export interface PickRound {
  gameweek: number
  fixtures: FixturePicks[]
  freshness: Freshness
  empty_message: string | null
}

export interface PickStats {
  person: Person
  settled: number
  points: number
  points_per_pick: number
  exact: number
  exact_pct: number
  outcomes: number
  outcome_pct: number
  totals: number
  total_pct: number
  current_streak: number
  best_streak: number
  predicted_goals: number
  actual_goals: number
  goal_bias: number
  home_pct: number
  with_market: number
  followed_favourite: number
  bold: number
  bold_hits: number
  bold_pct: number
  market_points: number
  edge: number
}

export interface PickStandings {
  rows: PickStats[]
  total_settled: number
  empty_message: string | null
  scoring: string
}

export interface Forecast {
  element: number
  name: string
  club: string
  position: string
  price: number
  expected_points: number
  appearances: number
  confident: boolean
  availability: string
  difficulty: number
  basis: string
  reasons: string[]
}

export interface CaptainPick {
  rank: number
  doubled: number
  player: Forecast
}

export interface TransferIdea {
  out_player: Forecast
  in_player: Forecast
  gain: number
  reasoning: string[]
}

export interface ManagerAdvice {
  person: string
  entry_name: string
  bank: number
  captain_now: string | null
  captains: CaptainPick[]
  transfers: TransferIdea[]
  projected_points: number
  projected_from: number
  squad_size: number
  note: string
}

export interface ManagerReport {
  person: string
  live_points: number
  bench_points: number
  bench_wasted: number
  captain: string | null
  captain_points: number
  best_captain: string | null
  best_captain_points: number
  captain_cost: number
  players_to_play: number
  verdict: string
}

export interface FplAdvice {
  gameweek: number
  managers: ManagerAdvice[]
  reports: ManagerReport[]
  worst: string | null
  worst_reason: string | null
  freshness: Freshness
  empty_message: string | null
  method: string
}

export interface WatchOn {
  place: string
  country: string
  city: string
  person: string
  provider: string
  url: string
  confidence: string
}

export interface CalendarEvent {
  title: string
  sport: string
  sport_label: string
  starts_at: string
  ends_at: string | null
  time_known: boolean
  multi_day: boolean
  in_progress: boolean
  days_until: number
  venue: string
  tier: 'major' | 'notable'
  note: string
  local_times: LocalTime[]
  watch: WatchOn[]
}

export interface Calendar {
  events: CalendarEvent[]
  sports: string[]
  checked_on: string
  empty_message: string | null
}
