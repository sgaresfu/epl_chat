/**
 * The all-time match-pick record.
 *
 * Four people, one table, and the numbers that actually separate them. Raw
 * accuracy is the least interesting column on it — everyone lands somewhere
 * near the same outcome rate, because most matches have an obvious favourite.
 * What differs is *how* each of them gets there, so the table carries the
 * shape of a person's judgement rather than just its score:
 *
 * - **Bold** is how often somebody backs against the market, and how often
 *   that comes off. It is the difference between reading a game and reading
 *   a price.
 * - **Edge** is points above what backing the favourite every single week
 *   would have scored. Positive means they are genuinely adding something.
 * - **Goal bias** says whether they systematically expect more or fewer
 *   goals than the league produces, which is the most readable habit there is.
 *
 * Everything recomputes from picks and results on every read, so it is never
 * stale and there is nothing to invalidate when a match finishes.
 */

import { usePickStats } from '@/api/queries'
import { Empty, TableSkeleton } from '@/components/states'
import type { PickStats } from '@/api/types'

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="metric" title={hint}>
      <p className="metric__label">{label}</p>
      <p className="metric__value">{value}</p>
    </div>
  )
}

function Leader({ row, mine }: { row: PickStats; mine: boolean }) {
  return (
    <div className="record" data-mine={mine}>
      <div className="record__head">
        <span className="record__who">
          {row.person.name}
          {mine && <span className="tag">you</span>}
        </span>
        <span className="record__points">
          {row.points}
          <small>pts</small>
        </span>
      </div>

      <div className="record__grid">
        <Metric
          label="Exact"
          value={`${row.exact} · ${row.exact_pct}%`}
          hint="Scorelines called exactly right"
        />
        <Metric
          label="Result"
          value={`${row.outcomes} · ${row.outcome_pct}%`}
          hint="Right team won, or right draw"
        />
        <Metric label="Per pick" value={String(row.points_per_pick)} hint="Average points per settled pick" />
        <Metric
          label="Streak"
          value={`${row.current_streak} · best ${row.best_streak}`}
          hint="Consecutive correct results"
        />
      </div>

      {row.with_market > 0 && (
        <div className="record__market">
          <span
            className="record__edge"
            data-dir={row.edge > 0 ? 'up' : row.edge < 0 ? 'down' : undefined}
            title="Points above or below simply backing the bookmaker's favourite every week"
          >
            {row.edge > 0 ? '+' : ''}
            {row.edge} vs the favourite
          </span>
          <span title="Picks made against the bookmaker's favourite, and how many came off">
            {row.bold} bold · {row.bold_hits} landed
            {row.bold > 0 && ` (${row.bold_pct}%)`}
          </span>
        </div>
      )}

      <p className="record__habit">
        {row.goal_bias > 0.25
          ? `Expects ${row.goal_bias} more goals a game than the league produces.`
          : row.goal_bias < -0.25
            ? `Expects ${Math.abs(row.goal_bias)} fewer goals a game than the league produces.`
            : 'Reads the number of goals about right.'}
        {row.settled > 0 && ` Backs the home side ${row.home_pct}% of the time.`}
      </p>
    </div>
  )
}

export function PickRecord({ me }: { me: string | undefined }) {
  const { data, isLoading } = usePickStats()

  if (isLoading) return <TableSkeleton rows={4} />
  if (!data || data.total_settled === 0) {
    return (
      <Empty title="No picks settled yet">
        <p>{data?.empty_message ?? 'Pick a scoreline on any match before it kicks off.'}</p>
        {data?.scoring && <p className="tnote">{data.scoring}</p>}
      </Empty>
    )
  }

  return (
    <>
      <div className="records stagger">
        {data.rows.map((row) => (
          <Leader key={row.person.key} row={row} mine={row.person.key === me} />
        ))}
      </div>
      <p className="tnote">
        {data.scoring} Settled across {data.total_settled} pick
        {data.total_settled === 1 ? '' : 's'}.
      </p>
    </>
  )
}
