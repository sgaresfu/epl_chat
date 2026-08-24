/**
 * Predictions and the leaderboard on one page.
 *
 * Stacked, four twenty-club tables is eighty rows of scrolling for something
 * whose whole interest is the disagreements. Laid out as four columns against
 * a shared position axis, it is one screen and the differences are what you
 * see first. Rows where everybody agreed are tinted down, so scanning finds
 * the arguments rather than the consensus.
 *
 * The awards were stored from the start and never rendered, which is why they
 * appeared to be missing.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useClubs, useLeaderboard, useMe, usePredictions } from '@/api/queries'
import { Crest } from '@/components/Crest'
import { Empty, TableSkeleton } from '@/components/states'
import { PickRecord } from '@/components/PickRecord'
import { countdownWords } from '@/lib/format'
import type { AwardPicks, Club, Prediction } from '@/api/types'

const ORDER = ['coyg', 'aure', 'twzt', 'bulba'] as const

const AWARD_ROWS: ReadonlyArray<[keyof AwardPicks, string]> = [
  ['golden_boot', 'Golden Boot'],
  ['golden_glove', 'Golden Glove'],
  ['defender', 'Defender'],
  ['playmaker', 'Playmaker'],
  ['player_of_the_season', 'Player of the Season'],
]

function zoneLabel(position: number): string | null {
  if (position === 1) return 'Champions League'
  if (position === 5) return 'Europa and the rest'
  if (position === 18) return 'Relegation'
  return null
}

function TableGrid({
  filed,
  clubs,
}: {
  filed: Prediction[]
  clubs: Map<string, Club>
}) {
  const rows = Array.from({ length: 20 }, (_, i) => i)

  return (
    <div className="pred-grid">
      <span className="pred-grid__head" />
      {filed.map((p) => (
        <span className="pred-grid__head" key={p.person}>
          {p.person.toUpperCase()}
        </span>
      ))}

      {rows.map((index) => {
        const picks = filed.map((p) => p.table[index])
        const agreed = picks.every((c) => c && c === picks[0])
        const zone = zoneLabel(index + 1)
        return (
          <div key={index} style={{ display: 'contents' }}>
            {zone && <span className="pred-grid__zone">{zone}</span>}
            <span className="pred-grid__pos">{index + 1}</span>
            {picks.map((short, i) => {
              const club = short ? clubs.get(short) : undefined
              return (
                <span
                  className={`pred-cell${agreed ? ' pred-row--agreed' : ''}`}
                  key={`${filed[i]?.person}-${index}`}
                >
                  {club && <Crest club={club} size={20} />}
                  <b>{club?.name ?? '—'}</b>
                </span>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}

function Awards({ filed }: { filed: Prediction[] }) {
  return (
    <div className="awards">
      <span className="pred-grid__head" style={{ textAlign: 'left' }} />
      {filed.map((p) => (
        <span className="pred-grid__head" key={p.person}>
          {p.person.toUpperCase()}
        </span>
      ))}

      {AWARD_ROWS.map(([key, label]) => (
        <div key={key} style={{ display: 'contents' }}>
          <span className="awards__label">{label}</span>
          {filed.map((p) => {
            const value = p.awards?.[key] ?? ''
            return (
              <span
                className="awards__pick"
                key={`${p.person}-${key}`}
                data-empty={!value}
                title={value || 'No pick'}
              >
                {value || '—'}
              </span>
            )
          })}
        </div>
      ))}
    </div>
  )
}

function ChampionsLeague({ filed }: { filed: Prediction[] }) {
  const rows: ReadonlyArray<[string, (p: Prediction) => string]> = [
    ['Winner', (p) => p.champions_league?.winner ?? ''],
    ['Finalists', (p) =>
      [p.champions_league?.finalist_a, p.champions_league?.finalist_b]
        .filter(Boolean)
        .join(' v '),
    ],
    ['Top scorer', (p) => p.champions_league?.top_scorer ?? ''],
  ]
  const anything = filed.some((p) => rows.some(([, get]) => get(p)))
  if (!anything) return null

  return (
    <div className="awards" style={{ marginTop: 30 }}>
      <span className="pred-grid__head" style={{ textAlign: 'left' }} />
      {filed.map((p) => (
        <span className="pred-grid__head" key={p.person}>
          {p.person.toUpperCase()}
        </span>
      ))}
      {rows.map(([label, get]) => (
        <div key={label} style={{ display: 'contents' }}>
          <span className="awards__label">{label}</span>
          {filed.map((p) => {
            const value = get(p)
            return (
              <span
                className="awards__pick"
                key={`${p.person}-${label}`}
                data-empty={!value}
                title={value || 'No pick'}
              >
                {value || '—'}
              </span>
            )
          })}
        </div>
      ))}
    </div>
  )
}

export function Standings() {
  const { data, isLoading } = useLeaderboard()
  const { data: me } = useMe()
  if (isLoading || !data) return <TableSkeleton rows={4} />

  return (
    <>
      {data.empty_message && (
        <Empty title="No points yet">
          <p>{data.empty_message}</p>
        </Empty>
      )}
      <div className="table-scroll" style={{ marginTop: data.empty_message ? 20 : 0 }}>
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
        <b style={{ color: 'var(--ink)' }}>3</b> per exact position ·{' '}
        <b style={{ color: 'var(--ink)' }}>1</b> within one place ·{' '}
        <b style={{ color: 'var(--ink)' }}>5</b> per award ·{' '}
        <b style={{ color: 'var(--ink)' }}>10</b> perfect top four ·{' '}
        <b style={{ color: 'var(--ink)' }}>15</b> champion plus all three relegated
      </p>
    </>
  )
}

type Tab = 'season' | 'matches'

export function Predictions() {
  const [tab, setTab] = useState<Tab>('season')
  const { data, isLoading } = usePredictions()
  const { data: clubList } = useClubs()
  const { data: me } = useMe()
  const clubs = new Map((clubList ?? []).map((c) => [c.short_name, c]))

  if (isLoading || !data) return <TableSkeleton rows={10} />

  const byPerson = new Map(data.predictions.map((p) => [p.person, p]))
  const filed = ORDER.map((k) => byPerson.get(k)).filter(
    (p): p is Prediction => Boolean(p?.filed && p.table.length === 20),
  )
  const sealed = data.predictions.filter((p) => p.filed && p.redacted)
  const missing = data.predictions.filter((p) => !p.filed)

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Predictions</h2>
          {/* Two games live here: the season-long table filed before the
              first ball, and the week-by-week scorelines. Same idea, very
              different cadence, so they share a page rather than a nav slot. */}
          <span className="seg" role="tablist" aria-label="Which predictions">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'season'}
              onClick={() => setTab('season')}
            >
              Season table
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'matches'}
              onClick={() => setTab('matches')}
            >
              Match picks
            </button>
          </span>
          {tab === 'season' && !data.locked && (
            <Link className="btn" to="/predictions/build" style={{ marginLeft: 'auto' }}>
              {byPerson.get(me?.person.key ?? '')?.filed ? 'Edit yours' : 'File yours'}
            </Link>
          )}
          {tab === 'season' && (
            <span
              className="shead__link"
              style={{
                color: data.locked ? 'var(--ink-3)' : 'var(--blue)',
                marginLeft: data.locked ? 'auto' : 0,
              }}
            >
              {data.locked ? 'Locked' : `Locks in ${countdownWords(data.seconds_remaining)}`}
            </span>
          )}
        </div>

        {tab === 'matches' ? (
          <>
            <PickRecord me={me?.person.key} />
            <p className="tnote" style={{ marginTop: 18 }}>
              Pick a scoreline on any match from{' '}
              <Link className="shead__link" to="/table?view=matches">
                Table &amp; matches
              </Link>
              . Picks close at kick-off and stay private until then.
            </p>
          </>
        ) : (
          <>
        <Standings />

        {sealed.length > 0 && (
          <p className="tnote" style={{ marginTop: 22 }}>
            {sealed.length} prediction{sealed.length === 1 ? ' is' : 's are'} filed and sealed
            until the deadline.
          </p>
        )}
        {missing.length > 0 && (
          <p className="tnote">
            {missing.map((p) => p.person.toUpperCase()).join(', ')}{' '}
            {data.locked ? 'did not file.' : 'have not filed yet.'}
          </p>
        )}

        {filed.length > 0 && (
          <>
            <hr className="rule" style={{ margin: '44px 0 30px' }} />
            <div className="shead">
              <h2 style={{ fontSize: 21 }}>The tables</h2>
              <span className="shead__link" style={{ color: 'var(--ink-3)' }}>
                shaded rows are where everybody agreed
              </span>
            </div>
            <TableGrid filed={filed} clubs={clubs} />

            <hr className="rule" style={{ margin: '44px 0 30px' }} />
            <div className="shead">
              <h2 style={{ fontSize: 21 }}>Awards</h2>
            </div>
            <Awards filed={filed} />

            <ChampionsLeague filed={filed} />
          </>
        )}
          </>
        )}
      </div>
    </section>
  )
}
