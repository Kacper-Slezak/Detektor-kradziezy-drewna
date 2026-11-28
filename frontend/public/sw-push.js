// Push handling in the app's service worker, loaded by workbox importScripts (vite.config.ts).
// Plain JS: this file is copied to the build as it is.
// What the backend sends: api.md, section 6 ({ type, alarm_id, sensor_id, title, body, url }).
// Types: alarm, and about a sensor: low_battery, silent, release_ended

// only paths of this app, e.g. /alarms/41: a push must not open another site
function safeUrl(url) {
  return typeof url === 'string' && url.startsWith('/') && !url.startsWith('//') ? url : '/'
}

// one notification per alarm, and one per kind of news about a sensor: a repeat replaces it
function tagOf(data) {
  if (data.alarm_id) return `alarm-${data.alarm_id}`
  if (data.type && data.sensor_id) return `${data.type}-${data.sensor_id}`
  return undefined
}

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    // not JSON (e.g. a test push from DevTools with plain text)
    data = { body: event.data ? event.data.text() : '' }
  }
  const alarm = Boolean(data.alarm_id)
  event.waitUntil(
    self.registration.showNotification(data.title || 'Detektor kradzieży drewna', {
      body: data.body || '',
      icon: '/pwa-192x192.png',
      badge: '/pwa-192x192.png',
      // a possible theft buzzes twice, news about a sensor (battery, no contact...) only briefly
      vibrate: alarm ? [200, 100, 200] : [100],
      tag: tagOf(data),
      // the same alarm again still buzzes; the same news about a sensor replaces it quietly
      renotify: alarm,
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
