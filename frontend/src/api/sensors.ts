// Sensor endpoints. GET /czujniki is in api.md; GET and POST /sensors (admin) and range_id in PATCH are
// not in api.md yet, agreed with backend

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockCreateSensor, mockListMapSensors, mockListSensors, mockUpdateSensor } from './mock'
import type { NewSensor, Sensor, SensorChanges, SensorFilters } from './types'

// Sensors for the map: a forester gets their own range, a district manager gets everything
export function listMapSensors(filters: SensorFilters = {}): Promise<Sensor[]> {
  if (USE_MOCK) return mockListMapSensors(getToken(), filters)
  const params = new URLSearchParams()
  if (filters.state) params.set('state', filters.state)
  if (filters.range_id !== undefined) params.set('range_id', String(filters.range_id))
  if (filters.unmounted) params.set('unmounted', 'true')
  const query = params.toString()
  return apiFetch<Sensor[]>(query ? `/czujniki?${query}` : '/czujniki')
}

export function listSensors(): Promise<Sensor[]> {
  if (USE_MOCK) return mockListSensors(getToken())
  return apiFetch<Sensor[]>('/sensors')
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
