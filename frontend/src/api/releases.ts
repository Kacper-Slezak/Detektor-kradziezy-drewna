// Timber release endpoints (api.md, section 3): the sensor is muted while the carrier takes the timber away

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockCreateRelease, mockEndRelease, mockListReleases } from './mock'
import type { NewRelease, Release, ReleaseFilters } from './types'

// Starts now. 409 when one already lasts for this sensor or the sensor is not mounted
export function createRelease(sensorId: string, release: NewRelease = {}): Promise<Release> {
  if (USE_MOCK) return mockCreateRelease(getToken(), sensorId, release)
  return apiFetch<Release>(`/sensors/${encodeURIComponent(sensorId)}/releases`, {
    method: 'POST',
    body: JSON.stringify(release),
  })
}

// The carrier left early: the sensor watches again at once. 409 when it has ended already
export function endRelease(id: number): Promise<Release> {
  if (USE_MOCK) return mockEndRelease(getToken(), id)
  return apiFetch<Release>(`/releases/${id}/end`, { method: 'POST' })
}

// Newest first. A forester gets the releases of their own range, a district manager and the admin get everything
export function listReleases(filters: ReleaseFilters = {}): Promise<Release[]> {
  if (USE_MOCK) return mockListReleases(getToken(), filters)
  const params = new URLSearchParams()
  if (filters.sensor_id) params.set('sensor_id', filters.sensor_id)
  if (filters.active !== undefined) params.set('active', String(filters.active))
  if (filters.from) params.set('from', filters.from)
  if (filters.to) params.set('to', filters.to)
  if (filters.limit !== undefined) params.set('limit', String(filters.limit))
  const query = params.toString()
  return apiFetch<Release[]>(query ? `/releases?${query}` : '/releases')
}
