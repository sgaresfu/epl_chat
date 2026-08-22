/** TanStack Query hooks. One key per endpoint, so the stream can patch them. */

import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { api } from './client'
import type {
  AdminStatus,
  Calendar,
  Club,
  Lineups,
  OddsRound,
  FixtureList,
  Home,
  LeagueTable,
  Me,
  Predictions,
  FplSquads,
  FplStandings,
  H2H,
  Bets,
  Leaderboard,
  News,
  PlayerStats,
  Polls,
  Quote,
  TeamStats,
  ProjectedTable,
  Season,
  Timeline,
  WatchStats,
} from './types'

export const keys = {
  me: ['me'] as const,
  clubs: ['clubs'] as const,
  home: ['home'] as const,
  season: ['season'] as const,
  table: ['table'] as const,
  projected: ['table', 'projected'] as const,
  fixtures: (gw?: number) => ['fixtures', gw ?? 'all'] as const,
  predictions: ['predictions'] as const,
  admin: ['admin'] as const,
  fplStandings: ['fpl', 'standings'] as const,
  fplSquads: ['fpl', 'squads'] as const,
  leaderboard: ['leaderboard'] as const,
  watch: ['watch'] as const,
  news: ['news'] as const,
  playerStats: ['stats', 'players'] as const,
  teamStats: ['stats', 'teams'] as const,
  quotes: ['chat', 'quotes'] as const,
  poll: ['chat', 'poll'] as const,
  bets: ['chat', 'bets'] as const,
  timeline: ['timeline'] as const,
  h2h: (a: string, b: string) => ['h2h', a, b] as const,
  calendar: ['calendar'] as const,
  odds: ['odds'] as const,
  lineups: (fixtureId: number) => ['lineups', fixtureId] as const,
}

export function useMe(): UseQueryResult<Me> {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => api.get<Me>('/api/me'),
    retry: false,
    staleTime: 5 * 60_000,
  })
}

export function useClubs(): UseQueryResult<Club[]> {
  return useQuery({
    queryKey: keys.clubs,
    queryFn: () => api.get<Club[]>('/api/clubs'),
    // The canonical club table changes once a season, not once a minute.
    staleTime: Infinity,
  })
}

export function useHome(): UseQueryResult<Home> {
  return useQuery({ queryKey: keys.home, queryFn: () => api.get<Home>('/api/home') })
}

export function useSeason(): UseQueryResult<Season> {
  return useQuery({ queryKey: keys.season, queryFn: () => api.get<Season>('/api/season') })
}

export function useTable(): UseQueryResult<LeagueTable> {
  return useQuery({ queryKey: keys.table, queryFn: () => api.get<LeagueTable>('/api/table') })
}

export function useProjectedTable(enabled = true): UseQueryResult<ProjectedTable> {
  return useQuery({
    queryKey: keys.projected,
    queryFn: () => api.get<ProjectedTable>('/api/table/projected'),
    enabled,
  })
}

export function useFixtures(gameweek?: number): UseQueryResult<FixtureList> {
  return useQuery({
    queryKey: keys.fixtures(gameweek),
    queryFn: () =>
      api.get<FixtureList>(
        gameweek == null ? '/api/fixtures' : `/api/fixtures?gameweek=${gameweek}`,
      ),
  })
}

export function useOdds(): UseQueryResult<OddsRound> {
  return useQuery({ queryKey: keys.odds, queryFn: () => api.get<OddsRound>('/api/odds') })
}

/** Only fetched once the fixture's own line-ups panel is actually opened --
 * this is the one endpoint that can trigger an upstream call, so it must
 * never be prefetched alongside the rest of a match row. */
export function useLineups(fixtureId: number, enabled: boolean): UseQueryResult<Lineups> {
  return useQuery({
    queryKey: keys.lineups(fixtureId),
    queryFn: () => api.get<Lineups>(`/api/fixtures/${fixtureId}/lineups`),
    enabled,
  })
}

export function usePredictions(): UseQueryResult<Predictions> {
  return useQuery({
    queryKey: keys.predictions,
    queryFn: () => api.get<Predictions>('/api/predictions'),
  })
}

export function useFplStandings(): UseQueryResult<FplStandings> {
  return useQuery({
    queryKey: keys.fplStandings,
    queryFn: () => api.get<FplStandings>('/api/fpl/standings'),
  })
}

export function useLeaderboard(): UseQueryResult<Leaderboard> {
  return useQuery({
    queryKey: keys.leaderboard,
    queryFn: () => api.get<Leaderboard>('/api/leaderboard'),
  })
}

export function useH2H(a: string, b: string): UseQueryResult<H2H> {
  return useQuery({
    queryKey: keys.h2h(a, b),
    queryFn: () => api.get<H2H>(`/api/h2h?a=${a}&b=${b}`),
    enabled: a !== b,
  })
}

export function useWatchStats(): UseQueryResult<WatchStats> {
  return useQuery({ queryKey: keys.watch, queryFn: () => api.get<WatchStats>('/api/watch') })
}

export function useNews(): UseQueryResult<News> {
  return useQuery({ queryKey: keys.news, queryFn: () => api.get<News>('/api/news') })
}

export function useCalendar(): UseQueryResult<Calendar> {
  return useQuery({ queryKey: keys.calendar, queryFn: () => api.get<Calendar>('/api/calendar') })
}

export function useQuotes(): UseQueryResult<Quote[]> {
  return useQuery({ queryKey: keys.quotes, queryFn: () => api.get<Quote[]>('/api/chat/quotes') })
}

export function usePoll(): UseQueryResult<Polls> {
  return useQuery({ queryKey: keys.poll, queryFn: () => api.get<Polls>('/api/chat/poll') })
}

export function useBets(): UseQueryResult<Bets> {
  return useQuery({ queryKey: keys.bets, queryFn: () => api.get<Bets>('/api/chat/bets') })
}

export function useTimeline(): UseQueryResult<Timeline> {
  return useQuery({ queryKey: keys.timeline, queryFn: () => api.get<Timeline>('/api/timeline') })
}

export function useFplSquads(): UseQueryResult<FplSquads> {
  return useQuery({
    queryKey: keys.fplSquads,
    queryFn: () => api.get<FplSquads>('/api/fpl/squads'),
    // Live during a match; the stream also invalidates this on an fpl event.
    refetchInterval: 60_000,
  })
}

export function usePlayerStats(): UseQueryResult<PlayerStats> {
  return useQuery({
    queryKey: keys.playerStats,
    queryFn: () => api.get<PlayerStats>('/api/stats/players'),
    // The whole list, sorted in the browser: 600 trimmed rows is a small
    // payload and makes sorting a column instant.
    staleTime: 5 * 60_000,
  })
}

export function useTeamStats(): UseQueryResult<TeamStats> {
  return useQuery({ queryKey: keys.teamStats, queryFn: () => api.get<TeamStats>('/api/stats/teams') })
}

export function useAdminStatus(): UseQueryResult<AdminStatus> {
  return useQuery({
    queryKey: keys.admin,
    queryFn: () => api.get<AdminStatus>('/api/admin/status'),
    refetchInterval: 30_000,
  })
}
