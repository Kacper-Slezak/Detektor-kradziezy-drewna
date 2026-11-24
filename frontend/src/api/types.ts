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

// PUT /sensors/{id}/mount: the forester names the sensor on site, the phone gives the location
export interface SensorMount {
  // 1-100 characters, trimmed by the backend
  name: string
  lat: number
  lon: number
}

// Types from section 3. Wydania drewna: the sensor is muted while the timber is taken away

export interface Release {
  id: number
  sensor_id: string
  sensor_name: string | null
  // ISO 8601, UTC; it starts when it is created
  starts_at: string
  // set to "now" when the forester ends it early
  ends_at: string
  // whether it lasts at the moment of the answer
  active: boolean
  carrier: string | null
  log_count: number | null
  comment: string | null
  // login of whoever created it
  created_by: string | null
}

// POST /sensors/{id}/releases. Without ends_at the backend takes 4 h; at most 24 h from now
export interface NewRelease {
  ends_at?: string
  // up to 100 characters
  carrier?: string
  // number of logs, 0-100000
  log_count?: number
  // up to 500 characters
  comment?: string
}

// GET /releases; newest first, a forester gets only their own range
export interface ReleaseFilters {
  sensor_id?: string
  // true = only ongoing, false = only finished
  active?: boolean
  // releases that lasted at least partly between from and to (ISO 8601)
  from?: string
  to?: string
  // a page of the list: at most limit releases (backend default 100, max 500), skipping offset
  limit?: number
  offset?: number
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

// POST /alarms/{id}/response: what the forester found on site
export type AlarmResult = Exclude<AlarmStatus, 'new'>

export interface AlarmAnswer {
  result: AlarmResult
  // up to 500 characters
  comment?: string
  // lat and lon go together or not at all
  lat?: number
  lon?: number
}

// Filters of GET /alarms (all optional)
export interface AlarmFilters {
  status?: AlarmStatus
  sensor_id?: string
  limit?: number
}

// POST /push/subscriptions: what subscription.toJSON() gives, plus a label of the device (api.md, section 6)
export interface PushSubscriptionBody {
  endpoint: string
  // the backend ignores it
  expirationTime?: number | null
  keys: { p256dh: string; auth: string }
  // e.g. "Android – Chrome", so the forester can tell their devices apart
  device_label?: string
}
