// Backend log tail from api.md (admin only)

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockListLogs } from './mock'
import type { LogLine } from './types'

export function listLogs(tail = 500): Promise<LogLine[]> {
  if (USE_MOCK) return mockListLogs(getToken(), tail)
  return apiFetch<LogLine[]>(`/admin/logs?tail=${tail}`)
}
