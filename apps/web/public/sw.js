/**
 * Service worker: an offline shell and a last-known-data cache.
 *
 * Three kinds of thing, because they go stale differently.
 *
 * **The document** (`index.html`, and every SPA route that resolves to it) is
 * **network-first**. This is the one rule that matters and the one that was
 * wrong: index.html is the only file in the build that is *not*
 * content-hashed, and its entire job is to name the hashed chunks belonging
 * to the current build. Serving it cache-first pins a returning visitor to
 * whichever build they first loaded — new deploys become invisible to them,
 * permanently, no matter how many times they reopen the app. That is exactly
 * how a shipped feature can be live on the server and absent in the browser.
 *
 * **Hashed assets** under `/assets/` *are* safe cache-first: the filename
 * changes whenever the contents do, so a cached copy can never be wrong, and
 * serving them from disk is what makes the app open instantly rather than
 * waiting on a free-tier server waking up.
 *
 * **API data** is network-first with a cache fallback. Fresh data always
 * wins; but on a train, or while the server is asleep, the last known table
 * beats an error page. Responses are marked so the app can say the data came
 * from cache rather than implying it is live.
 *
 * Never cached: the session endpoint and the event stream. A cached login
 * response would be both wrong and a security problem.
 */

// Bumped to purge the poisoned v3 shell, which may be holding an index.html
// from an old build on any device that visited before this fix.
const VERSION = 'v4'
const SHELL = `shell-${VERSION}`
const DATA = `data-${VERSION}`

// Genuinely static, genuinely safe to serve from disk without asking.
// index.html is deliberately absent -- see the note above.
const STATIC_URLS = ['/manifest.webmanifest', '/favicon.svg']

// Kept only as the offline fallback for a navigation, never as the preferred
// answer while there is a network.
const OFFLINE_DOC = '/'

// Anything whose answer depends on who is asking, or that never ends.
const NEVER_CACHE = [/\/api\/session/, /\/api\/stream/, /\/api\/presence/]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      // The document is fetched here too, but only so there is something to
      // show with no network. `addAll` rejects wholesale if any request
      // fails, so the document is added separately and allowed to fail.
      .then((cache) =>
        cache.addAll(STATIC_URLS).then(() =>
          cache.add(OFFLINE_DOC).catch(() => {
            /* offline at install: the fallback fills in on first success */
          }),
        ),
      )
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => !k.endsWith(VERSION)).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  )
})

/** Content-hashed, so a cached copy can never be the wrong copy. */
function isImmutableAsset(url) {
  return url.pathname.startsWith('/assets/')
}

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting()
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  if (NEVER_CACHE.some((p) => p.test(url.pathname))) return

  // --- the document: always ask the network first ------------------------
  //
  // A navigation is how a new build reaches somebody. Answering it from disk
  // is what made the previous version undeployable in practice.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Keep the newest good document as the offline fallback.
          const copy = response.clone()
          caches.open(SHELL).then((c) => c.put(OFFLINE_DOC, copy))
          return response
        })
        .catch(async () => {
          const hit = await caches.match(OFFLINE_DOC)
          if (hit) return hit
          return new Response('Offline, and nothing cached yet.', {
            status: 503,
            headers: { 'Content-Type': 'text/plain' },
          })
        }),
    )
    return
  }

  // --- hashed assets: cache-first is safe and fast ------------------------
  if (isImmutableAsset(url) || STATIC_URLS.includes(url.pathname)) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            const copy = response.clone()
            caches.open(SHELL).then((c) => c.put(request, copy))
            return response
          }),
      ),
    )
    return
  }

  // --- api data: fresh if possible, last-known if not ---------------------
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone()
            caches.open(DATA).then((c) => c.put(request, copy))
          }
          return response
        })
        .catch(async () => {
          const hit = await caches.match(request)
          if (!hit) throw new Error('offline and nothing cached')
          // Tell the app this is stale so it can say so rather than imply live.
          const headers = new Headers(hit.headers)
          headers.set('X-From-Cache', '1')
          return new Response(hit.body, { status: hit.status, headers })
        }),
    )
  }
})
