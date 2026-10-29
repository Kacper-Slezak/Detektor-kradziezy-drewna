// User management endpoints from api.md (admin only)

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockCreateUser, mockListRanges, mockListUsers } from './mock'
import type { ManagedUser, NewUser, Range } from './types'

export function listUsers(): Promise<ManagedUser[]> {
  if (USE_MOCK) return mockListUsers(getToken())
  return apiFetch<ManagedUser[]>('/users')
}

export function createUser(user: NewUser): Promise<ManagedUser> {
  if (USE_MOCK) return mockCreateUser(getToken(), user)
  return apiFetch<ManagedUser>('/users', {
    method: 'POST',
    body: JSON.stringify(user),
  })
}

export function listRanges(): Promise<Range[]> {
  if (USE_MOCK) return mockListRanges(getToken())
  return apiFetch<Range[]>('/ranges')
}
