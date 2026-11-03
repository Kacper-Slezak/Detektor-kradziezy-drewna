// Sensor endpoints. api.md still has Polish paths (GET /czujniki); we agreed on English ones with backend.
// POST /sensors (admin) and range_id in PATCH are not in api.md yet either

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockCreateSensor, mockListSensors, mockUpdateSensor } from './mock'
import type { NewSensor, Sensor, SensorChanges, SensorFilters } from './types'

// A forester gets the sensors of their own range, a district manager and the admin get everything
export function listSensors(filters: SensorFilters = {}): Promise<Sensor[]> {
  if (USE_MOCK) return mockListSensors(getToken(), filters)
  const params = new URLSearchParams()
  if (filters.state) params.set('state', filters.state)
  if (filters.range_id !== undefined) params.set('range_id', String(filters.range_id))
  if (filters.unmounted) params.set('unmounted', 'true')
  const query = params.toString()
  return apiFetch<Sensor[]>(query ? `/sensors?${query}` : '/sensors')
}

export function createSensor(sensor: NewSensor): Promise<Sensor> {
  if (USE_MOCK) return mockCreateSensor(getToken(), sensor)
  return apiFetch<Sensor>('/sensors', {
    method: 'POST',
    body: JSON.stringify(sensor),
  })
}

export function updateSensor(id: string, changes: SensorChanges): Promise<Sensor> {
  if (USE_MOCK) return mockUpdateSensor(getToken(), id, changes)
  return apiFetch<Sensor>(`/sensors/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
  })
}
