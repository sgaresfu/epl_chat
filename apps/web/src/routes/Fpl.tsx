import { useState } from 'react'
import { useFplSquads, useFplStandings, useMe } from '@/api/queries'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'
import type { FplPlayer, FplSquad } from '@/api/types'

/** FPL's chip codes are not words anybody says out loud. */
const CHIP_NAMES: Record<string, string> = {
  bboost: 'Bench Boost',
  '3xc': 'Triple Captain',
  freehit: 'Free Hit',
  wildcard: 'Wildcard',
  manager: 'Assistant Manager',
}

function Player({ player }: { player: FplPlayer }) {
  return (
    <div className="pl" data-played={player.played}>
      <span className="pl__pos">{player.position}</span>
      <span className="pl__name">{player.name}</span>
      <span className="pl__club">{player.club}</span>
      {player.is_captain && (
        <span className="pl__badge" data-kind="C" title="Captain">
          C
        </span>
      )}
      {player.is_vice_captain && (
        <span className="pl__badge" data-kind="V" title="Vice-captain">
          V
        </span>
      )}
      {player.differential && (
        <span className="pl__badge" data-kind="D" title="Nobody else in the league owns them">
          DIFF
        </span>
      )}
      <span className="pl__pts">{player.points}</span>
    </div>
  )
}

function Squad({ squad, me }: { squad: FplSquad; me: string | undefined }) {
  const differentials = [...squad.starting, ...squad.bench].filter((p) => p.differential)
  return (
    <div className="squad">
      <div className="squad__head">
        <span className="squad__who">
          {(squad.person ?? squad.entry_name).toUpperCase()}
          {squad.person === me && <span className="tag" style={{ marginLeft: 8 }}>you</span>}
        </span>
        <span className="squad__pts">{squad.live_points}</span>
      </div>
      <p className="squad__sub">
        {squad.entry_name} · {squad.players_played} played, {squad.players_to_play} to come
        {squad.bench_points > 0 &&
          (squad.bench_counts
            ? ` · ${squad.bench_points} from the bench, counted`
            : ` · ${squad.bench_points} left on the bench`)}
        {squad.chip && ` · ${CHIP_NAMES[squad.chip] ?? squad.chip}`}
        {differentials.length > 0 && ` · ${differentials.length} differential${differentials.length === 1 ? '' : 's'}`}
      </p>

      <p className="squad__group">Starting XI</p>
      {squad.starting.map((p) => (
        <Player key={p.element} player={p} />
      ))}

      <p className="squad__group">
        Bench{squad.bench_counts ? ' · counting, Bench Boost is on' : ''}
      </p>
      <div className="squad__bench" style={squad.bench_counts ? { opacity: 1 } : undefined}>
        {squad.bench.map((p) => (
          <Player key={p.element} player={p} />
        ))}
      </div>
    </div>
  )
}

function Standings() {
  const { data, isLoading } = useFplStandings()
  const { data: me } = useMe()
  if (isLoading || !data) return <TableSkeleton rows={4} />
  if (data.rows.length === 0) {
    return (
      <Empty title="The mini-league has not loaded">
        <p>{data.empty_message ?? 'It appears once the poller has fetched it.'}</p>
      </Empty>
    )
  }
  return (
    <>
      <div className="table-scroll">
        <table className="table">
          <caption className="sr-only">Mini-league standings</caption>
          <thead>
            <tr>
              <th scope="col">Pos</th>
              <th scope="col">Manager</th>
              <th scope="col">GW</th>
              <th scope="col">Total</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.entry_id}>
                <td>
                  <span className="pos">{row.rank ?? '—'}</span>
                </td>
                <td>
                  <span className="club">
                    <b>{row.person ? row.person.toUpperCase() : row.entry_name}</b>
                    {row.person === me?.person.key && <span className="tag">you</span>}
                    <span className="tag" style={{ borderStyle: 'dashed' }}>
                      {row.entry_name}
                    </span>
                  </span>
                </td>
                <td className="sec">{row.pending ? '—' : row.event_total}</td>
                <td className="pts">{row.pending ? '—' : row.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.rows.every((r) => r.pending) && (
        <p className="tnote">{data.empty_message}</p>
      )}
      <StaleNote freshness={data.freshness} label="Mini-league" />
    </>
  )
}

export function Fpl() {
  const [tab, setTab] = useState<'squads' | 'standings'>('squads')
  const { data, isLoading } = useFplSquads()
  const { data: me } = useMe()

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Fantasy</h2>
          <span className="seg" role="tablist" aria-label="View">
            <button role="tab" type="button" aria-selected={tab === 'squads'} onClick={() => setTab('squads')}>
              Live squads
            </button>
            <button
              role="tab"
              type="button"
              aria-selected={tab === 'standings'}
              onClick={() => setTab('standings')}
            >
              Standings
            </button>
          </span>
          {data && (
            <span className="shead__link" style={{ color: 'var(--ink-3)' }}>
              Gameweek {data.gameweek}
            </span>
          )}
        </div>

        {tab === 'standings' ? (
          <Standings />
        ) : isLoading ? (
          <TableSkeleton rows={8} />
        ) : !data || data.squads.length === 0 ? (
          <Empty title="Squads not available yet">
            <p>{data?.empty_message ?? 'They appear once the poller has fetched them.'}</p>
          </Empty>
        ) : (
          <>
            {Object.keys(data.captains).length > 0 && (
              <p className="tnote" style={{ marginTop: 0, marginBottom: 22 }}>
                <b style={{ color: 'var(--ink)' }}>Captains:</b>{' '}
                {Object.entries(data.captains)
                  .map(([who, name]) => `${who.toUpperCase()} ${name}`)
                  .join(' · ')}
              </p>
            )}
            <div className="squads">
              {data.squads.map((squad) => (
                <Squad key={squad.entry_id} squad={squad} me={me?.person.key} />
              ))}
            </div>
            <p className="tnote">{data.note}</p>
            <StaleNote freshness={data.freshness} label="Live points" />
          </>
        )}
      </div>
    </section>
  )
}
