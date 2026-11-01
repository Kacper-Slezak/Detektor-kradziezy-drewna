// Sensor endpoints. GET and POST /sensors (admin) are not in api.md yet, agreed with backend

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockCreateSensor, mockListSensors } from './mock'
import type { NewSensor, Sensor } from './types'

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
