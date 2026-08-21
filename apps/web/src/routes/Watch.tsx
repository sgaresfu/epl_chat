import { useMe, useWatchStats } from '@/api/queries'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'

export function Watch() {
  const { data, isLoading } = useWatchStats()
  const { data: me } = useMe()

  if (isLoading || !data) return <TableSkeleton rows={4} />

  const nothingYet = data.watched === 0

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Watch log</h2>
          <span className="shead__link" style={{ color: 'var(--ink-3)' }}>
            {me?.person.city}
          </span>
        </div>

        {nothingYet && (
          <Empty title="Nothing logged yet">
            <p>
              A match can be marked watched from the moment it kicks off until twelve
              hours after full time. The first one is Arsenal against Coventry.
            </p>
          </Empty>
        )}

        <div className="stats" style={{ marginTop: nothingYet ? 24 : 0 }}>
          <div className="stats__cell" data-soft={nothingYet}>
            <b>{data.watched}</b>
            <span>matches watched</span>
          </div>
          <div className="stats__cell" data-soft={nothingYet}>
            <b>{data.percent}%</b>
            <span>of all {data.total_matches}</span>
          </div>
          <div className="stats__cell" data-soft={nothingYet}>
            <b>{data.hours}</b>
            <span>hours, give or take</span>
          </div>
          <div className="stats__cell" data-soft={data.night_medals === 0}>
            <b>{data.night_medals}</b>
            <span>night medals</span>
          </div>
        </div>

        <p className="tnote">
          A night medal is a match watched between midnight and 05:00 in your own
          timezone &mdash; so the same kick-off can earn one in {me?.person.city ?? 'Alaska'} and
          not in Lviv. Hours are estimated at two per match. Your current streak is{' '}
          {data.streak} {data.streak === 1 ? 'round' : 'rounds'}.
        </p>
        <StaleNote freshness={data.freshness} label="Fixtures" />
      </div>
    </section>
  )
}
