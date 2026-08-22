/**
 * Register the service worker, and notice when a new version is waiting.
 *
 * A cache-first shell is what makes the app open instantly rather than waiting
 * for a free-tier server to wake. The cost is that a deployed change can sit
 * unseen behind the cached copy, so an update is detected and applied on the
 * next navigation rather than left to chance.
 */

export function registerServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return
  // `isSecureContext` is the browser's own answer to "may I register one?".
  // Testing for https or the literal string "localhost" gets it wrong on
  // 127.0.0.1, which is a secure context too — and then nothing registers with
  // no error to explain why.
  if (!window.isSecureContext) return

  window.addEventListener('load', () => {
    void navigator.serviceWorker
      .register('/sw.js')
      .then((registration) => {
        registration.addEventListener('updatefound', () => {
          const installing = registration.installing
          if (!installing) return
          installing.addEventListener('statechange', () => {
            // A new worker has taken over an existing page: the next load is
            // the new build. Nothing is forced on the user mid-session.
            if (installing.state === 'installed' && navigator.serviceWorker.controller) {
              registration.waiting?.postMessage({ type: 'SKIP_WAITING' })
            }
          })
        })
      })
      .catch(() => {
        // A failed registration is not worth an error in the console; the app
        // works perfectly well without it.
      })
  })
}
