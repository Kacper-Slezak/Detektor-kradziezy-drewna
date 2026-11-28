// Sensor endpoints. api.md still has Polish paths (GET /czujniki); we agreed on English ones with backend.
// POST /sensors (admin) and range_id in PATCH are not in api.md yet either

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockCreateSensor, mockDeleteSensor, mockListSensors, mockMountSensor, mockUpdateSensor } from './mock'
import type { NewSensor, Sensor, SensorChanges, SensorFilters, SensorMount } from './types'

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

// Admin only, for a sensor with no history (a typo in the DevEUI, a test device): 204.
// A sensor with alarms or releases gives 409; it can be switched off instead (active: false)
export function deleteSensor(id: string): Promise<void> {
  if (USE_MOCK) return mockDeleteSensor(getToken(), id)
  return apiFetch<void>(`/sensors/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// The forester mounts a sensor of their range; after this it is active and has a pin on the map
export function mountSensor(id: string, mount: SensorMount): Promise<Sensor> {
  if (USE_MOCK) return mockMountSensor(getToken(), id, mount)
  return apiFetch<Sensor>(`/sensors/${encodeURIComponent(id)}/mount`, {
    method: 'PUT',
    body: JSON.stringify(mount),
  })
}
