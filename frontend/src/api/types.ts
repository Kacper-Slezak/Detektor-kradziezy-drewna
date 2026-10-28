// Types matching docs/backend/api.md (section 1. Logowanie i hasło)

export type Role = 'forester' | 'district_manager' | 'admin'

export interface Range {
  id: number
  name: string
}

export interface User {
  id: number
  login: string
  full_name: string
  role: Role
  range: Range | null
  must_change_password: boolean
}

export interface LoginResponse {
  token: string
  expires_at: string
  user: User
}

// Types from section 2. Użytkownicy (admin only)

export interface ManagedUser {
  id: number
  login: string
  full_name: string
  role: Role
  range_id: number | null
  active: boolean
  must_change_password: boolean
}

export interface NewUser {
  login: string
  full_name: string
  role: Role
  range_id: number | null
  password: string
}
