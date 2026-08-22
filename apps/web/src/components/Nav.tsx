/**
 * Navigation, in two shapes.
 *
 * On a desktop the eleven destinations fit in one sticky translucent bar, as
 * the brief specifies. On a phone they do not — they measured 1009px inside a
 * 390px viewport, a horizontal scroller with no edge, no affordance and no
 * hint that seven of the eleven existed at all.
 *
 * So the phone gets what a phone expects: five destinations in a bottom tab
 * bar within thumb reach, and the rest behind More. That is the pattern the
 * NFL and Premier League apps use, and three of these four watch on a phone.
 *
 * The primary five are the ones with a reason to be opened mid-match. Stats,
 * News, Calendar, Archive and the group page are all read at leisure, so they
 * sit in the sheet without loss.
 */

import { useEffect, useRef, useState } from 'react'
import { NavLink } from 'react-router-dom'
import type { StreamState } from '@/api/useLiveStream'
import type { Me } from '@/api/types'
import { useOnline } from '@/lib/useOnline'
import { ThemeToggle } from '@/components/ThemeToggle'

type Link = readonly [to: string, label: string, short?: string]

const PRIMARY: readonly Link[] = [
  ['/', 'Home'],
  ['/table', 'Table & matches', 'Table'],
  ['/predictions', 'Predictions', 'Picks'],
  ['/fpl', 'Fantasy'],
  ['/watch', 'Watch log', 'Watched'],
] as const

const SECONDARY: readonly Link[] = [
  ['/stats', 'Stats'],
  ['/news', 'News'],
  ['/calendar', 'Calendar'],
  ['/chat', 'The group'],
  ['/archive', 'Archive'],
] as const

const ALL = [...PRIMARY, ...SECONDARY]

const STREAM_LABEL: Record<StreamState, string> = {
  live: 'Live updates connected',
  connecting: 'Reconnecting to live updates',
  offline: 'Live updates offline',
}

function LiveDot({ stream }: { stream: StreamState }) {
  const online = useOnline()
  if (!online) {
    // The service worker is serving the last known data; saying so beats
    // letting it look live.
    return (
      <span className="offline-tag" role="status">
        Offline
      </span>
    )
  }
  return <span className="pulse" data-state={stream} role="status" aria-label={STREAM_LABEL[stream]} />
}

/** Bottom-sheet overflow. Dismisses on Escape, on backdrop, and on navigation. */
function MoreSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    // Focus moves into the sheet so a keyboard or screen-reader user is not
    // left behind on the button that opened it.
    panel.current?.querySelector<HTMLElement>('a')?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label="More pages">
      <button className="sheet__scrim" type="button" aria-label="Close" onClick={onClose} />
      <div className="sheet__panel" ref={panel}>
        <span className="sheet__grip" aria-hidden="true" />
        <div className="sheet__links">
          {SECONDARY.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              onClick={onClose}
              className={({ isActive }) => (isActive ? 'sheet__link on' : 'sheet__link')}
            >
              {label}
            </NavLink>
          ))}
        </div>
        <div className="sheet__foot">
          <ThemeToggle />
        </div>
      </div>
    </div>
  )
}

export function Nav({ me, stream }: { me: Me | undefined; stream: StreamState }) {
  const [more, setMore] = useState(false)

  return (
    <>
      <nav className="nav" aria-label="Primary">
        <div className="wrap">
          <span className="nav__mark">Prediction League</span>
          <div className="nav__links">
            {ALL.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => (isActive ? 'on' : undefined)}
                end={to === '/'}
              >
                {label}
              </NavLink>
            ))}
          </div>
          <span className="nav__me">
            <LiveDot stream={stream} />
            <span className="nav__who">{me ? `${me.person.name} · ${me.person.city}` : ''}</span>
            <ThemeToggle />
          </span>
        </div>
      </nav>

      {/* Phone: the same destinations, reachable by thumb. */}
      <nav className="tabbar" aria-label="Primary">
        {PRIMARY.map(([to, label, short]) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) => (isActive ? 'tabbar__item on' : 'tabbar__item')}
          >
            <TabIcon to={to} />
            <span>{short ?? label}</span>
          </NavLink>
        ))}
        <button
          className={more ? 'tabbar__item on' : 'tabbar__item'}
          type="button"
          aria-expanded={more}
          aria-haspopup="dialog"
          onClick={() => setMore((v) => !v)}
        >
          <TabIcon to="more" />
          <span>More</span>
        </button>
      </nav>

      <MoreSheet open={more} onClose={() => setMore(false)} />
    </>
  )
}

/**
 * Line icons, drawn rather than imported.
 *
 * A tab bar needs icons — five words alone give no shape to aim at, and the
 * brief forbids emoji as iconography. These are the smallest honest set:
 * 1.6px strokes on a 24 grid, `currentColor` so the active state needs no
 * second copy.
 */
function TabIcon({ to }: { to: string }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.6,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }
  switch (to) {
    case '/':
      return (
        <svg {...common}>
          <path d="M3 10.5 12 3l9 7.5" />
          <path d="M5.5 9.5V20h13V9.5" />
        </svg>
      )
    case '/table':
      return (
        <svg {...common}>
          <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
          <path d="M3 9.5h18M3 14.5h18M9 9.5V19.5" />
        </svg>
      )
    case '/predictions':
      return (
        <svg {...common}>
          <path d="M5 4.5h14v15l-7-4-7 4z" />
        </svg>
      )
    case '/fpl':
      return (
        <svg {...common}>
          <path d="M12 3.5 14.6 9l6 .9-4.3 4.2 1 6-5.3-2.8L6.7 20l1-6L3.4 9.9 9.4 9z" />
        </svg>
      )
    case '/watch':
      return (
        <svg {...common}>
          <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      )
    default:
      return (
        <svg {...common}>
          <circle cx="5.5" cy="12" r="1.4" fill="currentColor" stroke="none" />
          <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
          <circle cx="18.5" cy="12" r="1.4" fill="currentColor" stroke="none" />
        </svg>
      )
  }
}
