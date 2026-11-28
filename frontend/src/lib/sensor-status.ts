// Sensor state shown in the app: the same colours in the admin table and on the map

import type { Sensor } from '@/api/types'

// State from api.md, plus "unmounted": registered but without a location yet
export type Status = Sensor['state'] | 'unmounted'

export function statusOf(sensor: Sensor): Status {
  if (sensor.state === 'inactive' && sensor.lat === null) return 'unmounted'
  return sensor.state
}

export const STATUS_DOT: Record<Status, string> = {
  ok: 'bg-emerald-500',
  muted: 'bg-sky-500',
  alarm: 'bg-red-500',
  silent: 'bg-amber-500',
  inactive: 'bg-muted-foreground',
  unmounted: 'bg-muted-foreground',
}

export const LOW_BATTERY_PCT = 20

export function formatDateTime(iso: string, language: string): string {
  return new Date(iso).toLocaleString(language, { dateStyle: 'short', timeStyle: 'short' })
}
