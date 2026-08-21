/**
 * The SSE connection.
 *
 * An incoming event invalidates the cached query it affects rather than
 * triggering a blind refetch of everything, so scores change under the user's
 * eye with no spinner and no full reload.
 *
 * If the stream drops, the hook falls back to polling and reports
 * `connecting`, because silently going stale is the failure this exists to
 * avoid. `EventSource` reconnects on its own, so the fallback is a safety net
 * for the case where it cannot.
 */

import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { API_BASE } from './client'
import { keys } from './queries'

export type StreamState = 'live' | 'connecting' | 'offline'

/** How long without any message before we assume the stream is dead. */
const SILENCE_LIMIT_MS = 45_000
const POLL_INTERVAL_MS = 60_000

export function useLiveStream(enabled: boolean): StreamState {
  const client = useQueryClient()
  const [state, setState] = useState<StreamState>('connecting')
  const lastMessage = useRef<number>(Date.now())

  useEffect(() => {
    if (!enabled) return

    // withCredentials is what sends the session cookie; without it the server
    // sees an anonymous request and returns 401.
    const source = new EventSource(`${API_BASE}/api/stream`, { withCredentials: true })

    const touch = () => {
      lastMessage.current = Date.now()
      setState('live')
    }

    source.addEventListener('hello', touch)

    source.addEventListener('scores', () => {
      touch()
      void client.invalidateQueries({ queryKey: keys.table })
      void client.invalidateQueries({ queryKey: ['fixtures'] })
      void client.invalidateQueries({ queryKey: keys.home })
    })

    source.addEventListener('fpl', () => {
      touch()
      void client.invalidateQueries({ queryKey: ['fpl'] })
    })

    source.addEventListener('odds', () => {
      touch()
      void client.invalidateQueries({ queryKey: ['fixtures'] })
    })

    source.onopen = () => setState('live')
    source.onerror = () => setState('connecting')

    // Watchdog: EventSource can sit in a half-open state where onerror never
    // fires. The server sends a comment heartbeat every 20s, so silence for
    // more than twice that means the connection is gone whatever it claims.
    const watchdog = window.setInterval(() => {
      if (Date.now() - lastMessage.current > SILENCE_LIMIT_MS) {
        setState((current) => (current === 'live' ? 'connecting' : current))
      }
    }, 10_000)

    return () => {
      window.clearInterval(watchdog)
      source.close()
    }
  }, [enabled, client])

  // Polling fallback while the stream is not live, so data never silently ages.
  useEffect(() => {
    if (!enabled || state === 'live') return
    const timer = window.setInterval(() => {
      void client.invalidateQueries({ queryKey: keys.table })
      void client.invalidateQueries({ queryKey: keys.home })
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [enabled, state, client])

  return state
}
