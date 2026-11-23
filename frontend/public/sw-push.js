// Push handling in the app's service worker, loaded by workbox importScripts (vite.config.ts).
// Plain JS: this file is copied to the build as it is.
// What the backend sends: api.md, section 6 ({ type, alarm_id, sensor_id, title, body, url })

// only paths of this app, e.g. /alarms/41: a push must not open another site
function safeUrl(url) {
  return typeof url === 'string' && url.startsWith('/') && !url.startsWith('//') ? url : '/'
}

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    // not JSON (e.g. a test push from DevTools with plain text)
    data = { body: event.data ? event.data.text() : '' }
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'Detektor kradzieży drewna', {
      body: data.body || '',
      icon: '/pwa-192x192.png',
      badge: '/pwa-192x192.png',
      vibrate: [200, 100, 200],
      // the same alarm again replaces its notification instead of adding another one, but still buzzes
      tag: data.alarm_id ? `alarm-${data.alarm_id}` : undefined,
      renotify: Boolean(data.alarm_id),
      data: { url: safeUrl(data.url) },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = safeUrl(event.notification.data && event.notification.data.url)
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then(async (windows) => {
      // the app is already open: show the alarm there instead of opening a second window
      const open = windows.find((client) => 'navigate' in client)
      if (open) {
        const navigated = await open.navigate(url).catch(() => null)
        return (navigated || open).focus()
      }
      return self.clients.openWindow(url)
    }),
  )
})
