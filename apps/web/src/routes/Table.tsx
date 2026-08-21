import { useState } from 'react'
import { useProjectedTable, useTable } from '@/api/queries'
import { Crest } from '@/components/Crest'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'
import { signed } from '@/lib/format'
import type { TableRow } from '@/api/types'

type View = 'actual' | 'projected'

function Rows({ rows, showModelled }: { rows: TableRow[]; showModelled: boolean }) {
  return (
    <tbody>
      {rows.map((row) => (
        <tr key={row.club.short_name}>
          <td>
            <span className="pos">{row.position}</span>
          </td>
          <td>
            <span className="club">
              <Crest club={row.club} />
              <b>{row.club.full_name}</b>
              {showModelled && row.modelled && (
                <span className="tag" title={row.note ?? undefined}>
                  modelled
                </span>
              )}
            </span>
          </td>
          <td className="sec">{row.played}</td>
          <td className="sec">{row.won}</td>
          <td className="sec">{row.drawn}</td>
          <td className="sec">{row.lost}</td>
          <td className="sec">{signed(row.goal_difference)}</td>
          <td className="pts">{row.points}</td>
          <td className="form">
            {row.form.length === 0 ? (
              <span className="form--empty">—</span>
            ) : (
              row.form.map((r, i) => <i key={i} data-r={r} />)
            )}
          </td>
        </tr>
      ))}
    </tbody>
  )
}

export function Table() {
  const [view, setView] = useState<View>('actual')
  const actual = useTable()
  const projected = useProjectedTable(view === 'projected')

  const active = view === 'actual' ? actual : projected
  const rows = active.data?.rows ?? []

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Table</h2>
          <span className="seg" role="tablist" aria-label="Table view">
            <button
              role="tab"
              aria-selected={view === 'actual'}
              onClick={() => setView('actual')}
              type="button"
            >
              Actual
            </button>
            <button
              role="tab"
              aria-selected={view === 'projected'}
              onClick={() => setView('projected')}
              type="button"
            >
              Projected
            </button>
          </span>
        </div>

        {active.isLoading ? (
          <TableSkeleton rows={20} />
        ) : rows.length === 0 ? (
          <Empty title="The table has not loaded">
            <p>
              {active.data?.empty_message ??
                'It will appear as soon as the fixture list has been fetched.'}
            </p>
          </Empty>
        ) : (
          <>
            {view === 'actual' && !actual.data?.season_started && (
              <Empty title="Nobody has played yet">
                <p>{actual.data?.empty_message}</p>
              </Empty>
            )}
            <div className="table-scroll" style={{ marginTop: 16 }}>
              <table className="table">
                <caption className="sr-only">
                  {view === 'actual'
                    ? 'Premier League table, computed from finished fixtures'
                    : 'Projected Premier League table'}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Pos</th>
                    <th scope="col">Club</th>
                    <th scope="col">Pl</th>
                    <th scope="col">W</th>
                    <th scope="col">D</th>
                    <th scope="col">L</th>
                    <th scope="col">GD</th>
                    <th scope="col">Pts</th>
                    <th scope="col">Form</th>
                  </tr>
                </thead>
                <Rows rows={rows} showModelled={view === 'projected'} />
              </table>
            </div>

            <p className="tnote">
              {view === 'actual'
                ? 'Built from finished fixtures, so the order is right before the official table updates.'
                : (projected.data?.method ?? '')}
            </p>
            {active.data && <StaleNote freshness={active.data.freshness} label="Data" />}
          </>
        )}
      </div>
    </section>
  )
}
