/**
 * The HTTP client.
 *
 * Two things matter here and both are easy to get wrong:
 *
 * 1. `credentials: 'include'` on every request. The frontend is a static site
 *    on a CDN and the api is a separate service, so the session cookie is
 *    cross-origin and is simply not sent without this.
 * 2. The CSRF token is read from the readable `pl_csrf` cookie and echoed in a
 *    header on every mutation -- the double-submit half the server checks.
 */

/**
 * Where the API lives.
 *
 * Render's blueprint can only inject a service's *host* (`x.onrender.com`),
 * not a full URL, so a bare host is normalised to `https://` here. Left empty
 * in development, where Vite proxies `/api` and the two are same-origin.
 */
function resolveBase(): string {
  const raw = (import.meta.env.VITE_API_BASE as string | undefined)?.trim() ?? ''
  if (!raw) return ''
  const withScheme = /^https?:\/\//.test(raw) ? raw : `https://${raw}`
  return withScheme.replace(/\/$/, '')
}

export const API_BASE = resolveBase()

/**
 * Send the browser to the origin that actually owns the session.
 *
 * The api serves this app itself, so the two are same-origin and the cookie is
 * first-party. A build deployed anywhere else — an older static site still
 * sitting on its own hostname — talks to the api cross-origin, which makes the
 * cookie third-party. Every browser on iOS is WebKit, so Safari drops it and
 * login silently fails: the request succeeds, the cookie is discarded, and the
 * next call is anonymous again.
 *
 * Rather than leave a stale bookmark to strand somebody, a build that finds
 * itself on the wrong origin forwards to the right one, keeping the path.
 */
export function redirectToCanonicalOrigin(): boolean {
  if (typeof window === 'undefined' || !API_BASE) return false
  const here = window.location.origin.replace(/\/$/, '')
  if (here === API_BASE) return false

  const target = `${API_BASE}${window.location.pathname}${window.location.search}`
  window.location.replace(target)
  return true
}

/**
 * Whether the last response came from the service worker's cache.
 *
 * A cached response is a *successful* response, so "did the request work?"
 * cannot tell live data from a copy served while offline. The worker stamps
 * `X-From-Cache` on anything it replays, which is the only honest signal.
 */
let servedFromCache = false
const cacheListeners = new Set<(cached: boolean) => void>()

export function onCacheStateChange(fn: (cached: boolean) => void): () => void {
  cacheListeners.add(fn)
  return () => cacheListeners.delete(fn)
}

export function isServedFromCache(): boolean {
  return servedFromCache
}

function noteCacheState(cached: boolean): void {
  if (cached === servedFromCache) return
  servedFromCache = cached
  for (const fn of cacheListeners) fn(cached)
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** True when the fix is to sign in again rather than to retry. */
    readonly needsSignIn = false,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  /** A 401 means "sign in", not "something broke". */
  get isUnauthorised(): boolean {
    return this.status === 401 || this.needsSignIn
  }
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)pl_csrf=([^;]+)/)
  return match?.[1] ? decodeURIComponent(match[1]) : ''
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)

  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    headers.set('X-CSRF-Token', csrfToken())
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: 'include',
    })
  } catch {
    // A network failure is not an exception the user should read a stack for.
    throw new ApiError(0, 'Could not reach the server. Check your connection.')
  }

  noteCacheState(response.headers.get('X-From-Cache') === '1')

  if (response.status === 204) return undefined as T

  const text = await response.text()
  const body: unknown = text ? JSON.parse(text) : null

  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : `Request failed (${response.status})`

    // A CSRF failure almost always means a stale session rather than an
    // attack: cookies left over from a previous deployment are no longer sent,
    // so the token cannot match. Clearing them and asking for the code word
    // again fixes it, which is a far better answer than showing somebody
    // "CSRF token missing or invalid" and leaving them stuck.
    if (response.status === 403 && detail.toLowerCase().includes('csrf')) {
      throw new ApiError(403, 'Your session expired. Sign in again.', true)
    }

    throw new ApiError(response.status, detail)
  }

  return body as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
