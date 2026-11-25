// The app has no router: the address only says which view of the home screen is open.
// "/alarms" is the alarm list, "/alarms/41" the list with alarm 41 shown (a push opens it,
// api.md section 6), "/releases" the timber releases, "/sensors/70B3D57ED0051234" the map
// with that sensor's pin open (a push about a sensor opens it), anything else is the map.

export type Route =
  | { view: 'map'; sensorId?: string }
  | { view: 'alarms'; alarmId: number | null }
  | { view: 'releases' }

export function parseRoute(path: string = window.location.pathname): Route {
  if (/^\/releases\/?$/.test(path)) return { view: 'releases' }
  const sensor = /^\/sensors\/([^/]+)\/?$/.exec(path)
  if (sensor) {
    try {
      return { view: 'map', sensorId: decodeURIComponent(sensor[1]) }
    } catch {
      // a broken address (e.g. a lone %) is just the map
      return { view: 'map' }
    }
  }
  const match = /^\/alarms(?:\/(\d+))?\/?$/.exec(path)
  if (!match) return { view: 'map' }
  return { view: 'alarms', alarmId: match[1] ? Number(match[1]) : null }
}

export function routePath(route: Route): string {
  if (route.view === 'map') return route.sensorId ? `/sensors/${encodeURIComponent(route.sensorId)}` : '/'
  if (route.view === 'releases') return '/releases'
  return route.alarmId === null ? '/alarms' : `/alarms/${route.alarmId}`
}

// a new history entry, so the phone's back button returns to the previous view
export function goTo(route: Route) {
  const path = routePath(route)
  if (path !== window.location.pathname) window.history.pushState(null, '', path)
}

// after logging out the next person starts on the map
export function resetRoute() {
  if (window.location.pathname !== '/') window.history.replaceState(null, '', '/')
}
