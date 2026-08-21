/** TanStack Query hooks. One key per endpoint, so the stream can patch them. */

import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { api } from './client'
import type {
  AdminStatus,
  Club,
  FixtureList,
  Home,
  LeagueTable,
  Me,
  Predictions,
  FplStandings,
  H2H,
  Leaderboard,
  News,
  ProjectedTable,
  Season,
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
  leaderboard: ['leaderboard'] as const,
  watch: ['watch'] as const,
  news: ['news'] as const,
  h2h: (a: string, b: string) => ['h2h', a, b] as const,
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

export function useAdminStatus(): UseQueryResult<AdminStatus> {
  return useQuery({
    queryKey: keys.admin,
    queryFn: () => api.get<AdminStatus>('/api/admin/status'),
    refetchInterval: 30_000,
  })
}
