import { usePredictions } from '@/api/queries'
import { useClubs } from '@/api/queries'
import { Crest } from '@/components/Crest'
import { Empty, TableSkeleton } from '@/components/states'
import { countdownWords } from '@/lib/format'
import type { Club, Prediction } from '@/api/types'

function Filed({ prediction, clubs }: { prediction: Prediction; clubs: Map<string, Club> }) {
  if (prediction.redacted) {
    return (
      <Empty title={`${prediction.person.toUpperCase()} has filed`}>
        <p>
          Sealed until the deadline. Nobody sees anybody else&rsquo;s table before the lock —
          otherwise the last to file just copies the best one on screen.
        </p>
      </Empty>
    )
  }

  return (
    <div className="table-scroll">
      <table className="table">
        <caption className="sr-only">{prediction.person} predicted table</caption>
        <thead>
          <tr>
            <th scope="col">Pos</th>
            <th scope="col">Club</th>
          </tr>
        </thead>
        <tbody>
          {prediction.table.map((short, index) => {
            const club = clubs.get(short)
            return (
              <tr key={short}>
                <td>
                  <span className="pos">{index + 1}</span>
                </td>
                <td>
                  <span className="club">
                    {club && <Crest club={club} />}
                    <b>{club?.full_name ?? short}</b>
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function Predictions() {
  const { data, isLoading } = usePredictions()
  const { data: clubList } = useClubs()
  const clubs = new Map((clubList ?? []).map((c) => [c.short_name, c]))

  if (isLoading || !data) return <TableSkeleton rows={10} />

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Predictions</h2>
          <span className="shead__link" style={{ color: data.locked ? 'var(--ink-3)' : 'var(--blue)' }}>
            {data.locked
              ? 'Locked'
              : `Locks in ${countdownWords(data.seconds_remaining)}`}
          </span>
        </div>

        {data.predictions.map((prediction) => (
          <div key={prediction.person} style={{ marginBottom: 40 }}>
            <h3 style={{ fontSize: 21, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 14 }}>
              {prediction.person.toUpperCase()}
              {prediction.submitted_at && (
                <span style={{ fontSize: 13, color: 'var(--ink-3)', fontWeight: 400, marginLeft: 10 }}>
                  filed {new Date(prediction.submitted_at).toISOString().slice(0, 10)}
                </span>
              )}
            </h3>

            {prediction.filed ? (
              <Filed prediction={prediction} clubs={clubs} />
            ) : (
              <Empty title={data.locked ? 'Did not file' : 'Still open'}>
                <p>
                  {data.locked
                    ? 'No table was filed before the deadline, so this slot scores zero for the season.'
                    : `The slot stays open until the lock — ${countdownWords(data.seconds_remaining)} left.`}
                </p>
              </Empty>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
