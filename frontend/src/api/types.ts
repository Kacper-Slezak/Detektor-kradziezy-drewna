// Typy zgodne z docs/backend/api.md (sekcja 1. Logowanie i hasło)

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
