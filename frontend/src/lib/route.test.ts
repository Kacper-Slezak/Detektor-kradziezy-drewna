import { describe, expect, it } from 'vitest'

import { parseRoute, routePath, type Route } from './route'

describe('parseRoute', () => {
  it.each<[string, Route]>([
    ['/', { view: 'map' }],
    ['/alarms', { view: 'alarms', alarmId: null }],
    ['/alarms/', { view: 'alarms', alarmId: null }],
    ['/alarms/41', { view: 'alarms', alarmId: 41 }],
    ['/releases', { view: 'releases' }],
    ['/releases/', { view: 'releases' }],
  ])('reads %s', (path, route) => {
    expect(parseRoute(path)).toEqual(route)
  })

  // an old or mistyped link lands on the map instead of an empty screen
  it.each(['/releases/8', '/alarms/abc', '/nothing-here'])('opens the map for %s', (path) => {
    expect(parseRoute(path)).toEqual({ view: 'map' })
  })
})

describe('routePath', () => {
  it.each<Route>([
    { view: 'map' },
    { view: 'alarms', alarmId: null },
    { view: 'alarms', alarmId: 41 },
    { view: 'releases' },
  ])('turns %o into an address that reads back the same', (route) => {
    expect(parseRoute(routePath(route))).toEqual(route)
  })
})
