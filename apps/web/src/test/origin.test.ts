/**
 * A build served from the wrong origin must forward, not strand the user.
 *
 * The api serves this app itself, so they are same-origin and the cookie is
 * first-party. An older static site on its own hostname talks to the api
 * cross-origin, which makes the cookie third-party — and every browser on iOS
 * is WebKit, so Safari drops it. Login then fails in the worst possible way:
 * the request succeeds, the cookie is silently discarded, and the next call is
 * anonymous again with nothing to show the user.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('redirectToCanonicalOrigin', () => {
  const replace = vi.fn()

  beforeEach(() => {
    vi.resetModules()
    replace.mockClear()
  })

  async function load(apiBase: string, origin: string, path = '/', search = '') {
    vi.stubEnv('VITE_API_BASE', apiBase)
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { origin, pathname: path, search, replace },
    })
    return await import('@/api/client')
  }

  it('does nothing when already on the api origin', async () => {
    const { redirectToCanonicalOrigin } = await load(
      'https://league-api.onrender.com',
      'https://league-api.onrender.com',
    )
    expect(redirectToCanonicalOrigin()).toBe(false)
    expect(replace).not.toHaveBeenCalled()
  })

  it('forwards from a stale static-site origin', async () => {
    const { redirectToCanonicalOrigin } = await load(
      'https://league-api.onrender.com',
      'https://league-web.onrender.com',
    )
    expect(redirectToCanonicalOrigin()).toBe(true)
    expect(replace).toHaveBeenCalledWith('https://league-api.onrender.com/')
  })

  it('keeps the path and query when forwarding', async () => {
    const { redirectToCanonicalOrigin } = await load(
      'https://league-api.onrender.com',
      'https://league-web.onrender.com',
      '/table',
      '?view=matches',
    )
    redirectToCanonicalOrigin()
    expect(replace).toHaveBeenCalledWith('https://league-api.onrender.com/table?view=matches')
  })

  it('does nothing in development, where the base is empty', async () => {
    const { redirectToCanonicalOrigin } = await load('', 'http://localhost:5173')
    expect(redirectToCanonicalOrigin()).toBe(false)
    expect(replace).not.toHaveBeenCalled()
  })
})
