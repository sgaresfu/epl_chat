import { NavLink } from 'react-router-dom'
import type { StreamState } from '@/api/useLiveStream'
import type { Me } from '@/api/types'
import { useOnline } from '@/lib/useOnline'

const LINKS = [
  ['/', 'Home'],
  ['/table', 'Table & matches'],
  ['/stats', 'Stats'],
  ['/predictions', 'Predictions'],
  ['/fpl', 'Fantasy'],
  ['/watch', 'Watch log'],
  ['/news', 'News'],
  ['/chat', 'The group'],
] as const

const STREAM_LABEL: Record<StreamState, string> = {
  live: 'Live updates connected',
  connecting: 'Reconnecting to live updates',
  offline: 'Live updates offline',
}

export function Nav({ me, stream }: { me: Me | undefined; stream: StreamState }) {
  const online = useOnline()
  return (
    <nav className="nav">
      <div className="wrap">
        <span className="nav__mark">Prediction League</span>
        {LINKS.map(([to, label]) => (
          <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'on' : undefined)} end={to === '/'}>
            {label}
          </NavLink>
        ))}
        <span className="nav__me">
          {/* A quiet dot rather than a banner: the brief asks for an indicator,
              not an interruption. */}
          {online ? (
            <span
              className="pulse"
              data-state={stream}
              role="status"
              aria-label={STREAM_LABEL[stream]}
            />
          ) : (
            /* Offline: the service worker is serving the last known data, and
               saying so is better than letting it look live. */
            <span className="offline-tag" role="status">
              Offline
            </span>
          )}
          {me ? `${me.person.name} · ${me.person.city}` : ''}
        </span>
      </div>
    </nav>
  )
}
