// Fake backend for working without FastAPI: run with VITE_USE_MOCK=true.
// Test accounts (login / password):
//   blazej / tajne123          forester
//   bogdan / tajne123          district manager
//   admin / admin123           admin
//   nowy.lesniczy / Tymczasowe123!   forester, must change password

import { ApiError } from './client'
import type { LoginResponse, ManagedUser, NewSensor, NewUser, Range, Sensor, SensorChanges, User } from './types'

interface MockAccount {
  password: string
  user: User
}

const ranges: Range[] = [
  { id: 1, name: 'Leśnictwo Dąbrowa' },
  { id: 2, name: 'Leśnictwo Olszyny' },
]

const accounts: MockAccount[] = [
  {
    password: 'tajne123',
    user: {
      id: 3,
      login: 'blazej',
      full_name: 'Błażej Kowalski',
      role: 'forester',
      range: ranges[0],
      must_change_password: false,
    },
  },
  {
    password: 'tajne123',
    user: {
      id: 4,
      login: 'bogdan',
      full_name: 'Bogdan Nowak',
      role: 'district_manager',
      range: null,
      must_change_password: false,
    },
  },
  {
    password: 'admin123',
    user: {
      id: 1,
      login: 'admin',
      full_name: 'Administrator',
      role: 'admin',
      range: null,
      must_change_password: false,
    },
  },
  {
    password: 'Tymczasowe123!',
    user: {
      id: 5,
      login: 'nowy.lesniczy',
      full_name: 'Jan Nowy',
      role: 'forester',
      range: ranges[1],
      must_change_password: true,
    },
  },
]

function accountByToken(token: string | null): MockAccount {
  const account = accounts.find((a) => token === `mock-${a.user.id}`)
  if (!account) throw new ApiError(401, 'Sesja wygasła, zaloguj się ponownie')
  return account
}

function adminByToken(token: string | null): MockAccount {
  const account = accountByToken(token)
  if (account.user.role !== 'admin') throw new ApiError(403, 'Brak uprawnień')
  return account
}

const delay = () => new Promise((resolve) => setTimeout(resolve, 400))

export async function mockLogin(login: string, password: string): Promise<LoginResponse> {
  await delay()
  const account = accounts.find((a) => a.user.login === login && a.password === password)
  if (!account) throw new ApiError(401, 'Nieprawidłowy login lub hasło')
  return {
    token: `mock-${account.user.id}`,
    expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
    user: { ...account.user },
  }
}

export async function mockMe(token: string | null): Promise<User> {
  await delay()
  return { ...accountByToken(token).user }
}

export async function mockChangePassword(
  token: string | null,
  oldPassword: string,
  newPassword: string,
): Promise<void> {
  await delay()
  const account = accountByToken(token)
  if (account.password !== oldPassword) throw new ApiError(400, 'Stare hasło jest nieprawidłowe')
  account.password = newPassword
  account.user.must_change_password = false
}

function toManagedUser({ user }: MockAccount): ManagedUser {
  return {
    id: user.id,
    login: user.login,
    full_name: user.full_name,
    role: user.role,
    range_id: user.range?.id ?? null,
    active: true,
    must_change_password: user.must_change_password,
  }
}

export async function mockListUsers(token: string | null): Promise<ManagedUser[]> {
  await delay()
  adminByToken(token)
  return accounts.map(toManagedUser).sort((a, b) => a.id - b.id)
}

export async function mockCreateUser(token: string | null, newUser: NewUser): Promise<ManagedUser> {
  await delay()
  adminByToken(token)
  if (accounts.some((a) => a.user.login === newUser.login)) {
    throw new ApiError(409, `Login ${newUser.login} jest już zajęty`)
  }
  const range = ranges.find((r) => r.id === newUser.range_id) ?? null
  if (newUser.role === 'forester' && !range) {
    throw new ApiError(400, 'Leśniczy musi mieć przypisane leśnictwo')
  }
  const account: MockAccount = {
    password: newUser.password,
    user: {
      id: Math.max(...accounts.map((a) => a.user.id)) + 1,
      login: newUser.login,
      full_name: newUser.full_name,
      role: newUser.role,
      range,
      must_change_password: true,
    },
  }
  accounts.push(account)
  return toManagedUser(account)
}

export async function mockListRanges(token: string | null): Promise<Range[]> {
  await delay()
  adminByToken(token)
  return ranges.map((r) => ({ ...r }))
}

// Sensors from the examples in api.md, plus one silent and one registered but not mounted yet
const sensors: Sensor[] = [
  {
    id: '70B3D57ED0051234',
    name: 'Skład przy drodze 5',
    lat: 50.0647,
    lon: 19.945,
    range_id: 1,
    active: true,
    state: 'alarm',
    battery_pct: 64,
    last_seen: '2026-10-16T09:58:12Z',
    muted_until: null,
    open_alarm_id: 41,
  },
  {
    id: '70B3D57ED0055678',
    name: 'Skład przy szlabanie',
    lat: 50.0712,
    lon: 19.9533,
    range_id: 1,
    active: true,
    state: 'muted',
    battery_pct: 91,
    last_seen: '2026-10-16T10:01:00Z',
    muted_until: '2026-10-16T18:00:00Z',
    open_alarm_id: null,
  },
  {
    id: '70B3D57ED005DEF0',
    name: 'Skład przy leśniczówce',
    lat: 50.0581,
    lon: 19.9312,
    range_id: 2,
    active: true,
    state: 'silent',
    battery_pct: 8,
    last_seen: '2026-10-14T21:40:00Z',
    muted_until: null,
    open_alarm_id: null,
  },
  {
    id: '70B3D57ED0059ABC',
    name: null,
    lat: null,
    lon: null,
    range_id: 2,
    active: false,
    state: 'inactive',
    battery_pct: null,
    last_seen: null,
    muted_until: null,
    open_alarm_id: null,
  },
]

// DevEUI: 16 hex characters
const SENSOR_ID = /^[0-9A-F]{16}$/

export async function mockListSensors(token: string | null): Promise<Sensor[]> {
  await delay()
  adminByToken(token)
  return sensors.map((s) => ({ ...s }))
}

export async function mockCreateSensor(token: string | null, newSensor: NewSensor): Promise<Sensor> {
  await delay()
  adminByToken(token)
  const id = newSensor.id.toUpperCase()
  if (!SENSOR_ID.test(id)) throw new ApiError(400, 'ID czujnika musi mieć 16 znaków szesnastkowych')
  if (sensors.some((s) => s.id === id)) throw new ApiError(409, `Czujnik ${id} jest już dodany`)
  if (!ranges.some((r) => r.id === newSensor.range_id)) throw new ApiError(400, 'Nie ma takiego leśnictwa')

  // a new sensor stays inactive until a forester mounts it
  const sensor: Sensor = {
    id,
    name: newSensor.name,
    lat: null,
    lon: null,
    range_id: newSensor.range_id,
    active: false,
    state: 'inactive',
    battery_pct: null,
    last_seen: null,
    muted_until: null,
    open_alarm_id: null,
  }
  sensors.push(sensor)
  return { ...sensor }
}

export async function mockUpdateSensor(token: string | null, id: string, changes: SensorChanges): Promise<Sensor> {
  await delay()
  adminByToken(token)
  const sensor = sensors.find((s) => s.id === id)
  if (!sensor) throw new ApiError(404, `Nie ma czujnika ${id}`)
  if (changes.range_id !== undefined && !ranges.some((r) => r.id === changes.range_id)) {
    throw new ApiError(400, 'Nie ma takiego leśnictwa')
  }
  Object.assign(sensor, changes)
  return { ...sensor }
}
