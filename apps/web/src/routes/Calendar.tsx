/**
 * Other sport: F1 weekends, boxing and UFC cards, big finals -- next 30 days,
 * each in all four cities' own local time. A maintained file, not a live feed,
 * so there is no freshness note here the way there is on the football pages.
 */

import { useMemo, useState } from 'react'
import { useCalendar, useMe } from '@/api/queries'
import { Empty, TableSkeleton } from '@/components/states'
import type { CalendarEvent } from '@/api/types'

const LABELS: Record<CalendarEvent['category'], string> = {
  f1: 'F1',
  boxing: 'Boxing',
  ufc: 'UFC',
  other: 'Other',
}

function EventTimes({ event, me }: { event: CalendarEvent; me: string | undefined }) {
  return (
    <div className="tv" style={{ marginTop: 18 }}>
      {event.local_times.map((slot) => (
        <div className="tv__cell" key={slot.place} data-mine={slot.place === me}>
          <b className="tv__time">
            {slot.time}
            {slot.day_shift !== 0 && (
              <span className="tv__day">{slot.day_shift > 0 ? '+1' : '−1'}</span>
            )}
          </b>
          <span className="tv__city">
            {slot.weekday} · {slot.city}
            {slot.place === me ? ' · you' : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

function Event({ event, me }: { event: CalendarEvent; me: string | undefined }) {
  return (
    <div className="calendar-event">
      <div className="calendar-event__head">
        <span className="calendar-event__badge">{LABELS[event.category]}</span>
        <h3>{event.title}</h3>
      </div>
      <EventTimes event={event} me={me} />
      {event.note && <p className="tnote">{event.note}</p>}
    </div>
  )
}

export function Calendar() {
  const { data, isLoading } = useCalendar()
  const { data: me } = useMe()
  const [category, setCategory] = useState<'all' | CalendarEvent['category']>('all')

  const categories = useMemo(() => {
    const seen = new Set((data?.events ?? []).map((e) => e.category))
    return ['all', ...Array.from(seen)] as const
  }, [data])

  const shown = useMemo(() => {
    const events = data?.events ?? []
    return category === 'all' ? events : events.filter((e) => e.category === category)
  }, [data, category])

  if (isLoading) return <TableSkeleton rows={6} />

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Calendar</h2>
          <span className="shead__link" style={{ color: 'var(--ink-3)' }}>
            F1 · Boxing · UFC · finals
          </span>
        </div>

        {categories.length > 2 && (
          <div className="source-filter">
            {categories.map((c) => (
              <button
                key={c}
                type="button"
                className="chip"
                aria-pressed={category === c}
                onClick={() => setCategory(c)}
              >
                {c === 'all' ? 'All' : LABELS[c]}
              </button>
            ))}
          </div>
        )}

        {shown.length === 0 ? (
          <Empty title="Nothing on right now">
            <p>{data?.empty_message ?? 'Nothing else on in the next 30 days.'}</p>
          </Empty>
        ) : (
          <div className="calendar-list">
            {shown.map((event) => (
              <Event key={`${event.title}-${event.starts_at}`} event={event} me={me?.person.key} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
