/**
 * The service worker must never serve the document from cache first.
 *
 * This is a regression test for a bug that made the site undeployable in
 * practice. `index.html` is the only file in the build that is not
 * content-hashed, and its whole job is to name the hashed chunks of the
 * current build. The previous worker listed `/` among its cache-first shell
 * URLs, so every returning visitor was pinned to whichever build they first
 * loaded: new deploys reached the server and never reached the browser.
 *
 * It is asserted against the source text rather than by running the worker,
 * because the failure is a *policy* mistake -- the wrong URL in the wrong
 * list -- and that is exactly what reading the source can catch.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const sw = readFileSync(join(__dirname, '../../public/sw.js'), 'utf8')

describe('service worker caching policy', () => {
  it('does not precache the document as a static asset', () => {
    const staticList = sw.match(/const STATIC_URLS = \[(.*?)\]/s)?.[1] ?? ''
    expect(staticList).not.toMatch(/['"]\/['"]/)
  })

  it('handles navigations network-first', () => {
    // The navigate branch must call fetch before it consults the cache.
    const navBranch = sw.slice(sw.indexOf("request.mode === 'navigate'"))
    const fetchAt = navBranch.indexOf('fetch(request)')
    const cacheAt = navBranch.indexOf('caches.match')
    expect(fetchAt).toBeGreaterThan(-1)
    expect(cacheAt).toBeGreaterThan(-1)
    expect(fetchAt).toBeLessThan(cacheAt)
  })

  it('treats only content-hashed paths as immutable', () => {
    const fn = sw.slice(sw.indexOf('function isImmutableAsset'))
    expect(fn).toMatch(/\/assets\//)
    // No bare document path may sneak into the immutable test.
    const body = fn.slice(0, fn.indexOf('}'))
    expect(body).not.toMatch(/===\s*['"]\/['"]/)
  })

  it('still keeps a document for offline use', () => {
    expect(sw).toMatch(/OFFLINE_DOC/)
    expect(sw).toMatch(/caches\.match\(OFFLINE_DOC\)/)
  })

  it('purges caches from older versions on activate', () => {
    const activate = sw.slice(sw.indexOf("addEventListener('activate'"))
    expect(activate).toMatch(/caches\.delete/)
    expect(activate).toMatch(/endsWith\(VERSION\)/)
  })

  it('never caches the session or the stream', () => {
    const never = sw.match(/const NEVER_CACHE = \[(.*?)\]/s)?.[1] ?? ''
    expect(never).toMatch(/session/)
    expect(never).toMatch(/stream/)
  })
})

/**
 * The other half of the same bug.
 *
 * A network-first document fixes ordinary deploys, but not a deploy that
 * changes the worker itself: that load is answered by the *old* worker, so
 * the new build only appears on the load after. Reloading once when a new
 * worker claims an already-controlled page closes that gap -- and the
 * `wasControlled` guard is what stops it firing on a first visit, where the
 * worker also claims the page and a reload would be a flash for nothing.
 */
describe('service worker registration', () => {
  const reg = readFileSync(join(__dirname, '../lib/serviceWorker.ts'), 'utf8')

  it('reloads when a new worker takes over an existing page', () => {
    expect(reg).toMatch(/addEventListener\(\s*'controllerchange'/)
    expect(reg).toMatch(/location\.reload\(\)/)
  })

  it('reads the controller before registering, not after', () => {
    const read = reg.indexOf('navigator.serviceWorker.controller)')
    const register = reg.indexOf(".register('/sw.js')")
    expect(read).toBeGreaterThan(-1)
    expect(register).toBeGreaterThan(-1)
    expect(read).toBeLessThan(register)
  })

  it('does not reload on a first visit, and cannot loop', () => {
    const handler = reg.slice(reg.indexOf("'controllerchange'"))
    const body = handler.slice(0, handler.indexOf('})'))
    // Both guards must sit before the reload, or one of them is decorative.
    expect(body).toMatch(/if \(!wasControlled \|\| reloading\) return/)
    expect(body.indexOf('return')).toBeLessThan(body.indexOf('location.reload'))
  })
})
