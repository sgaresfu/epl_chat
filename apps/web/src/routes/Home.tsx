import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useHome, useMe, usePredictions, useTable } from '@/api/queries'
import { Crest } from '@/components/Crest'
import { FourCities } from '@/components/FourCities'
import { SeasonTimeline } from '@/components/SeasonTimeline'
import { Empty, StaleNote, TableSkeleton, TileSkeleton } from '@/components/states'
import { countdown, countdownWords, signed } from '@/lib/format'
import { headline } from '@/lib/headline'

/** Ticks once a second, but only while a countdown is actually running. */
function useTick(active: boolean): number {
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setTick((n) => n + 1), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  return 0
}

function NextMatch() {
  const { data, isLoading } = useHome()
  const { data: me } = useMe()
  const [start] = useState(() => Date.now())

  const seconds = data?.next_match.countdown_seconds ?? null
  const running = seconds !== null && seconds > 0
  useTick(running)

  if (isLoading) {
    return (
      <div className="board">
        <span className="skel" style={{ display: 'block', height: 240, borderRadius: 20 }} />
      </div>
    )
  }

  const next = data?.next_match
  if (!next?.fixture) {
    return (
      <Empty title="No match scheduled">
        <p>{next?.message ?? 'The fixture list has not loaded yet.'}</p>
      </Empty>
    )
  }

  const fixture = next.fixture
  const elapsed = (Date.now() - start) / 1000
  const remaining = seconds === null ? 0 : Math.max(0, seconds - elapsed)

  return (
    <div className="board">
      <p className="board__label">{next.in_play ? 'Live' : 'Next match'}</p>

      <div className="tie">
        <span className="side">
          <Crest club={fixture.home} size={44} />
          {fixture.home.name}
        </span>
        <span className="tie__v">vs</span>
        <span className="side">
          {fixture.away.name}
          <Crest club={fixture.away} size={44} />
        </span>
      </div>

      {next.in_play ? (
        <p className="score">
          {fixture.home_score ?? 0}–{fixture.away_score ?? 0}
          <small>{fixture.minutes}&rsquo; · live</small>
        </p>
      ) : (
        <p className="countdown">
          <span aria-hidden="true">{countdown(remaining)}</span>
          <span className="sr-only">{countdownWords(remaining)} until kick-off</span>
          <small>until kick-off</small>
        </p>
      )}

      <FourCities times={fixture.local_times} me={me?.person.key} />
    </div>
  )
}

function TablePreview() {
  const { data, isLoading, error } = useTable()

  if (isLoading) return <TableSkeleton rows={6} />
  if (error || !data) {
    return (
      <Empty title="The table is not available">
        <p>It will appear as soon as the poller has fetched the fixture list.</p>
      </Empty>
    )
  }

  if (!data.season_started) {
    return (
      <>
        <Empty title="Nobody has kicked a ball yet">
          <p>{data.empty_message}</p>
        </Empty>
        <StaleNote freshness={data.freshness} label="Fixtures" />
      </>
    )
  }

  const rows = data.rows.slice(0, 5)
  return (
    <>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Pos</th>
              <th scope="col">Club</th>
              <th scope="col">Pl</th>
              <th scope="col">GD</th>
              <th scope="col">Pts</th>
              <th scope="col">Form</th>
            </tr>
          </thead>
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
                  </span>
                </td>
                <td className="sec">{row.played}</td>
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
        </table>
      </div>
      <StaleNote freshness={data.freshness} label="Table" />
    </>
  )
}

function PredictionTile() {
  const { data, isLoading } = usePredictions()
  if (isLoading || !data) return <TileSkeleton />

  const filed = data.predictions.filter((p) => p.filed)
  const open = data.predictions.filter((p) => !p.filed)

  return (
    <div className="tile">
      <h3>Predictions</h3>
      <p className="tile__big">
        {filed.length}
        <span> of {data.predictions.length} filed</span>
      </p>
      <div className="lb">
        {data.predictions.map((p) => (
          <div className="lb__row" key={p.person}>
            <span className="lb__i">{p.person.slice(0, 1).toUpperCase()}</span>
            <span className="lb__who">{p.person.toUpperCase()}</span>
            {p.filed ? (
              <span className="lb__open">{p.redacted ? 'Filed · sealed' : 'Filed'}</span>
            ) : (
              <span className="lb__open">{data.locked ? 'Did not file' : 'Still open'}</span>
            )}
          </div>
        ))}
      </div>
      <p>
        {data.locked
          ? 'Locked. Every table is now visible to everyone.'
          : open.length > 0
            ? `${open.length} still unfiled. Everything seals the moment Arsenal kick off.`
            : 'All four are in. Everything seals at kick-off.'}
      </p>
    </div>
  )
}

export function Home() {
  const { data } = useHome()
  const { data: predictions } = usePredictions()

  const unfiled = predictions?.predictions.filter((p) => !p.filed).length ?? 0

  return (
    <>
      <div className="wrap">
        <div className="hero">
          <p className="eyebrow">Matchweek {Math.max(1, (data?.season.gameweeks_played ?? 0) + 1)}</p>
          <h1>{headline(data)}</h1>
          <p className="lead">
            {data?.line_of_the_day ??
              'Four predictions. Everything locks the moment the first ball is kicked.'}
          </p>
          <div className="cta">
            <Link className="btn" to="/predictions">
              {unfiled > 0 ? 'File your prediction' : 'See the predictions'}
            </Link>
            <Link className="btn btn--plain" to="/table">
              See the table
            </Link>
          </div>
        </div>

        <NextMatch />
      </div>

      <section className="section">
        <div className="wrap">
          <div className="shead">
            <h2>Table</h2>
            <Link className="shead__link" to="/table">
              Full table
            </Link>
          </div>
          <TablePreview />
        </div>
      </section>

      <hr className="rule" />

      <section className="section">
        <div className="wrap">
          <div className="shead">
            <h2>Standings</h2>
            <Link className="shead__link" to="/leaderboard">
              How scoring works
            </Link>
          </div>
          <div className="tiles">
            <PredictionTile />
            <div className="tile">
              <h3>Fantasy · Gameweek 1</h3>
              <p className="tile__big">
                —<span> not yet scored</span>
              </p>
              <p>
                Live points appear once the first match kicks off. The mini-league orders
                itself after gameweek one is scored.
              </p>
            </div>
          </div>
        </div>
      </section>

      <hr className="rule" />

      <section className="section" style={{ paddingTop: 0 }}>
        <div className="wrap">{data?.season ? <SeasonTimeline season={data.season} /> : <TileSkeleton height={280} />}</div>
      </section>
    </>
  )
}
