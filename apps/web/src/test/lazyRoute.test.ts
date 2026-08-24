/**
 * A deploy that lands mid-session retires the chunk names the open page is
 * holding, so the next unvisited route 404s. One reload fixes it; looping
 * forever on a failure that is *not* a stale chunk would be worse than the
 * bug being fixed, so recovery is deliberately once per session.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadWithRecovery } from '@/lib/lazyRoute'

const reload = vi.fn()
const stale = () => Promise.reject(new Error('error loading dynamically imported module'))

/** Resolves to true only if the promise is still pending — i.e. the page is
 *  being replaced rather than rendered into. */
async function pending(p: Promise<unknown>): Promise<boolean> {
  const marker = Symbol('pending')
  return (await Promise.race([p.catch(() => marker), Promise.resolve(marker)])) === marker
}

beforeEach(() => {
  sessionStorage.clear()
  reload.mockClear()
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, reload },
  })
})

describe('loadWithRecovery', () => {
  it('passes a working chunk straight through', async () => {
    const mod = { default: 'x' }
    await expect(loadWithRecovery(async () => mod)).resolves.toBe(mod)
    expect(reload).not.toHaveBeenCalled()
  })

  it('reloads when a chunk has been retired by a deploy', async () => {
    const p = loadWithRecovery(stale)
    expect(await pending(p)).toBe(true)
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('gives up after one attempt rather than refreshing forever', async () => {
    await pending(loadWithRecovery(stale))
    expect(reload).toHaveBeenCalledTimes(1)

    // Same session, still failing: the error must surface instead of looping.
    await expect(loadWithRecovery(stale)).rejects.toThrow('dynamically imported module')
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('re-arms once a chunk loads, so a later deploy is also survivable', async () => {
    sessionStorage.setItem('chunk-reloaded', '1')
    await loadWithRecovery(async () => 'ok')
    expect(sessionStorage.getItem('chunk-reloaded')).toBeNull()

    // And the next stale chunk is recovered rather than thrown at the user.
    expect(await pending(loadWithRecovery(stale))).toBe(true)
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('does not reload when storage cannot remember that it did', async () => {
    const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })
    await expect(loadWithRecovery(stale)).rejects.toThrow()
    expect(reload).not.toHaveBeenCalled()
    get.mockRestore()
  })
})
