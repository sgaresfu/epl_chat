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
import { keys, useFixtures, useLineups, useMe } from '@/api/queries'
import { Crest } from '@/components/Crest'
import { FourCities } from '@/components/FourCities'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'
import type { Fixture, LineupSide } from '@/api/types'

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

/** bet365 1X2, with a week's drift when there's history to show it. Nothing
 * renders when there's no price -- a missing key or an unlisted match reads
 * as an ordinary match row, not an error. */
function OddsLine({ fixture }: { fixture: Fixture }) {
  const odds = fixture.odds
  if (!odds || !odds.available) return null

  const outcomes: [string, number | undefined, number | null][] = [
    [fixture.home.short_name, odds.drift?.home, odds.home],
    ['Draw', odds.drift?.draw, odds.draw],
    [fixture.away.short_name, odds.drift?.away, odds.away],
  ]

  return (
    <p className="match-odds">
      <span className="match-odds__book">{odds.bookmaker}</span>
      {outcomes.map(([label, from, to]) => (
        <span className="match-odds__price" key={label}>
          {label}{' '}
          {from !== undefined && to !== null && from !== to
            ? `${from.toFixed(2)} → ${to.toFixed(2)}`
            : (to?.toFixed(2) ?? '—')}
        </span>
      ))}
    </p>
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
  if (isLoading) return <p className="tnote">Checking for confirmed line-ups…</p>
  if (!data?.available || !data.home || !data.away) {
    return <p className="tnote">{data?.reason ?? 'Line-ups are not available for this match.'}</p>
  }
  return (
    <div className="lineups">
      <LineupSideList label={fixture.home.name} side={data.home} />
      <LineupSideList label={fixture.away.name} side={data.away} />
    </div>
  )
}

function Match({ fixture, me }: { fixture: Fixture; me: string | undefined }) {
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
    <>
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
    </>
  )
}

export function Fixtures({ embedded = false }: { embedded?: boolean } = {}) {
  const [gameweek, setGameweek] = useState(1)
  const { data, isLoading } = useFixtures(gameweek)
  const { data: me } = useMe()

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
                  <Match key={fixture.id} fixture={fixture} me={me?.person.key} />
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
