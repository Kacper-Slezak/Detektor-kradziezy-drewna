// Alarm endpoints (api.md, section 4)

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockListAlarms, mockRespondToAlarm } from './mock'
import type { Alarm, AlarmAnswer, AlarmFilters } from './types'

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

// The forester's answer closes the alarm. A second answer to the same alarm is 409
export function respondToAlarm(id: number, answer: AlarmAnswer): Promise<Alarm> {
  if (USE_MOCK) return mockRespondToAlarm(getToken(), id, answer)
  return apiFetch<Alarm>(`/alarms/${id}/response`, {
    method: 'POST',
    body: JSON.stringify(answer),
  })
}
