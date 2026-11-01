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

// Types from section 7. Użytkownicy (admin)

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

// PATCH /users/{id}: only the fields being changed; range_id: null unassigns the range
export interface UserChanges {
  full_name?: string
  role?: Role
  range_id?: number | null
  active?: boolean
}

// Types from section 2. Czujniki (mapa)

export type SensorState = 'ok' | 'muted' | 'alarm' | 'silent' | 'inactive'

export interface Sensor {
  id: string
  name: string | null
  lat: number | null
  lon: number | null
  range_id: number | null
  active: boolean
  state: SensorState
  battery_pct: number | null
  last_seen: string | null
  muted_until: string | null
  open_alarm_id: number | null
}

// Sensor registration by the admin: not in api.md yet, agreed with backend
export interface NewSensor {
  id: string
  range_id: number
  name: string | null
}

// PATCH /sensors/{id}: only the fields being changed. range_id is not in api.md yet, agreed with backend
export interface SensorChanges {
  name?: string | null
  range_id?: number
  active?: boolean
}
