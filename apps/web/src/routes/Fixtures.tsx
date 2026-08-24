/**
 * A round of matches, grouped by day.
 *
 * Time on the left, the two clubs meeting in the middle, the score where the
 * fixture separator would be. The winner reads solid and the loser recedes, so
 * a result is legible without a badge announcing it. Actions stay quiet until
 * the row is approached — on a touch screen, where there is no hover, they are
 * always shown.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '@/api/client'
import { keys, useFixtures, useLineups, useMe, usePicks } from '@/api/queries'
import { ScorePicker } from '@/components/ScorePicker'
import { Crest } from '@/components/Crest'
import { FourCities } from '@/components/FourCities'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'
import type { Fixture, FixturePicks, LineupSide } from '@/api/types'

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Group by the viewer's own local day, which is what "Saturday" means to them. */
function localDayKey(fixture: Fixture, me: string | undefined): string {
  const slot = fixture.local_times.find((t) => t.place === me) ?? fixture.local_times[0]
  return slot ? slot.iso.slice(0, 10) : 'unscheduled'
}

function dayLabel(key: string): { day: string; date: string } {
  if (key === 'unscheduled') return { day: 'Date to be confirmed', date: '' }
  const d = new Date(`${key}T12:00:00Z`)
  return {
    day: DAYS[d.getUTCDay()] ?? '',
    date: `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()] ?? ''}`,
  }
}

/** bet365 1X2, as implied probability rather than bare decimals.
 *
 * A price of 1.20 means little at a glance; "83%" means a great deal. The
 * three prices are converted to probabilities and normalised to remove the
 * bookmaker's overround, so the bar sums to 100 and the split is honest
 * about what the market actually thinks.
 *
 * Only before kick-off. These are pre-match prices, so printing them beside a
 * finished score says nothing about the match and reads as though the market
 * is still open. Nothing renders when there is no price either — an unlisted
 * match should look like an ordinary row, not an error.
 */
function OddsLine({ fixture }: { fixture: Fixture }) {
  const odds = fixture.odds
  if (fixture.started || fixture.finished) return null
  if (!odds?.available || odds.home == null || odds.draw == null || odds.away == null) return null

  const homeP = 1 / odds.home
  const drawP = 1 / odds.draw
  const awayP = 1 / odds.away
  const overround = homeP + drawP + awayP

  const legs = [
    { key: 'home', label: fixture.home.short_name, price: odds.home, from: odds.drift?.home, pct: (homeP / overround) * 100 },
    { key: 'draw', label: 'Draw', price: odds.draw, from: odds.drift?.draw, pct: (drawP / overround) * 100 },
    { key: 'away', label: fixture.away.short_name, price: odds.away, from: odds.drift?.away, pct: (awayP / overround) * 100 },
  ]

  return (
    <div className="match-odds">
      <div
        className="match-odds__bar"
        role="img"
        aria-label={legs.map((l) => `${l.label} ${Math.round(l.pct)}%`).join(', ')}
      >
        {legs.map((l) => (
          <span key={l.key} data-leg={l.key} style={{ width: `${l.pct}%` }} />
        ))}
      </div>
      <p className="match-odds__legend">
        <span className="match-odds__book">{odds.bookmaker}</span>
        {legs.map((l) => {
          // A price that has shortened means money came for it.
          const from = l.from
          const moved = from != null && from !== l.price
          const shorter = moved && l.price < from
          return (
            <span className="match-odds__leg" key={l.key}>
              <b>{l.label}</b> {Math.round(l.pct)}%
              <span className="match-odds__price">{l.price.toFixed(2)}</span>
              {moved && (
                <span className="match-odds__drift" data-dir={shorter ? 'in' : 'out'}>
                  {shorter ? '▼' : '▲'} {from.toFixed(2)}
                </span>
              )}
            </span>
          )
        })}
      </p>
    </div>
  )
}

/** One side's confirmed XI and bench, or nothing while waiting on a request. */
function LineupSideList({ label, side }: { label: string; side: LineupSide }) {
  return (
    <div className="lineup-side">
      <p className="lineup-side__head">
        {label} <span className="lineup-side__formation">{side.formation}</span>
      </p>
      <ol className="lineup-side__players">
        {side.starting.map((p) => (
          <li key={`${p.number}-${p.name}`}>
            {p.number != null && <b>{p.number}</b>} {p.name}
          </li>
        ))}
      </ol>
      {side.bench.length > 0 && (
        <p className="lineup-side__bench">Bench: {side.bench.map((p) => p.name).join(', ')}</p>
      )}
    </div>
  )
}

