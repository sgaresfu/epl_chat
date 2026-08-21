/**
 * The season progress bar.
 *
 * Every number here is computed server-side from the fixture list and the
 * current date -- a hardcoded counter would be wrong by tomorrow and worse
 * than none at all.
 */

import type { Season } from '@/api/types'

const MONTHS = ['Jan', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

function longDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()] ?? ''} ${d.getUTCFullYear()}`
}

export function SeasonTimeline({ season }: { season: Season }) {
  return (
    <div className="season">
      <div className="season__top">
        <h2>The season</h2>
        <span className="season__range">
          {longDate(season.starts)} — {longDate(season.ends)}
        </span>
      </div>

      <div
        className="track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(season.percent)}
        aria-label={`Season progress: day ${season.day} of ${season.total_days}`}
      >
        <i style={{ width: `${Math.max(season.percent, 0.4)}%` }} />
      </div>

      <div className="ticks">
        {season.markers.map((marker) => (
          <b
            key={marker.label}
            data-now={marker.is_now}
            style={{
              left: `${marker.percent}%`,
              // Keep the first and last labels inside the panel rather than
              // letting them hang off the edge.
              transform:
                marker.percent < 6
                  ? 'translateX(0)'
                  : marker.percent > 94
                    ? 'translateX(-100%)'
                    : 'translateX(-50%)',
            }}
          >
            {marker.label}
          </b>
        ))}
      </div>

      <div className="stats">
        <div className="stats__cell">
          <b>{season.days_remaining}</b>
          <span>days until the final whistle</span>
        </div>
        <div className="stats__cell">
          <b>{season.gameweeks_played}</b>
          <span>of {season.gameweeks_total} gameweeks played</span>
        </div>
        <div className="stats__cell">
          <b>{season.matches_remaining}</b>
          <span>matches still to come</span>
        </div>
        <div className="stats__cell" data-soft={season.watched === 0}>
          <b>{season.watched}</b>
          <span>matches you&rsquo;ve watched</span>
        </div>
      </div>
    </div>
  )
}
