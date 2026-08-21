/**
 * Loading, empty and stale -- the three states every panel ships.
 *
 * A skeleton sits at the real final dimensions so arriving data never shifts
 * the layout. An empty panel says what will appear and when, because an empty
 * screen is an instruction and not an apology. A stale panel shows the last
 * good data with a quiet note about its age, never a blank box and never a
 * raw error code.
 */

import type { Freshness } from '@/api/types'

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading the table</span>
      {Array.from({ length: rows }, (_, index) => (
        <div className="skel-row" key={index}>
          <span className="skel" style={{ width: 24, height: 15 }} />
          <span className="skel" style={{ width: 32, height: 32, borderRadius: '50%' }} />
          <span className="skel" style={{ width: 140, height: 17 }} />
          <span className="skel" style={{ width: 34, height: 15, marginLeft: 'auto' }} />
        </div>
      ))}
    </div>
  )
}

export function TileSkeleton({ height = 190 }: { height?: number }) {
  return (
    <div className="tile" aria-busy="true">
      <span className="sr-only">Loading</span>
      <span className="skel" style={{ display: 'block', width: '100%', height }} />
    </div>
  )
}

export function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children}
    </div>
  )
}

/** How old is this, in words a person would actually use. */
export function describeAge(seconds: number): string {
  if (seconds < 0) return 'never updated'
  if (seconds < 60) return 'updated just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `updated ${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `updated ${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  return `updated ${days} day${days === 1 ? '' : 's'} ago`
}

export function StaleNote({ freshness, label }: { freshness: Freshness; label: string }) {
  if (!freshness.available) {
    return <p className="stale">{freshness.reason ?? `${label} has not loaded yet.`}</p>
  }
  if (!freshness.stale) return null
  return (
    <p className="stale">
      {label} {describeAge(freshness.age_seconds)}.
    </p>
  )
}

export function ErrorPanel({ title, detail }: { title: string; detail: string }) {
  return (
    <Empty title={title}>
      <p>{detail}</p>
    </Empty>
  )
}