/** Fetched only while this panel is open -- confirmed line-ups is the one
 * thing in the app allowed to trigger an upstream call on request. */
function LineupsPanel({ fixture, open }: { fixture: Fixture; open: boolean }) {
  const { data, isLoading } = useLineups(fixture.id, open)
  if (!open) return null
  if (isLoading) return <p className="tnote">Checking line-ups…</p>
  if (!data?.available || !data.home || !data.away) {
    return <p className="tnote">{data?.reason ?? 'Line-ups are not available for this match.'}</p>
  }
  return (
    <>
      <p className="lineups__basis" data-confirmed={data.confirmed}>
        <span>{data.confirmed ? 'Confirmed' : 'Predicted'}</span>
        {data.basis}
      </p>
      <div className="lineups">
        <LineupSideList label={fixture.home.name} side={data.home} />
        <LineupSideList label={fixture.away.name} side={data.away} />
      </div>
    </>
  )
}

/**
 * Everyone's call on this match.
 *
 * Before kick-off only your own is shown, and only to you -- the server
 * withholds the rest, so there is nothing here to leak. Afterwards all four
 * appear with what each of them scored.
 */
function PicksRow({ fixture, picks }: { fixture: Fixture; picks: FixturePicks | undefined }) {
  if (!picks) return null

  if (picks.open_for_picks) {
    return (
      <ScorePicker
        fixtureId={fixture.id}
        home={fixture.home}
        away={fixture.away}
        homeGoals={picks.my_pick?.home_goals ?? null}
        awayGoals={picks.my_pick?.away_goals ?? null}
      />
    )
  }

  if (picks.picks.length === 0) return null

  return (
    <p className="calls">
      <span className="calls__label">Called</span>
      {picks.picks.map((p) => (
        <span
          className="calls__one"
          key={p.person}
          data-hit={p.exact ? 'exact' : p.outcome_hit ? 'outcome' : p.total_hit ? 'total' : 'miss'}
          title={
            p.points === null
              ? 'Not settled yet'
              : `${p.points} point${p.points === 1 ? '' : 's'}` +
                (p.exact ? ' — exact score' : p.outcome_hit ? ' — right result' : '') +
                (p.total_hit && !p.exact ? ', right number of goals' : '')
          }
        >
          <em>{p.person.toUpperCase()}</em>
          {p.home_goals}–{p.away_goals}
          {p.points !== null && <b>{p.points}</b>}
        </span>
      ))}
    </p>
  )
}

function Match({
  fixture,
  me,
  picks,
}: {
  fixture: Fixture
  me: string | undefined
  picks: FixturePicks | undefined
}) {
  const [showTimes, setShowTimes] = useState(false)
  const [showLineups, setShowLineups] = useState(false)
  const client = useQueryClient()
  const watched = me !== undefined && fixture.watched_by.includes(me)
  const slot = fixture.local_times.find((t) => t.place === me) ?? fixture.local_times[0]

  const toggle = useMutation({
    mutationFn: () => api.post('/api/watch', { fixture_id: fixture.id }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['fixtures'] })
      await client.invalidateQueries({ queryKey: keys.watch })
    },
  })

  const played = fixture.finished || fixture.started
  const h = fixture.home_score ?? 0
  const a = fixture.away_score ?? 0
  const live = fixture.started && !fixture.finished

  const result = (side: 'home' | 'away'): string | undefined => {
    if (!fixture.finished) return undefined
    if (h === a) return 'drew'
    return (side === 'home') === h > a ? 'won' : 'lost'
  }

  return (
    <div className="match-block">
      <div className="match">
        <span className="match__time">
          <b>{fixture.postponed ? '—' : (slot?.time ?? '')}</b>
          <span className="match__state" data-live={live}>
            {live ? `${fixture.minutes}'` : fixture.finished ? 'FT' : fixture.postponed ? 'PP' : ''}
          </span>
        </span>

        <span className="match__tie">
          <span className="match__side" data-result={result('home')}>
            <Crest club={fixture.home} size={26} />
            <span className="match__club">{fixture.home.name}</span>
          </span>
          <span className="match__score" data-played={played}>
            {played ? `${h}–${a}` : 'v'}
          </span>
          <span className="match__side match__side--away" data-result={result('away')}>
            <Crest club={fixture.away} size={26} />
            <span className="match__club">{fixture.away.name}</span>
          </span>
        </span>

        <span className="match__actions">
          {fixture.derby && <span className="match__badge">{fixture.derby}</span>}
          {fixture.watched_by.length > 0 && (
            <span className="match__watchers" title={`Watched by ${fixture.watched_by.join(', ')}`}>
              {fixture.watched_by.map((w) => (
                <span className="watcher" key={w}>
                  {w.slice(0, 1).toUpperCase()}
                </span>
              ))}
            </span>
          )}
          <button
            className="chip"
            type="button"
            aria-pressed={showTimes}
            onClick={() => setShowTimes((v) => !v)}
          >
            {showTimes ? 'Hide' : 'Where'}
          </button>
          {!fixture.postponed && (
            <button
              className="chip"
              type="button"
              aria-pressed={showLineups}
              onClick={() => setShowLineups((v) => !v)}
            >
              {showLineups ? 'Hide' : 'Line-ups'}
            </button>
          )}
          {(fixture.watch_open || watched) && (
            <button
              className={watched ? 'chip chip--done' : 'chip'}
              type="button"
              aria-pressed={watched}
              disabled={toggle.isPending}
              onClick={() => toggle.mutate()}
            >
              {watched ? 'Watched' : 'Mark watched'}
            </button>
          )}
        </span>
      </div>

      <OddsLine fixture={fixture} />

      <PicksRow fixture={fixture} picks={picks} />

      {toggle.isError && (
        <p className="picker__error" role="alert">
          {toggle.error instanceof ApiError ? toggle.error.message : 'Could not save that.'}
        </p>
      )}
      {showTimes && (
        <div style={{ padding: '4px 8px 18px' }}>
          <FourCities times={fixture.local_times} me={me} />
        </div>
      )}
      {showLineups && (
        <div style={{ padding: '4px 8px 18px' }}>
          <LineupsPanel fixture={fixture} open={showLineups} />
        </div>
      )}
    </div>
  )
}

