import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  useFixtures,
  useFplSquads,
  useHome,
  useMe,
  useNews,
  usePlayerStats,
  usePredictions,
  useTable,
} from '@/api/queries'
import { Crest } from '@/components/Crest'
import { FourCities } from '@/components/FourCities'
import { ManagerPhotos } from '@/components/ManagerPhotos'
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
          <small>
            <span className="live-badge">live</span> · {fixture.minutes}&rsquo;
          </small>
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

function ago(iso: string | null): string {
  if (!iso) return ''
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 60) return `${Math.max(1, minutes)}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

/** The last few results, so the front page shows what actually happened. */
function Results() {
  const { data } = useFixtures()
  const finished = (data?.fixtures ?? [])
    .filter((f) => f.finished && f.home_score !== null)
    .sort((a, b) => (b.kickoff ?? '').localeCompare(a.kickoff ?? ''))
    .slice(0, 6)

  if (finished.length === 0) return null

  return (
    <section className="section" style={{ paddingBottom: 0 }}>
      <div className="wrap">
        <div className="shead">
          <h2>Results</h2>
          <Link className="shead__link" to="/table?view=matches">
            All matches
          </Link>
        </div>
        <div className="results">
          {finished.map((f) => {
            const h = f.home_score ?? 0
            const a = f.away_score ?? 0
            return (
              <Link className="result" to="/table?view=matches" key={f.id}>
                <div className="result__teams" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                  <span className="result__row" data-outcome={h < a ? 'lost' : 'won'}>
                    <Crest club={f.home} size={18} />
                    <span className="result__name">{f.home.name}</span>
                    <span className="result__score">{h}</span>
                  </span>
                  <span className="result__row" data-outcome={a < h ? 'lost' : 'won'}>
                    <Crest club={f.away} size={18} />
                    <span className="result__name">{f.away.name}</span>
                    <span className="result__score">{a}</span>
                  </span>
                </div>
                <p className="result__when">{ago(f.kickoff)}</p>
              </Link>
            )
          })}
        </div>
      </div>
    </section>
  )
}

/** Who is actually doing something this season. */
function Highlights() {
  const { data } = usePlayerStats()
  const players = data?.players ?? []
  if (players.length === 0 || (data?.matches_played ?? 0) === 0) return null

  const best = (key: 'goals' | 'assists' | 'points' | 'bonus') =>
    [...players].sort((a, b) => b[key] - a[key] || b.minutes - a.minutes)[0]

  const scorer = best('goals')
  const creator = best('assists')
  const points = best('points')

  const tiles = [
    ['Top scorer', scorer, `${scorer?.goals ?? 0}`],
    ['Most assists', creator, `${creator?.assists ?? 0}`],
    ['Most points', points, `${points?.points ?? 0}`],
  ] as const

  return (
    <section className="section" style={{ paddingBottom: 0 }}>
      <div className="wrap">
        <div className="shead">
          <h2>Leading the way</h2>
          <Link className="shead__link" to="/stats">
            All statistics
          </Link>
        </div>
        <div className="highlights">
          {tiles.map(([label, player, value]) => (
            <div className="highlight" key={label}>
              <p className="highlight__label">{label}</p>
              <p className="highlight__value">{value}</p>
              <p className="highlight__who">
                {player ? `${player.name} · ${player.club}` : '—'}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/** The mini-league as it stands right now, not once a round is settled. */
function FantasyTile() {
  const { data } = useFplSquads()
  const { data: me } = useMe()
  const squads = data?.squads ?? []

  if (squads.length === 0) {
    return (
      <div className="tile">
        <h3>Fantasy</h3>
        <p className="tile__big">
          —<span> squads not in yet</span>
        </p>
        <p>{data?.empty_message ?? 'They appear once the gameweek deadline passes.'}</p>
      </div>
    )
  }

  const lead = Math.max(...squads.map((s) => s.live_points))
  const top = squads[0]

  return (
    <div className="tile">
      <h3>Fantasy · Gameweek {data?.gameweek}</h3>
      <p className="tile__big">
        {lead}
        <span> {top?.person?.toUpperCase() ?? ''}, live</span>
      </p>
      <div className="fpl-mini">
        {squads.map((squad) => (
          <div className="fpl-mini__row" key={squad.entry_id} data-lead={squad.live_points === lead}>
            <span className="fpl-mini__who">
              {(squad.person ?? squad.entry_name).toUpperCase()}
              {squad.person === me?.person.key && (
                <span className="tag" style={{ marginLeft: 7 }}>
                  you
                </span>
              )}
            </span>
            {squad.captain && <span className="fpl-mini__cap">C {squad.captain.name}</span>}
            <span className="fpl-mini__pts">{squad.live_points}</span>
          </div>
        ))}
      </div>
      <p>
        {squads.reduce((n, s) => n + s.players_to_play, 0)} players still to come across the
        four squads.
      </p>
    </div>
  )
}

/** New uploads from the six channels. */
function LatestVideo() {
  const { data } = useNews()
  const videos = (data?.youtube ?? []).slice(0, 4)
  if (videos.length === 0) return null

  return (
    <section className="section" style={{ paddingTop: 0 }}>
      <div className="wrap">
        <div className="shead">
          <h2>Watching</h2>
          <Link className="shead__link" to="/news">
            All video
          </Link>
        </div>
        <div className="home-video">
          {videos.map((item) => (
            <a className="video" key={item.url} href={item.url} target="_blank" rel="noreferrer noopener">
              {item.image && (
                <div className="video__art">
                  <img src={item.image} alt="" loading="lazy" />
                </div>
              )}
              <p className="video__title">{item.title}</p>
              <p className="video__channel">
                {item.source} · {ago(item.published)}
              </p>
            </a>
          ))}
        </div>
      </div>
    </section>
  )
}

/** Three headlines with their pictures. */
function LatestNews() {
  const { data } = useNews()
  const items = (data?.sky ?? []).slice(0, 3)
  if (items.length === 0) return null

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Latest</h2>
          <Link className="shead__link" to="/news">
            More news
          </Link>
        </div>
        <div className="home-news">
          {items.map((item) => (
            <a
              className="home-news__item"
              key={item.url}
              href={item.url}
              target="_blank"
              rel="noreferrer noopener"
            >
              {item.image && (
                <div className="home-news__art">
                  <img src={item.image} alt="" loading="lazy" />
                </div>
              )}
              <p className="home-news__title">{item.title}</p>
              <p className="home-news__meta">
                {item.source} · {ago(item.published)}
              </p>
            </a>
          ))}
        </div>
      </div>
    </section>
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
            <FantasyTile />
          </div>
        </div>
      </section>

      <Results />

      <Highlights />

      <section className="section">
        <div className="wrap">
          <div className="shead">
            <h2>The era</h2>
          </div>
          <ManagerPhotos />
        </div>
      </section>

      <hr className="rule" style={{ marginTop: 64 }} />

      <section className="section" style={{ paddingTop: 0, marginTop: 64 }}>
        <div className="wrap">{data?.season ? <SeasonTimeline season={data.season} /> : <TileSkeleton height={280} />}</div>
      </section>

      <hr className="rule" />

      <LatestNews />

      <LatestVideo />
    </>
  )
}
