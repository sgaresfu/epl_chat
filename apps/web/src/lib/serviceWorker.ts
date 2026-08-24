/**
 * Register the service worker, and get a new build in front of the user.
 *
 * The worker serves the document network-first, so an ordinary deploy lands on
 * the very next load with nothing special happening here. The one case that
 * needs help is a deploy that changes *the worker itself*: the load that
 * discovers the new worker has already been answered by the old one, so the
 * page on screen is the old build. Left alone that resolves on the following
 * load — which, for anybody who opens the app and closes it again, may be
 * days away, or never.
 *
 * So when a new worker takes over a page that was already controlled, reload
 * once. `wasControlled` is the guard that matters: on a first-ever visit the
 * worker also claims the page, and reloading there would be a pointless flash
 * on somebody's first impression of the app.
 */

export function registerServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return
  // `isSecureContext` is the browser's own answer to "may I register one?".
  // Testing for https or the literal string "localhost" gets it wrong on
  // 127.0.0.1, which is a secure context too — and then nothing registers with
  // no error to explain why.
  if (!window.isSecureContext) return

  // Read before anything is registered: afterwards it tells us nothing.
  const wasControlled = Boolean(navigator.serviceWorker.controller)
  let reloading = false

  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!wasControlled || reloading) return
    reloading = true
    window.location.reload()
  })

  window.addEventListener('load', () => {
    void navigator.serviceWorker
      .register('/sw.js')
      .then((registration) => {
        registration.addEventListener('updatefound', () => {
          const installing = registration.installing
          if (!installing) return
          installing.addEventListener('statechange', () => {
            // Installed while a worker is already running means an update, not
            // a first visit. Hand over immediately; `controllerchange` above
            // then puts the new build on screen.
            if (installing.state === 'installed' && navigator.serviceWorker.controller) {
              installing.postMessage({ type: 'SKIP_WAITING' })
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
