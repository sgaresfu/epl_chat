/**
 * Lazy-load a route, and survive a deploy that happened mid-session.
 *
 * Route chunks are content-hashed, so a deploy gives them new filenames and
 * retires the old ones. Anybody with the app already open is holding a
 * document that names the *previous* build's chunks — so the moment they tap
 * a nav link they have not visited yet, the import 404s and the route dies. A
 * blank panel, for a user who did nothing wrong, on a build that is perfectly
 * healthy. It showed up in the QA sweep as a page error on a route that had
 * loaded fine minutes earlier.
 *
 * A reload fixes it completely, because the document is fetched network-first
 * and comes back naming chunks that exist. The care needed is in not
 * reloading forever when the failure is not a stale chunk at all — a real
 * outage, or a genuinely broken build. So recovery is attempted once per
 * session, and after that the error surfaces honestly.
 */

import { lazy } from 'react'
import type { ComponentType } from 'react'

const FLAG = 'chunk-reloaded'

function attempted(): boolean {
  try {
    return sessionStorage.getItem(FLAG) === '1'
  } catch {
    // Private mode, or storage disabled. Treat as "already tried": a page
    // that cannot remember reloading is exactly the page that must not start.
    return true
  }
}

function remember(value: '1' | null): void {
  try {
    if (value === null) sessionStorage.removeItem(FLAG)
    else sessionStorage.setItem(FLAG, value)
  } catch {
    /* nothing to do; `attempted()` already fails closed */
  }
}

/**
 * The recovery itself, kept separate from `lazy()` so it can be tested as
 * what it is — a promise that either resolves, reloads, or rethrows — without
 * reaching into React's internals to trigger it.
 */
export async function loadWithRecovery<T>(load: () => Promise<T>): Promise<T> {
  try {
    const loaded = await load()
    // Something loaded, so whatever went wrong is over. Clear the flag, or a
    // session gets one recovery and never another.
    remember(null)
    return loaded
  } catch (error) {
    if (attempted()) throw error
    remember('1')
    window.location.reload()
    // The page is being replaced. Resolving here would render a route into a
    // document already on its way out.
    return new Promise<T>(() => {})
  }
}

export function lazyRoute<T extends ComponentType<Record<string, never>>>(
  load: () => Promise<{ default: T }>,
) {
  return lazy(() => loadWithRecovery(load))
}
