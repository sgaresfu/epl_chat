/**
 * Player and team statistics.
 *
 * The whole player list arrives once and is sorted in the browser, so changing
 * a column is instant rather than a round trip. That is the difference between
 * a table you explore and one you wait for.
 *
 * Expected goals is the column worth having: goals alone say what happened,
 * `G−xG` says whether it was likely to keep happening.
 */

import { useMemo, useState } from 'react'
import { usePlayerStats, useTeamStats } from '@/api/queries'
import { Crest } from '@/components/Crest'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'
import { signed } from '@/lib/format'
import type { PlayerStat, TeamStat } from '@/api/types'

type PlayerKey = keyof PlayerStat
type Dir = 'asc' | 'desc'

const PLAYER_COLUMNS: ReadonlyArray<[PlayerKey, string, string]> = [
  ['goals', 'G', 'Goals'],
  ['assists', 'A', 'Assists'],
  ['goal_involvements', 'G+A', 'Goals and assists'],
  ['xg', 'xG', 'Expected goals'],
  ['xa', 'xA', 'Expected assists'],
  ['goals_minus_xg', 'G−xG', 'Goals above or below expectation'],
  ['minutes', 'Min', 'Minutes played'],
  ['clean_sheets', 'CS', 'Clean sheets'],
  ['bonus', 'Bns', 'Bonus points'],
  ['points', 'Pts', 'Fantasy points'],
  ['price', '£', 'Fantasy price'],
]

const POSITIONS = ['All', 'GK', 'DEF', 'MID', 'FWD'] as const

