// Sensor endpoints. GET and POST /sensors (admin) and range_id in PATCH are not in api.md yet, agreed with backend

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockCreateSensor, mockListSensors, mockUpdateSensor } from './mock'
import type { NewSensor, Sensor, SensorChanges } from './types'

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
