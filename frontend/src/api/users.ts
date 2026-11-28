// User management endpoints from api.md (admin only)

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockCreateUser, mockListRanges, mockListUsers, mockResetPassword, mockUpdateUser } from './mock'
import type { ManagedUser, NewUser, Range, UserChanges } from './types'

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

export function updateUser(id: number, changes: UserChanges): Promise<ManagedUser> {
  if (USE_MOCK) return mockUpdateUser(getToken(), id, changes)
  return apiFetch<ManagedUser>(`/users/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
  })
}

// the backend draws the temporary password and returns it only this once
export async function resetPassword(id: number): Promise<string> {
  if (USE_MOCK) return mockResetPassword(getToken(), id)
  const res = await apiFetch<{ temporary_password: string }>(`/users/${id}/reset-password`, { method: 'POST' })
  return res.temporary_password
}

export function listRanges(): Promise<Range[]> {
  if (USE_MOCK) return mockListRanges(getToken())
  return apiFetch<Range[]>('/ranges')
}
