// Checking for a new version of the installed app.
// The browser looks for a new service worker only when a page loads, but an installed app
// on Android is usually brought back from the background instead of loaded again.
// So we also check when the app comes back to the screen and every hour while it stays open.
// Activating the new version and reloading the page is done by registerSW (main.tsx).

const CHECK_INTERVAL_MS = 60 * 60 * 1000

export function watchForUpdates(registration: ServiceWorkerRegistration) {
  function check() {
    // offline there is nothing to check; the saved version keeps working
    if (!navigator.onLine) return
    registration.update().catch(() => {
      // server unreachable (e.g. tunnel closed), try again next time
    })
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') check()
  })
  setInterval(check, CHECK_INTERVAL_MS)
}
