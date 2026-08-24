/**
 * Run the service worker for real, in a fake global scope.
 *
 * The policy tests next door read the source, which is right for "is the
 * document in the wrong list". It is not enough for the activate handler,
 * where the bug that actually happened was a *deadlock*: awaiting
 * `client.navigate()` inside `waitUntil` makes the worker wait on a request
 * only it can answer, and it cannot answer anything until activation
 * finishes. The page hangs with nothing on it. No amount of reading the
 * source catches that reliably -- but running it does, because the promise
 * simply never settles.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

const SOURCE = readFileSync(join(__dirname, '../../public/sw.js'), 'utf8')

interface Harness {
  fire: (type: string) => Promise<void>
  navigated: string[]
  deleted: string[]
  claimed: () => boolean
}

/** Boot sw.js against a fake ServiceWorkerGlobalScope. */
function boot(existingCaches: string[], openWindows: string[]): Harness {
  const listeners = new Map<string, (event: unknown) => void>()
  const deleted: string[] = []
  const navigated: string[] = []
  let claimed = false

  const store = new Set(existingCaches)
  const cacheApi = {
    keys: async () => [...store],
    delete: async (k: string) => {
      deleted.push(k)
      return store.delete(k)
    },
    open: async () => ({ addAll: async () => {}, add: async () => {}, put: async () => {} }),
    match: async () => undefined,
  }

  // A navigation cannot complete until the worker is activated: the request it
  // makes is one only this worker can answer, and it answers nothing until
  // activation is done. Modelling that is the whole point -- a worker that
  // awaits its own navigations is then waiting on itself, exactly as it does
  // in a browser, and the test hangs instead of quietly passing.
  let releaseNavigations = (): void => {}
  const activated = new Promise<void>((resolve) => (releaseNavigations = resolve))

  const clients = openWindows.map((url) => ({
    url,
    navigate: vi.fn(async (to: string) => {
      navigated.push(to)
      await activated
      return null
    }),
  }))

  const self = {
    addEventListener: (type: string, fn: (event: unknown) => void) => listeners.set(type, fn),
    skipWaiting: async () => {},
    registration: { active: existingCaches.length > 0 ? {} : null },
    location: { origin: 'https://example.test' },
    clients: {
      claim: async () => {
        claimed = true
      },
      matchAll: async () => clients,
    },
  }

  // eslint-disable-next-line no-new-func
  new Function('self', 'caches', 'fetch', 'Response', 'Headers', 'URL', SOURCE)(
    self,
    cacheApi,
    async () => new Response(''),
    Response,
    Headers,
    URL,
  )

  return {
    fire: async (type: string) => {
      const fn = listeners.get(type)
      if (!fn) throw new Error(`no ${type} listener registered`)
      let held: Promise<unknown> = Promise.resolve()
      fn({ waitUntil: (p: Promise<unknown>) => (held = p) })
      void held.then(releaseNavigations, releaseNavigations)
      await held
    },
    navigated,
    deleted,
    claimed: () => claimed,
  }
}

/** Rejects rather than hanging forever, so a deadlock fails the test. */
function within<T>(p: Promise<T>, ms = 2000): Promise<T> {
  return Promise.race([
    p,
    new Promise<T>((_, reject) =>
      setTimeout(() => reject(new Error('activate never settled — deadlocked')), ms),
    ),
  ])
}

describe('service worker activation', () => {
  it('completes activation instead of deadlocking on its own navigations', async () => {
    const h = boot(['shell-v4'], ['https://example.test/table'])
    await expect(within(h.fire('activate'))).resolves.toBeUndefined()
  })

  it('reloads pages left on the previous build', async () => {
    const h = boot(['shell-v4'], ['https://example.test/table', 'https://example.test/fpl'])
    await within(h.fire('activate'))
    // navigate() is fired without being awaited, so let the microtasks drain.
    await new Promise((r) => setTimeout(r, 10))
    expect(h.navigated).toEqual(['https://example.test/table', 'https://example.test/fpl'])
    expect(h.claimed()).toBe(true)
  })

  it('leaves a first-time visitor alone', async () => {
    const h = boot([], ['https://example.test/'])
    await within(h.fire('activate'))
    await new Promise((r) => setTimeout(r, 10))
    expect(h.navigated).toEqual([])
    expect(h.claimed()).toBe(true)
  })

  it('purges caches from older versions and keeps its own', async () => {
    const h = boot(['shell-v3', 'data-v3', 'shell-v4'], [])
    await within(h.fire('activate'))
    expect(h.deleted).toEqual(expect.arrayContaining(['shell-v3', 'data-v3', 'shell-v4']))
    const version = /const VERSION = '(v\d+)'/.exec(SOURCE)?.[1]
    expect(h.deleted.some((k) => k.endsWith(String(version)))).toBe(false)
  })
})
