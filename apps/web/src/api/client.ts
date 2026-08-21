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

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  /** A 401 means "sign in", not "something broke". */
  get isUnauthorised(): boolean {
    return this.status === 401
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

  if (response.status === 204) return undefined as T

  const text = await response.text()
  const body: unknown = text ? JSON.parse(text) : null

  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : `Request failed (${response.status})`
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
