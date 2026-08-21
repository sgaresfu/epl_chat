import { useFplStandings, useMe } from '@/api/queries'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'

export function Fpl() {
  const { data, isLoading } = useFplStandings()
  const { data: me } = useMe()

  if (isLoading) return <TableSkeleton rows={4} />

  if (!data || data.rows.length === 0) {
    return (
      <section className="section">
        <div className="wrap">
          <div className="shead">
            <h2>Fantasy</h2>
          </div>
          <Empty title="The mini-league has not loaded">
            <p>{data?.empty_message ?? 'It appears once the poller has fetched it.'}</p>
          </Empty>
        </div>
      </section>
    )
  }

  const pending = data.rows.every((r) => r.pending)

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Fantasy</h2>
          <span className="shead__link" style={{ color: 'var(--ink-3)' }}>
            {data.league_name} · gameweek {data.gameweek}
          </span>
        </div>

        {pending && (
          <Empty title="Registered, not yet scored">
            <p>{data.empty_message}</p>
          </Empty>
        )}

        <div className="table-scroll" style={{ marginTop: pending ? 24 : 0 }}>
          <table className="table">
            <caption className="sr-only">Mini-league {data.league_id} standings</caption>
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

        {data.unmapped.length > 0 && (
          <p className="tnote">
            {data.unmapped.length} entry in this league is not mapped to a person yet
            (id {data.unmapped.join(', ')}). Set it on the admin page.
          </p>
        )}

        <p className="tnote">
          Squads, captains, differentials and projected points appear once gameweek one has
          been scored.
        </p>
        <StaleNote freshness={data.freshness} label="Mini-league" />
      </div>
    </section>
  )
}
