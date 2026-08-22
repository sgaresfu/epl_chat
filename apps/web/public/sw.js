/**
 * Service worker: an offline shell and a last-known-data cache.
 *
 * Two caches, because the two kinds of thing fail differently.
 *
 * The **shell** (the app itself) is cache-first: it is content-hashed, so a
 * cached copy is always correct, and serving it from disk is what makes the
 * app open instantly instead of waiting on a free-tier server waking up.
 *
 * **API data** is network-first with a cache fallback. Fresh data always wins;
 * but on a train, or while the server is asleep, the last known table is far
 * better than an error page. Responses are marked so the app can say the data
 * is from cache rather than pretending it is live.
 *
 * Never cached: the session endpoint and the event stream. A cached login
 * response would be both wrong and a security problem.
 */

const VERSION = 'v3'
const SHELL = `shell-${VERSION}`
const DATA = `data-${VERSION}`

const SHELL_URLS = ['/', '/manifest.webmanifest', '/favicon.svg']

// Anything whose answer depends on who is asking, or that never ends.
const NEVER_CACHE = [/\/api\/session/, /\/api\/stream/, /\/api\/presence/]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL).then((cache) => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting()),
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

function isShellAsset(url) {
  return url.pathname.startsWith('/assets/') || SHELL_URLS.includes(url.pathname)
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

  // Hashed assets never change under the same URL, so cache-first is safe.
  if (isShellAsset(url)) {
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
    return
  }

  // Any other navigation is a route in the single-page app: fall back to the
  // shell so a deep link works offline too.
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match('/')))
  }
})