export function Fixtures({ embedded = false }: { embedded?: boolean } = {}) {
  const [gameweek, setGameweek] = useState(1)
  const { data, isLoading } = useFixtures(gameweek)
  const { data: me } = useMe()
  const { data: picks } = usePicks(gameweek)
  const picksByFixture = new Map((picks?.fixtures ?? []).map((f) => [f.fixture_id, f]))

  const groups = new Map<string, Fixture[]>()
  for (const fixture of data?.fixtures ?? []) {
    const key = localDayKey(fixture, me?.person.key)
    groups.set(key, [...(groups.get(key) ?? []), fixture])
  }

  const body = (
    <>
      <div className="shead" style={embedded ? { marginTop: 4 } : undefined}>
        {!embedded && <h2>Matches</h2>}
        <span className="seg" role="group" aria-label="Gameweek">
          <button
            type="button"
            onClick={() => setGameweek((g) => Math.max(1, g - 1))}
            disabled={gameweek <= 1}
            aria-label="Previous gameweek"
          >
            ‹
          </button>
          <button type="button" aria-selected="true" role="tab">
            Gameweek {gameweek}
          </button>
          <button
            type="button"
            onClick={() => setGameweek((g) => Math.min(38, g + 1))}
            disabled={gameweek >= 38}
            aria-label="Next gameweek"
          >
            ›
          </button>
        </span>
      </div>

      {isLoading ? (
        <TableSkeleton rows={5} />
      ) : !data || data.fixtures.length === 0 ? (
        <Empty title="No matches to show">
          <p>{data?.empty_message ?? 'Fixtures appear once the schedule has loaded.'}</p>
        </Empty>
      ) : (
        <>
          {[...groups.entries()].map(([key, matches]) => {
            const { day, date } = dayLabel(key)
            return (
              <div key={key}>
                <div className="day-head">
                  <span className="day-head__day">{day}</span>
                  <span className="day-head__date">{date}</span>
                  <span className="day-head__count">
                    {matches.length} {matches.length === 1 ? 'match' : 'matches'}
                  </span>
                </div>
                {matches.map((fixture) => (
                  <Match
                    key={fixture.id}
                    fixture={fixture}
                    me={me?.person.key}
                    picks={picksByFixture.get(fixture.id)}
                  />
                ))}
              </div>
            )
          })}
          <p className="tnote">
            Times are yours. Tap <b style={{ color: 'var(--ink)' }}>Where</b> for all four
            cities and their broadcasters, verified{' '}
            {data.fixtures[0]?.local_times[0]?.verified_on ?? 'recently'}.
          </p>
          <StaleNote freshness={data.freshness} label="Fixtures" />
        </>
      )}
    </>
  )

  if (embedded) return body

  return (
    <section className="section">
      <div className="wrap">{body}</div>
    </section>
  )
}
