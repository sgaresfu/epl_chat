/**
 * One kickoff, four cities, each with its own broadcaster.
 *
 * The logged-in person's city is highlighted. Times come from the server,
 * already converted through each person's IANA zone -- the browser never does
 * the arithmetic, so a viewer in a fifth timezone still sees the right answer
 * for all four.
 */

import type { LocalTime } from '@/api/types'

interface Props {
  times: LocalTime[]
  me: string | undefined
}

export function FourCities({ times, me }: Props) {
  if (times.length === 0) return null

  return (
    <div className="tv">
      {times.map((slot) => (
        <div className="tv__cell" key={slot.place} data-mine={slot.place === me}>
          <b className="tv__time">
            {slot.time}
            {slot.day_shift !== 0 && (
              <span className="tv__day">{slot.day_shift > 0 ? '+1' : '−1'}</span>
            )}
          </b>
          <span className="tv__city">
            {slot.city}
            {slot.place === me ? ' · you' : ''}
          </span>
          <em className="tv__where">
            {slot.broadcaster_url ? (
              <a href={slot.broadcaster_url} target="_blank" rel="noreferrer noopener">
                {slot.broadcaster}
              </a>
            ) : (
              (slot.broadcaster ?? 'Listing to confirm')
            )}
          </em>
        </div>
      ))}
    </div>
  )
}
