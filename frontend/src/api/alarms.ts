// Alarm endpoints (api.md, section 4)

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockListAlarms } from './mock'
import type { Alarm, AlarmFilters } from './types'

// Newest first. A forester gets the alarms of their own range, a district manager and the admin get everything
export function listAlarms(filters: AlarmFilters = {}): Promise<Alarm[]> {
  if (USE_MOCK) return mockListAlarms(getToken(), filters)
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.sensor_id) params.set('sensor_id', filters.sensor_id)
  if (filters.limit !== undefined) params.set('limit', String(filters.limit))
  const query = params.toString()
  return apiFetch<Alarm[]>(query ? `/alarms?${query}` : '/alarms')
}
