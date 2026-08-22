import { useState } from 'react'
import { useClubs, useFplSquads, useFplStandings, useMe } from '@/api/queries'
import { Crest } from '@/components/Crest'
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
  // A crest reads faster than three letters, and every other table on the
  // site now shows one.
  const { data: clubList } = useClubs()
  const club = (clubList ?? []).find((c) => c.short_name === player.club)

  return (
    <div className="pl" data-played={player.played}>
      <span className="pl__pos">{player.position}</span>
      <span className="pl__name">{player.name}</span>
      <span className="pl__club">
        {club && <Crest club={club} size={15} />}
        {player.club}
      </span>
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

function Chips({ squad }: { squad: FplSquad }) {
  if (squad.chips.length === 0) return null
  // Two halves of the season, each with its own set. Showing them together
  // would imply eight are available now, when only the first four are.
  const half = squad.chips.filter((c) => c.half === 1)
  const later = squad.chips.filter((c) => c.half === 2)
  const played = squad.chips.filter((c) => c.played)

  return (
    <>
      <p className="squad__group">
        Chips · {played.length} used, {squad.chips.length - played.length} left
      </p>
      <div className="chips-row">
        {half.map((chip) => (
          <span
            key={`${chip.code}-${chip.half}`}
            className="chip-pill"
            data-played={chip.played}
            title={chip.played ? `Played in gameweek ${chip.played_in}` : 'Still available'}
          >
            {chip.name}
            {chip.played && <b> GW{chip.played_in}</b>}
          </span>
        ))}
      </div>
      {later.length > 0 && (
        <p className="chips-note">
          {later.filter((c) => !c.played).length} more from gameweek 20
          {later.some((c) => c.played) &&
            ` · ${later.filter((c) => c.played).map((c) => c.name).join(', ')} already used`}
        </p>
      )}
    </>
  )
}

/** Who is winning, without reading four cards. */
function StandingsBar({ squads, me }: { squads: FplSquad[]; me: string | undefined }) {
  if (squads.length === 0) return null
  const lead = Math.max(...squads.map((s) => s.live_points))
  return (
    <div className="fpl-bar">
      {squads.map((squad) => {
        const total = squad.players_played + squad.players_to_play
        const done = total ? (squad.players_played / total) * 100 : 0
        return (
          <div className="fpl-bar__cell" key={squad.entry_id} data-lead={squad.live_points === lead}>
            <p className="fpl-bar__who">
              {(squad.person ?? squad.entry_name).toUpperCase()}
              {squad.person === me && <span className="tag">you</span>}
            </p>
            <p className="fpl-bar__pts">{squad.live_points}</p>
            <p className="fpl-bar__sub">
              {squad.players_played} of {total} played
              {squad.bench_counts ? ' · bench counting' : ''}
            </p>
            <span className="fpl-bar__prog">
              <i style={{ width: `${done}%` }} />
            </span>
          </div>
        )
      })}
    </div>
  )
}

/** The captain choice, which is where most of a round is decided. */
function CaptainRow({ squads }: { squads: FplSquad[] }) {
  const withCaptain = squads.filter((s) => s.captain)
  if (withCaptain.length === 0) return null

  const counts = new Map<number, number>()
  for (const s of withCaptain) {
    const id = s.captain!.element
    counts.set(id, (counts.get(id) ?? 0) + 1)
  }

  return (
    <div className="captains">
      {withCaptain.map((squad) => {
        const captain = squad.captain!
        const unique = counts.get(captain.element) === 1
        return (
          <div className="captain" key={squad.entry_id} data-unique={unique}>
            <p className="captain__who">{(squad.person ?? squad.entry_name).toUpperCase()} · captain</p>
            <p className="captain__name">{captain.name}</p>
            <p className="captain__pts">
              {captain.points} pts · {captain.club}
            </p>
            {unique && <span className="captain__tag">ONLY ONE</span>}
          </div>
        )
      })}
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

      <Chips squad={squad} />

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
            <StandingsBar squads={data.squads} me={me?.person.key} />
            <CaptainRow squads={data.squads} />
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
