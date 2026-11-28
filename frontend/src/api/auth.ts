// Auth endpoints from api.md

import { USE_MOCK, apiFetch, getToken } from './client'
import { mockChangePassword, mockLogin, mockMe } from './mock'
import type { LoginResponse, User } from './types'

export function login(login: string, password: string): Promise<LoginResponse> {
  if (USE_MOCK) return mockLogin(login, password)
  return apiFetch<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ login, password }),
  })
}

export function me(): Promise<User> {
  if (USE_MOCK) return mockMe(getToken())
  return apiFetch<User>('/auth/me')
}

export function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  if (USE_MOCK) return mockChangePassword(getToken(), oldPassword, newPassword)
  return apiFetch<void>('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  })
}
