/**
 * Whether the app can actually reach the server.
 *
 * `navigator.onLine` only reports whether a network interface exists — a phone
 * on hotel wifi with no route out still says true, and a page restored from the
 * service worker cache can say true with nothing behind it. So it is used as a
 * hint, and the real signal is whether requests are succeeding.
 *
 * The service worker will happily serve the last known table offline, which is
 * the right behaviour. Showing it without a word would imply it is live.
 */

import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, isServedFromCache, onCacheStateChange } from '@/api/client'

/** ApiError uses status 0 for "the request never reached anybody". */
const NETWORK_FAILURE = 0

export function useOnline(): boolean {
  const client = useQueryClient()
  const [reachable, setReachable] = useState(() => !isServedFromCache())

  useEffect(() => {
    const up = () => setReachable(true)
    const down = () => setReachable(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    if (typeof navigator !== 'undefined' && !navigator.onLine) setReachable(false)

    // A query that fails to reach the server at all is the honest signal; one
    // that succeeds proves we are back.
    const unsubscribe = client.getQueryCache().subscribe((event) => {
      if (event.type !== 'updated') return
      const { status, error } = event.query.state
      if (error instanceof ApiError && error.status === NETWORK_FAILURE) setReachable(false)
      // A cached reply is a *successful* reply, so success alone proves
      // nothing; the worker's stamp is what separates live from replayed.
      else if (status === 'success' && !isServedFromCache()) setReachable(true)
    })

    const unwatchCache = onCacheStateChange((cached) => setReachable(!cached))

    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
      unsubscribe()
      unwatchCache()
    }
  }, [client])

  return reachable
}