function Players() {
  const { data, isLoading } = usePlayerStats()
  const [sort, setSort] = useState<PlayerKey>('goals')
  const [dir, setDir] = useState<Dir>('desc')
  const [pos, setPos] = useState<(typeof POSITIONS)[number]>('All')
  const [query, setQuery] = useState('')

  const rows = useMemo(() => {
    let list = data?.players ?? []
    if (pos !== 'All') list = list.filter((p) => p.position === pos)
    const needle = query.trim().toLowerCase()
    if (needle) {
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(needle) ||
          p.full_name.toLowerCase().includes(needle) ||
          p.club.toLowerCase().includes(needle) ||
          p.club_name.toLowerCase().includes(needle),
      )
    }
    const sorted = [...list].sort((a, b) => {
      const av = a[sort]
      const bv = b[sort]
      const cmp = typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : String(av).localeCompare(String(bv))
      // Ties fall back to minutes, so the leader of an empty column is the one
      // actually playing rather than whoever FPL listed first.
      return (dir === 'desc' ? -cmp : cmp) || b.minutes - a.minutes
    })
    return sorted.slice(0, 60)
  }, [data, sort, dir, pos, query])

  if (isLoading) return <TableSkeleton rows={12} />
  if (!data || data.players.length === 0) {
    return (
      <Empty title="No statistics yet">
        <p>{data?.empty_message ?? 'They appear once the squad list has loaded.'}</p>
      </Empty>
    )
  }

  function toggle(key: PlayerKey) {
    if (key === sort) setDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    else {
      setSort(key)
      setDir('desc')
    }
  }

  return (
    <>
      {data.empty_message && (
        <Empty title="Nothing played yet">
          <p>{data.empty_message}</p>
        </Empty>
      )}

      <div className="stats-bar" style={{ marginTop: data.empty_message ? 20 : 0 }}>
        <span className="seg" role="tablist" aria-label="Position">
          {POSITIONS.map((p) => (
            <button key={p} role="tab" type="button" aria-selected={pos === p} onClick={() => setPos(p)}>
              {p}
            </button>
          ))}
        </span>
        <label className="sr-only" htmlFor="pq">
          Search players
        </label>
        <input
          id="pq"
          className="stats-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search player or club"
        />
        <span className="stats-count">
          top {rows.length} by {PLAYER_COLUMNS.find(([k]) => k === sort)?.[2] ?? sort}
        </span>
      </div>

      <div className="table-scroll">
        <table className="table">
          <caption className="sr-only">Player statistics</caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Player</th>
              {PLAYER_COLUMNS.map(([key, short, full]) => (
                <th
                  key={key}
                  scope="col"
                  data-sortable="true"
                  title={`${full} — click to sort`}
                  aria-sort={sort === key ? (dir === 'desc' ? 'descending' : 'ascending') : undefined}
                  onClick={() => toggle(key)}
                >
                  {short}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.id}>
                <td>
                  <span className="pos">{i + 1}</span>
                </td>
                <td>
                  <span className="player-name">
                    {p.status !== 'a' && (
                      <span
                        className="player-flag"
                        data-status={p.status}
                        title={p.news || 'Doubtful'}
                      />
                    )}
                    <b title={p.full_name}>{p.name}</b>
                    <span className="player-pos">{p.position}</span>
                    <span className="sec">{p.club}</span>
                  </span>
                </td>
                {PLAYER_COLUMNS.map(([key]) => {
                  const value = p[key] as number
                  if (key === 'goals_minus_xg') {
                    return (
                      <td className="sec stat-num" key={key}>
                        <span
                          className="delta"
                          data-dir={value > 0.05 ? 'over' : value < -0.05 ? 'under' : undefined}
                        >
                          {value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2)}
                        </span>
                      </td>
                    )
                  }
                  return (
                    <td className={key === sort ? 'pts stat-num' : 'sec stat-num'} key={key}>
                      {key === 'price' ? `£${value.toFixed(1)}` : value}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tnote">
        Expected goals and assists come from the Premier League&rsquo;s own fantasy
        feed. <b style={{ color: 'var(--ink)' }}>G−xG</b> is finishing against
        expectation: positive means scoring more than the chances were worth. Rates
        per 90 need a full match played before they mean anything. A coloured dot is
        an injury or doubt.
      </p>
      <StaleNote freshness={data.freshness} label="Statistics" />
    </>
  )
}

const TEAM_COLUMNS: ReadonlyArray<[keyof TeamStat, string, string]> = [
  ['played', 'Pl', 'Played'],
  ['won', 'W', 'Won'],
  ['drawn', 'D', 'Drawn'],
  ['lost', 'L', 'Lost'],
  ['goals_for', 'GF', 'Goals for'],
  ['goals_against', 'GA', 'Goals against'],
  ['goal_difference', 'GD', 'Goal difference'],
  ['clean_sheets', 'CS', 'Clean sheets'],
  ['failed_to_score', 'FTS', 'Failed to score'],
  ['goals_per_game', 'GF/g', 'Goals per game'],
  ['conceded_per_game', 'GA/g', 'Conceded per game'],
  ['squad_xg', 'xG', 'Squad expected goals'],
  ['points', 'Pts', 'Points'],
]

function Teams() {
  const { data, isLoading } = useTeamStats()
  const [sort, setSort] = useState<keyof TeamStat>('points')
  const [dir, setDir] = useState<Dir>('desc')

  const rows = useMemo(() => {
    const list = [...(data?.teams ?? [])]
    return list.sort((a, b) => {
      const av = a[sort]
      const bv = b[sort]
      const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : 0
      return (dir === 'desc' ? -cmp : cmp) || a.position - b.position
    })
  }, [data, sort, dir])

  if (isLoading) return <TableSkeleton rows={20} />
  if (!data || data.teams.length === 0) {
    return (
      <Empty title="No team statistics yet">
        <p>{data?.empty_message ?? 'They appear once the fixture list has loaded.'}</p>
      </Empty>
    )
  }

  return (
    <>
      <div className="table-scroll">
        <table className="table">
          <caption className="sr-only">Team statistics</caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Club</th>
              {TEAM_COLUMNS.map(([key, short, full]) => (
                <th
                  key={key}
                  scope="col"
                  data-sortable="true"
                  title={`${full} — click to sort`}
                  aria-sort={sort === key ? (dir === 'desc' ? 'descending' : 'ascending') : undefined}
                  onClick={() => {
                    if (key === sort) setDir((d) => (d === 'desc' ? 'asc' : 'desc'))
                    else {
                      setSort(key)
                      setDir('desc')
                    }
                  }}
                >
                  {short}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((t, i) => (
              <tr key={t.club.short_name}>
                <td>
                  <span className="pos">{i + 1}</span>
                </td>
                <td>
                  <span className="club">
                    <Crest club={t.club} size={26} />
                    <b>{t.club.name}</b>
                  </span>
                </td>
                {TEAM_COLUMNS.map(([key]) => {
                  const value = t[key] as number
                  return (
                    <td className={key === sort ? 'pts stat-num' : 'sec stat-num'} key={key}>
                      {key === 'goal_difference' ? signed(value) : value}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tnote">
        Squad xG totals every player&rsquo;s expected goals, so it reflects the
        squad rather than one afternoon&rsquo;s finishing.
      </p>
      <StaleNote freshness={data.freshness} label="Statistics" />
    </>
  )
}

export function Stats() {
  const [tab, setTab] = useState<'players' | 'teams'>('players')
  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Statistics</h2>
          <span className="seg" role="tablist" aria-label="View">
            <button role="tab" type="button" aria-selected={tab === 'players'} onClick={() => setTab('players')}>
              Players
            </button>
            <button role="tab" type="button" aria-selected={tab === 'teams'} onClick={() => setTab('teams')}>
              Teams
            </button>
          </span>
        </div>
        {tab === 'players' ? <Players /> : <Teams />}
      </div>
    </section>
  )
}
