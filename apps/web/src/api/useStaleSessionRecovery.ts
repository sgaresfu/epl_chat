/**
 * Recover from a session that no longer works.
 *
 * Cookies set by a previous deployment can stop being sent — a change of
 * origin or of SameSite is enough — and the next mutation then fails CSRF. The
 * user sees "CSRF token missing or invalid", which tells them nothing and
 * leaves them stuck on a page that looks signed in.
 *
 * Any query or mutation that reports `needsSignIn` clears the cached identity,
 * which drops the app back to the login screen with an explanation.
 */

import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from './client'
import { keys } from './queries'

export function useStaleSessionRecovery(): void {
  const client = useQueryClient()

  useEffect(() => {
    const cache = client.getQueryCache()
    const mutations = client.getMutationCache()

    function handle(error: unknown): void {
      if (error instanceof ApiError && error.needsSignIn) {
        // Drop the stale cookies so the next sign-in starts clean.
        document.cookie = 'pl_csrf=; Max-Age=0; path=/'
        client.setQueryData(keys.me, null)
        void client.invalidateQueries({ queryKey: keys.me })
      }
    }

    const unsubQueries = cache.subscribe((event) => {
      if (event.type === 'updated' && event.query.state.error) {
        handle(event.query.state.error)
      }
    })
    const unsubMutations = mutations.subscribe((event) => {
      if (event.type === 'updated' && event.mutation?.state.error) {
        handle(event.mutation.state.error)
      }
    })

    return () => {
      unsubQueries()
      unsubMutations()
    }
  }, [client])
}
