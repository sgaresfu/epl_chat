/**
 * Everything worth clearing an evening for, bar football.
 *
 * Structured the way a sports calendar is actually read: what is on next,
 * then the months ahead. A date tile carries the when, so the eye scans one
 * column rather than parsing prose. Where-to-watch sits on the row itself —
 * knowing the Super Bowl is on is useless to somebody in Lviv who does not
 * know which service carries it.
 *
 * Two honesty rules the data model enforces and this renders:
 * a four-day major has no single kickoff, so it shows a date range instead of
 * four invented clock times; and a broadcaster that was never confirmed is
 * marked as such rather than stated as fact.
 */

import { useEffect, useMemo, useState } from 'react'
import { useCalendar, useMe } from '@/api/queries'
import { Empty, TableSkeleton } from '@/components/states'
import type { CalendarEvent, WatchOn } from '@/api/types'

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]
const SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function monthKey(iso: string): string {
  const d = new Date(iso)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth()).padStart(2, '0')}`
}

function monthLabel(key: string): string {
  const [year, month] = key.split('-')
  return `${MONTHS[Number(month)]} ${year}`
}

/** "in 3 days" reads better than a date the reader has to subtract from today. */
function relative(event: CalendarEvent): string {
  if (event.in_progress) return 'Under way'
  if (event.days_until === 0) return 'Today'
  if (event.days_until === 1) return 'Tomorrow'
  if (event.days_until < 14) return `in ${event.days_until} days`
  if (event.days_until < 60) return `in ${Math.round(event.days_until / 7)} weeks`
  return `in ${Math.round(event.days_until / 30)} months`
}

function dateRange(event: CalendarEvent): string {
  const s = new Date(event.starts_at)
  if (!event.multi_day || !event.ends_at) return ''
  const e = new Date(event.ends_at)
  const sameMonth = s.getUTCMonth() === e.getUTCMonth()
  const left = `${s.getUTCDate()} ${sameMonth ? '' : SHORT[s.getUTCMonth()]}`.trim()
  return `${left} – ${e.getUTCDate()} ${SHORT[e.getUTCMonth()]}`
}

/** Ticks once a minute — a countdown to something days away needs no second hand. */
function useMinuteTick(active: boolean): void {
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setTick((n) => n + 1), 60_000)
    return () => window.clearInterval(timer)
  }, [active])
}

function WatchRow({ watch, me }: { watch: WatchOn[]; me: string | undefined }) {
  if (watch.length === 0) return null
  return (
    <p className="cal-watch">
      {watch.map((w) => (
        <span className="cal-watch__cell" key={w.place} data-mine={w.place === me}>
          <span className="cal-watch__city">{w.city}</span>
          {w.url ? (
            <a href={w.url} target="_blank" rel="noreferrer noopener">
              {w.provider}
            </a>
          ) : (
            <span>{w.provider}</span>
          )}
          {w.confidence !== 'verified' && (
            <abbr className="cal-watch__flag" title="Not confirmed for this season — check before you plan around it">
              ?
            </abbr>
          )}
        </span>
      ))}
    </p>
  )
}

function NextUp({ event, me }: { event: CalendarEvent; me: string | undefined }) {
  useMinuteTick(true)
  const slot = event.local_times.find((t) => t.place === me) ?? event.local_times[0]

  return (
    <div className="cal-next">
      <p className="eyebrow">
        {event.in_progress ? 'On now' : 'Next up'} · {event.sport_label}
      </p>
      <h3>{event.title}</h3>
      <p className="cal-next__when">
        {event.time_known && slot ? (
          <>
            <b>{slot.time}</b> your time · {slot.weekday} {slot.day}
          </>
        ) : (
          <b>{event.multi_day ? dateRange(event) : `${new Date(event.starts_at).getUTCDate()} ${SHORT[new Date(event.starts_at).getUTCMonth()]}`}</b>
        )}
        <span className="cal-next__rel">{relative(event)}</span>
      </p>
      {event.venue && <p className="cal-next__venue">{event.venue}</p>}
      <WatchRow watch={event.watch} me={me} />
    </div>
  )
}

function EventRow({ event, me }: { event: CalendarEvent; me: string | undefined }) {
  const [open, setOpen] = useState(false)
  const start = new Date(event.starts_at)
  const slot = event.local_times.find((t) => t.place === me) ?? event.local_times[0]

  return (
    <div className="cal-row" data-tier={event.tier} data-live={event.in_progress}>
      <div className="cal-row__date" aria-hidden="true">
        <b>{start.getUTCDate()}</b>
        <span>{SHORT[start.getUTCMonth()]}</span>
      </div>

      <div className="cal-row__body">
        <p className="cal-row__head">
          <span className="cal-row__sport">{event.sport_label}</span>
          {event.in_progress && <span className="cal-row__live">Under way</span>}
          <span className="cal-row__title">{event.title}</span>
        </p>
        <p className="cal-row__meta">
          {event.multi_day ? (
            <span>{dateRange(event)}</span>
          ) : event.time_known && slot ? (
            <span>
              {slot.time} your time
              {slot.day_shift !== 0 && <span className="tv__day">{slot.day_shift > 0 ? '+1' : '−1'}</span>}
            </span>
          ) : (
            <span>Time to be confirmed</span>
          )}
          {event.venue && <span>{event.venue}</span>}
          <span className="cal-row__rel">{relative(event)}</span>
        </p>
        <WatchRow watch={event.watch} me={me} />
        {open && (
          <>
            {event.local_times.length > 0 && (
              <div className="tv" style={{ marginTop: 14 }}>
                {event.local_times.map((t) => (
                  <div className="tv__cell" key={t.place} data-mine={t.place === me}>
                    <b className="tv__time">
                      {t.time}
                      {t.day_shift !== 0 && (
                        <span className="tv__day">{t.day_shift > 0 ? '+1' : '−1'}</span>
                      )}
                    </b>
                    <span className="tv__city">
                      {t.weekday} · {t.city}
                      {t.place === me ? ' · you' : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {event.note && <p className="tnote">{event.note}</p>}
          </>
        )}
      </div>

      {(event.local_times.length > 0 || event.note) && (
        <button
          className="chip cal-row__more"
          type="button"
          aria-expanded={open}
          aria-label={open ? `Hide detail for ${event.title}` : `Show detail for ${event.title}`}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? 'Less' : 'More'}
        </button>
      )}
    </div>
  )
}

export function Calendar() {
  const { data, isLoading } = useCalendar()
  const { data: me } = useMe()
  const [sport, setSport] = useState<string>('all')

  const events = data?.events ?? []

  const counts = useMemo(() => {
    const map = new Map<string, number>()
    for (const e of events) map.set(e.sport, (map.get(e.sport) ?? 0) + 1)
    return map
  }, [events])

  const labels = useMemo(() => {
    const map = new Map<string, string>()
    for (const e of events) map.set(e.sport, e.sport_label)
    return map
  }, [events])

  const shown = sport === 'all' ? events : events.filter((e) => e.sport === sport)

  const months = useMemo(() => {
    const groups = new Map<string, CalendarEvent[]>()
    for (const e of shown) {
      const k = monthKey(e.starts_at)
      groups.set(k, [...(groups.get(k) ?? []), e])
    }
    return [...groups.entries()]
  }, [shown])

  if (isLoading) return <TableSkeleton rows={8} />

  const lead = shown[0]

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Calendar</h2>
          <span className="shead__link" style={{ color: 'var(--ink-3)' }}>
            {events.length} events · everything but football
          </span>
        </div>

        {lead && <NextUp event={lead} me={me?.person.key} />}

        <div className="source-filter stagger" style={{ marginTop: 28 }}>
          <button
            type="button"
            className="chip"
            aria-pressed={sport === 'all'}
            onClick={() => setSport('all')}
          >
            All <i>{events.length}</i>
          </button>
          {[...counts.entries()]
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
            .map(([key, n]) => (
              <button
                key={key}
                type="button"
                className="chip"
                aria-pressed={sport === key}
                onClick={() => setSport(key)}
              >
                {labels.get(key)} <i>{n}</i>
              </button>
            ))}
        </div>

        {shown.length === 0 ? (
          <Empty title="Nothing on">
            <p>{data?.empty_message ?? 'Nothing scheduled in this window.'}</p>
          </Empty>
        ) : (
          months.map(([key, list]) => (
            <div key={key}>
              <div className="day-head" style={{ marginTop: 34 }}>
                <span className="day-head__day">{monthLabel(key)}</span>
                <span className="day-head__count">
                  {list.length} {list.length === 1 ? 'event' : 'events'}
                </span>
              </div>
              {list.map((e) => (
                <EventRow key={`${e.title}-${e.starts_at}`} event={e} me={me?.person.key} />
              ))}
            </div>
          ))
        )}

        {data?.checked_on && (
          <p className="tnote" style={{ marginTop: 30 }}>
            Dates checked against each governing body&rsquo;s own calendar on {data.checked_on}. A{' '}
            <abbr title="Not confirmed for this season">?</abbr> against a broadcaster means the
            listing was not confirmed for this season.
          </p>
        )}
      </div>
    </section>
  )
}
