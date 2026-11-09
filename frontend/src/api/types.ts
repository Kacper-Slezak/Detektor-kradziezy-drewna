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

// Filters of GET /sensors (all optional)
export interface SensorFilters {
  state?: SensorState
  range_id?: number
  // only sensors without a location, for the list when mounting
  unmounted?: boolean
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

// Types from section 4. Alarmy

export type AlarmStatus = 'new' | 'theft' | 'false_alarm'

export type AlarmSource = 'microphone' | 'vibration'

export interface AlarmSensor {
  id: string
  name: string | null
  lat: number | null
  lon: number | null
}

// the forester's answer after checking on site
export interface AlarmResponse {
  by: string
  at: string
  comment: string | null
  lat: number | null
  lon: number | null
}

export interface Alarm {
  id: number
  detected_at: string
  last_frame_at: string
  sensor: AlarmSensor
  // 'theft' for now, any other code from the device is 'unknown'
  event_type: string
  sources: AlarmSource[]
  confidence: number
  duration_s: number
  energy: number
  repeats: number
  // only vibrations, no sound: someone may be handling the sensor
  possible_tampering: boolean
  status: AlarmStatus
  response: AlarmResponse | null
}

// Filters of GET /alarms (all optional)
export interface AlarmFilters {
  status?: AlarmStatus
  sensor_id?: string
  limit?: number
}
