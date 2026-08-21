import { useState } from 'react'
import { useFixtures, useMe } from '@/api/queries'
import { Crest } from '@/components/Crest'
import { FourCities } from '@/components/FourCities'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'
import type { Fixture } from '@/api/types'

function myKickoff(fixture: Fixture, me: string | undefined): string {
  const mine = fixture.local_times.find((t) => t.place === me) ?? fixture.local_times[0]
  if (!mine) return 'Time to be confirmed'
  return `${mine.weekday} ${mine.time} · your time`
}

function Row({ fixture, me }: { fixture: Fixture; me: string | undefined }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="fxr">
      <div className="fxr__head">
        <span className="side">
          <Crest club={fixture.home} size={34} />
          {fixture.home.name}
        </span>
        <span className="tie__v">
          {fixture.finished || fixture.started
            ? `${fixture.home_score ?? 0}–${fixture.away_score ?? 0}`
            : 'vs'}
        </span>
        <span className="side">
          {fixture.away.name}
          <Crest club={fixture.away} size={34} />
        </span>
        {fixture.derby && <span className="fxr__badge">{fixture.derby}</span>}
        {fixture.postponed && <span className="fxr__badge">Postponed</span>}
        <span className="fxr__ko">{myKickoff(fixture, me)}</span>
      </div>

      {fixture.odds?.available ? (
        <div className="odds">
          <b>
            {fixture.odds.home ?? '—'}
            <span>{fixture.home.name}</span>
          </b>
          <b>
            {fixture.odds.draw ?? '—'}
            <span>Draw</span>
          </b>
          <b>
            {fixture.odds.away ?? '—'}
            <span>{fixture.away.name}</span>
          </b>
        </div>
      ) : null}

      <div className="acts">
        <button
          className="chip"
          type="button"
          aria-pressed={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? 'Hide kick-off times' : 'Where to watch'}
        </button>
        <button className="chip" type="button" disabled={!fixture.watch_open}>
          {fixture.watch_open ? 'Mark as watched' : 'Opens at kick-off'}
        </button>
      </div>

      {open && <FourCities times={fixture.local_times} me={me} />}
    </div>
  )
}

export function Fixtures() {
  const [gameweek, setGameweek] = useState(1)
  const { data, isLoading } = useFixtures(gameweek)
  const { data: me } = useMe()

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Matches</h2>
          <span className="seg" role="group" aria-label="Gameweek">
            <button type="button" onClick={() => setGameweek((g) => Math.max(1, g - 1))}>
              ‹
            </button>
            <button type="button" aria-selected="true" role="tab">
              Gameweek {gameweek}
            </button>
            <button type="button" onClick={() => setGameweek((g) => Math.min(38, g + 1))}>
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
            <div className="fx">
              {data.fixtures.map((fixture) => (
                <Row key={fixture.id} fixture={fixture} me={me?.person.key} />
              ))}
            </div>
            <p className="tnote">
              Every kick-off is shown in all four cities with its broadcaster. Listings verified{' '}
              {data.fixtures[0]?.local_times[0]?.verified_on ?? 'recently'}.
            </p>
            <StaleNote freshness={data.freshness} label="Fixtures" />
          </>
        )}
      </div>
    </section>
  )
}
