/**
 * Table and matches on one page.
 *
 * They answer the same question a few minutes apart — who is winning, and who
 * plays next — so making them two destinations meant a round trip through the
 * nav for something that fits on one screen. A segmented control switches
 * between them and the URL follows, so a link to the fixtures still works.
 */

import { lazy, Suspense } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useProjectedTable, useTable } from '@/api/queries'
import { Crest } from '@/components/Crest'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'
import { signed } from '@/lib/format'
import type { TableRow } from '@/api/types'

const Fixtures = lazy(() =>
  import('@/routes/Fixtures').then((m) => ({ default: m.Fixtures })),
)

type View = 'table' | 'projected' | 'matches'

const VIEWS: ReadonlyArray<[View, string]> = [
  ['table', 'Table'],
  ['projected', 'Projected'],
  ['matches', 'Matches'],
]

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

function TableView({ view }: { view: 'table' | 'projected' }) {
  const actual = useTable()
  const projected = useProjectedTable(view === 'projected')
  const active = view === 'table' ? actual : projected
  const rows = active.data?.rows ?? []

  if (active.isLoading) return <TableSkeleton rows={20} />
  if (rows.length === 0) {
    return (
      <Empty title="The table has not loaded">
        <p>
          {active.data?.empty_message ??
            'It appears as soon as the fixture list has been fetched.'}
        </p>
      </Empty>
    )
  }

  return (
    <>
      {view === 'table' && !actual.data?.season_started && (
        <Empty title="Nobody has played yet">
          <p>{actual.data?.empty_message}</p>
        </Empty>
      )}
      <div className="table-scroll" style={{ marginTop: 16 }}>
        <table className="table">
          <caption className="sr-only">
            {view === 'table'
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
        {view === 'table'
          ? 'Built from finished fixtures, so the order is right before the official table updates.'
          : (projected.data?.method ?? '')}
      </p>
      {active.data && <StaleNote freshness={active.data.freshness} label="Data" />}
    </>
  )
}

export function League() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const raw = params.get('view')
  const view: View = raw === 'matches' || raw === 'projected' ? raw : 'table'

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>{view === 'matches' ? 'Matches' : 'Table'}</h2>
          <span className="seg" role="tablist" aria-label="View">
            {VIEWS.map(([key, label]) => (
              <button
                key={key}
                role="tab"
                type="button"
                aria-selected={view === key}
                onClick={() =>
                  // Replace rather than push: flipping between two views of the
                  // same page should not fill up the back button.
                  navigate(key === 'table' ? '/table' : `/table?view=${key}`, { replace: true })
                }
              >
                {label}
              </button>
            ))}
          </span>
        </div>

        {view === 'matches' ? (
          <Suspense fallback={<TableSkeleton rows={5} />}>
            <Fixtures embedded />
          </Suspense>
        ) : (
          <TableView view={view} />
        )}
      </div>
    </section>
  )
}
