import { useState } from 'react'
import { useH2H, useLeaderboard, useMe } from '@/api/queries'
import { Crest } from '@/components/Crest'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'

const SCORING = [
  ['3', 'per club in its exact finishing position'],
  ['1', 'per club within one place'],
  ['5', 'per correct award'],
  ['10', 'for a perfect top four, in any order'],
  ['15', 'for the champion plus all three relegated'],
] as const

function HeadToHead({ people }: { people: { key: string; name: string }[] }) {
  const [a, setA] = useState(people[0]?.key ?? 'coyg')
  const [b, setB] = useState(people[1]?.key ?? 'aure')
  const { data, isLoading } = useH2H(a, b)

  return (
    <>
      <div className="shead" style={{ marginTop: 8 }}>
        <h2>Head to head</h2>
      </div>

      <div className="acts" style={{ marginTop: 0, marginBottom: 22 }}>
        {(['a', 'b'] as const).map((side) => (
          <span className="seg" key={side}>
            {people.map((p) => {
              const selected = side === 'a' ? a === p.key : b === p.key
              const other = side === 'a' ? b : a
              return (
                <button
                  key={p.key}
                  type="button"
                  aria-selected={selected}
                  disabled={p.key === other}
                  onClick={() => (side === 'a' ? setA(p.key) : setB(p.key))}
                >
                  {p.name}
                </button>
              )
            })}
          </span>
        ))}
      </div>

      {isLoading || !data ? (
        <TableSkeleton rows={5} />
      ) : data.empty_message ? (
        <Empty title="Nothing to compare">
          <p>{data.empty_message}</p>
        </Empty>
      ) : (
        <div className="tiles tiles--fit">
          <div className="tile">
            <h3>Agreed on</h3>
            <p className="tile__big">
              {data.agreement_count}
              <span> of 20 exactly</span>
            </p>
            <div className="lb">
              {data.agreements.slice(0, 6).map((row) => (
                <div className="lb__row" key={row.club.short_name}>
                  <span className="lb__i">{row.position}</span>
                  <Crest club={row.club} size={24} />
                  <span className="lb__who">{row.club.name}</span>
                </div>
              ))}
              {data.agreements.length === 0 && (
                <p style={{ marginTop: 0 }}>Not one club in the same place.</p>
              )}
            </div>
          </div>

          <div className="tile">
            <h3>Furthest apart</h3>
            <p className="tile__big">
              {data.gaps[0]?.distance ?? 0}
              <span> places at most</span>
            </p>
            <div className="lb">
              {data.gaps.slice(0, 6).map((row) => (
                <div className="lb__row" key={row.club.short_name}>
                  <Crest club={row.club} size={24} />
                  <span className="lb__who">{row.club.name}</span>
                  <span className="lb__v" style={{ fontSize: 15, fontWeight: 400 }}>
                    {row.a_position} v {row.b_position}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export function Leaderboard() {
  const { data, isLoading } = useLeaderboard()
  const { data: me } = useMe()

  if (isLoading || !data) return <TableSkeleton rows={4} />

  const people = data.rows.map((r) => ({ key: r.person.key, name: r.person.name }))

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Leaderboard</h2>
        </div>

        {data.empty_message && (
          <Empty title="No points yet">
            <p>{data.empty_message}</p>
          </Empty>
        )}

        <div className="table-scroll" style={{ marginTop: data.empty_message ? 24 : 0 }}>
          <table className="table">
            <caption className="sr-only">Prediction leaderboard</caption>
            <thead>
              <tr>
                <th scope="col">Pos</th>
                <th scope="col">Who</th>
                <th scope="col">Exact</th>
                <th scope="col">Table</th>
                <th scope="col">Awards</th>
                <th scope="col">Total</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.person.key}>
                  <td>
                    <span className="pos">{row.rank}</span>
                  </td>
                  <td>
                    <span className="club">
                      <b>{row.person.name}</b>
                      {row.person.key === me?.person.key && <span className="tag">you</span>}
                      {!row.filed && <span className="tag">{row.status}</span>}
                    </span>
                  </td>
                  <td className="sec">{row.exact_hits}</td>
                  <td className="sec">{row.table_points}</td>
                  <td className="sec">{row.award_points}</td>
                  <td className="pts">{row.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="tnote">
          {SCORING.map(([points, what]) => (
            <span key={what} style={{ display: 'block' }}>
              <b style={{ color: 'var(--ink)' }}>{points}</b> {what}
            </span>
          ))}
        </p>
        <StaleNote freshness={data.freshness} label="Table" />

        <hr className="rule" style={{ margin: '48px 0' }} />

        <HeadToHead people={people} />
      </div>
    </section>
  )
}
