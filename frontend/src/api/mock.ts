// Fake backend for working without FastAPI: run with VITE_USE_MOCK=true.
// Test accounts (login / password):
//   blazej / tajne123          forester
//   bogdan / tajne123          district manager
//   admin / admin123           admin
//   nowy.lesniczy / Tymczasowe123!   forester, must change password

import { generateTempPassword } from '@/lib/password'

import { ApiError } from './client'
import type {
  Alarm,
  AlarmAnswer,
  AlarmFilters,
  LoginResponse,
  ManagedUser,
  NewRelease,
  NewSensor,
  NewUser,
  PushSubscriptionBody,
  Range,
  Release,
  ReleaseFilters,
  Sensor,
  SensorChanges,
  SensorFilters,
  SensorMount,
  User,
  UserChanges,
} from './types'

interface MockAccount {
  password: string
  user: User
  // deactivated accounts cannot sign in (default: active)
  active?: boolean
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
  if (!account || account.active === false) throw new ApiError(401, 'Sesja wygasła, zaloguj się ponownie')
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
  if (!account || account.active === false) throw new ApiError(401, 'Nieprawidłowy login lub hasło')
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

function toManagedUser(account: MockAccount): ManagedUser {
  const { user } = account
  return {
    id: user.id,
    login: user.login,
    full_name: user.full_name,
    role: user.role,
    range_id: user.range?.id ?? null,
    active: account.active !== false,
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

export async function mockUpdateUser(token: string | null, id: number, changes: UserChanges): Promise<ManagedUser> {
  await delay()
  const admin = adminByToken(token)
  const account = accounts.find((a) => a.user.id === id)
  if (!account) throw new ApiError(404, 'Nie ma takiego użytkownika')
  if (account === admin && (changes.active === false || (changes.role ?? 'admin') !== 'admin')) {
    throw new ApiError(409, 'Nie możesz dezaktywować ani zdegradować własnego konta')
  }

  const role = changes.role ?? account.user.role
  const rangeId = changes.range_id !== undefined ? changes.range_id : (account.user.range?.id ?? null)
  const range = rangeId === null ? null : ranges.find((r) => r.id === rangeId)
  if (range === undefined) throw new ApiError(400, `Nie ma leśnictwa o id ${rangeId}`)
  if (role === 'forester' && !range) throw new ApiError(400, 'Leśniczy musi mieć przypisane leśnictwo')

  if (changes.full_name !== undefined) account.user.full_name = changes.full_name
  if (changes.active !== undefined) account.active = changes.active
  account.user.role = role
  account.user.range = range
  return toManagedUser(account)
}

export async function mockResetPassword(token: string | null, id: number): Promise<string> {
  await delay()
  adminByToken(token)
  const account = accounts.find((a) => a.user.id === id)
  if (!account) throw new ApiError(404, 'Nie ma takiego użytkownika')
  account.password = generateTempPassword()
  account.user.must_change_password = true
  return account.password
}

export async function mockListRanges(token: string | null): Promise<Range[]> {
  await delay()
  adminByToken(token)
  return ranges.map((r) => ({ ...r }))
}

const HOUR_MS = 60 * 60 * 1000
const hoursFromNow = (hours: number) => new Date(Date.now() + hours * HOUR_MS).toISOString()

// Sensors from the examples in api.md, plus one working, one silent and one registered but not mounted yet
const sensors: Sensor[] = [
  {
    id: '70B3D57ED0052345',
    name: 'Skład przy paśniku',
    lat: 50.0598,
    lon: 19.9605,
    range_id: 1,
    active: true,
    state: 'ok',
    battery_pct: 77,
    last_seen: '2026-10-16T10:05:30Z',
    muted_until: null,
    open_alarm_id: null,
  },
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
    // the end of release 8 below, so the release really lasts while you click around
    muted_until: hoursFromNow(2),
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
  // so that the forester of Dąbrowa has a sensor to mount too
  {
    id: '70B3D57ED005A1B2',
    name: null,
    lat: null,
    lon: null,
    range_id: 1,
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

export async function mockListSensors(token: string | null, filters: SensorFilters = {}): Promise<Sensor[]> {
  await delay()
  unmuteFinished()
  const { user } = accountByToken(token)
  return sensors
    .filter((s) => user.role !== 'forester' || s.range_id === user.range?.id)
    .filter((s) => !filters.state || s.state === filters.state)
    .filter((s) => filters.range_id === undefined || s.range_id === filters.range_id)
    .filter((s) => !filters.unmounted || s.lat === null)
    .map((s) => ({ ...s }))
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

export async function mockMountSensor(token: string | null, id: string, mount: SensorMount): Promise<Sensor> {
  await delay()
  const { user } = accountByToken(token)
  if (user.role === 'district_manager') throw new ApiError(403, 'Brak uprawnień')
  const sensor = sensors.find((s) => s.id === id)
  if (!sensor) throw new ApiError(404, `Nie ma czujnika ${id}`)
  if (user.role === 'forester' && sensor.range_id !== user.range?.id) {
    throw new ApiError(403, 'Czujnik jest w innym leśnictwie')
  }
  const name = mount.name.trim()
  if (name.length < 1 || name.length > 100) throw new ApiError(422, 'Nazwa musi mieć od 1 do 100 znaków')
  if (Math.abs(mount.lat) > 90 || Math.abs(mount.lon) > 180) throw new ApiError(422, 'Nieprawidłowa lokalizacja')

  // mounting again moves the sensor; a sensor that has not sent anything yet is silent
  Object.assign(sensor, { name, lat: mount.lat, lon: mount.lon, active: true })
  if (sensor.state === 'inactive') sensor.state = sensor.last_seen ? 'ok' : 'silent'
  return { ...sensor }
}

// Timber releases (api.md, section 3). Release 8 is the one muting "Skład przy szlabanie" right now.
// sensor_name and active are worked out when answering, like in the backend
type MockRelease = Omit<Release, 'sensor_name' | 'active'>

const RELEASE_DEFAULT_HOURS = 4
const RELEASE_MAX_HOURS = 24

// start of a past release `days` ago, or its end when it lasted `hours`; counted from today,
// so the history filters (7 days, 30 days, a year) always have something to show
const daysAgo = (days: number, hours = 0) => hoursFromNow(-24 * days + hours)

// the ongoing one, then the history (ids follow the order they were added to the mock, not the dates)
const releases: MockRelease[] = [
  {
    id: 8,
    sensor_id: '70B3D57ED0055678',
    starts_at: hoursFromNow(-1),
    ends_at: sensors.find((s) => s.id === '70B3D57ED0055678')!.muted_until!,
    carrier: 'Transdrew Sp. z o.o.',
    log_count: 24,
    comment: null,
    created_by: 'blazej',
  },
  {
    id: 7,
    sensor_id: '70B3D57ED0051234',
    starts_at: daysAgo(41),
    ends_at: daysAgo(41, 3.33),
    carrier: 'Trans-Las',
    log_count: 30,
    comment: 'odjechał wcześniej',
    created_by: 'blazej',
  },
  {
    id: 6,
    sensor_id: '70B3D57ED005DEF0',
    starts_at: daysAgo(43),
    ends_at: daysAgo(43, 4),
    carrier: null,
    log_count: null,
    comment: null,
    created_by: 'nowy.lesniczy',
  },
  {
    id: 9,
    sensor_id: '70B3D57ED0052345',
    starts_at: daysAgo(1),
    ends_at: daysAgo(1, 3),
    carrier: 'Trans-Las',
    log_count: 18,
    comment: null,
    created_by: 'blazej',
  },
  {
    id: 10,
    sensor_id: '70B3D57ED0051234',
    starts_at: daysAgo(3),
    ends_at: daysAgo(3, 4),
    carrier: 'Transdrew Sp. z o.o.',
    log_count: 40,
    comment: 'dwa kursy',
    created_by: 'blazej',
  },
  {
    id: 11,
    sensor_id: '70B3D57ED005DEF0',
    starts_at: daysAgo(6),
    ends_at: daysAgo(6, 2),
    carrier: 'Drewex',
    log_count: 12,
    comment: null,
    created_by: 'nowy.lesniczy',
  },
  {
    id: 12,
    sensor_id: '70B3D57ED0055678',
    starts_at: daysAgo(10),
    ends_at: daysAgo(10, 4),
    carrier: 'Trans-Las',
    log_count: 25,
    comment: null,
    created_by: 'blazej',
  },
  {
    id: 13,
    sensor_id: '70B3D57ED0052345',
    starts_at: daysAgo(18),
    ends_at: daysAgo(18, 1),
    carrier: null,
    log_count: null,
    comment: 'odbiór próbek do badań',
    created_by: 'blazej',
  },
  {
    id: 14,
    sensor_id: '70B3D57ED005DEF0',
    starts_at: daysAgo(25),
    ends_at: daysAgo(25, 4),
    carrier: 'Drewex',
    log_count: 30,
    comment: null,
    created_by: 'nowy.lesniczy',
  },
  {
    id: 15,
    sensor_id: '70B3D57ED0055678',
    starts_at: daysAgo(90),
    ends_at: daysAgo(90, 3),
    carrier: 'Transdrew Sp. z o.o.',
    log_count: 22,
    comment: null,
    created_by: 'blazej',
  },
  {
    id: 16,
    sensor_id: '70B3D57ED0051234',
    starts_at: daysAgo(200),
    ends_at: daysAgo(200, 4),
    carrier: 'Trans-Las',
    log_count: 35,
    comment: 'przyjechał godzinę później',
    created_by: 'blazej',
  },
  {
    id: 17,
    sensor_id: '70B3D57ED0052345',
    starts_at: daysAgo(400),
    ends_at: daysAgo(400, 2),
    carrier: null,
    log_count: 15,
    comment: null,
    created_by: 'blazej',
  },
]

// state of a sensor before its release muted it, given back when the release ends
const stateBeforeRelease = new Map<string, Sensor['state']>([['70B3D57ED0055678', 'ok']])

const isOngoing = (r: MockRelease, now = Date.now()) => Date.parse(r.starts_at) <= now && now < Date.parse(r.ends_at)

function toRelease(r: MockRelease): Release {
  const sensor = sensors.find((s) => s.id === r.sensor_id)
  return { ...r, sensor_name: sensor?.name ?? null, active: isOngoing(r) }
}

function unmute(sensor: Sensor) {
  sensor.muted_until = null
  if (sensor.state === 'muted') sensor.state = stateBeforeRelease.get(sensor.id) ?? 'ok'
  stateBeforeRelease.delete(sensor.id)
}

// The backend works out the state on every read; the mock stores it, so it settles here:
// a sensor whose release has run out watches again
function unmuteFinished() {
  for (const sensor of sensors) {
    if (sensor.muted_until && Date.parse(sensor.muted_until) <= Date.now()) unmute(sensor)
  }
}

// Creating and ending: a forester of the sensor's range, or the admin. The district manager only reads
function releaserFor(token: string | null, sensor: Sensor) {
  const { user } = accountByToken(token)
  if (user.role === 'district_manager') throw new ApiError(403, 'Brak uprawnień')
  if (user.role === 'forester' && sensor.range_id !== user.range?.id) {
    throw new ApiError(403, 'Czujnik należy do innego leśnictwa')
  }
  return user
}

export async function mockCreateRelease(token: string | null, sensorId: string, release: NewRelease): Promise<Release> {
  await delay()
  unmuteFinished()
  const sensor = sensors.find((s) => s.id === sensorId.toUpperCase())
  if (!sensor) throw new ApiError(404, `Czujnik o id ${sensorId} nie istnieje`)
  const user = releaserFor(token, sensor)
  if (sensor.lat === null || sensor.lon === null) {
    throw new ApiError(409, 'Czujnik nie jest zamontowany (brak lokalizacji)')
  }
  if ((release.carrier?.length ?? 0) > 100) throw new ApiError(422, 'Przewoźnik może mieć najwyżej 100 znaków')
  if ((release.comment?.length ?? 0) > 500) throw new ApiError(422, 'Komentarz może mieć najwyżej 500 znaków')
  if (release.log_count !== undefined && !(release.log_count >= 0 && release.log_count <= 100_000)) {
    throw new ApiError(422, 'Liczba kłód musi być od 0 do 100000')
  }

  const now = Date.now()
  const endsAt = release.ends_at ? Date.parse(release.ends_at) : now + RELEASE_DEFAULT_HOURS * HOUR_MS
  if (!(endsAt > now)) throw new ApiError(422, 'Koniec wydania musi być w przyszłości')
  if (endsAt > now + RELEASE_MAX_HOURS * HOUR_MS) {
    throw new ApiError(422, `Wydanie może trwać najwyżej ${RELEASE_MAX_HOURS} h`)
  }
  const ongoing = releases.find((r) => r.sensor_id === sensor.id && isOngoing(r, now))
  if (ongoing) {
    throw new ApiError(409, `Wydanie dla tego czujnika już trwa (id ${ongoing.id}); zakończ je albo poczekaj`)
  }

  const created: MockRelease = {
    id: Math.max(0, ...releases.map((r) => r.id)) + 1,
    sensor_id: sensor.id,
    starts_at: new Date(now).toISOString(),
    ends_at: new Date(endsAt).toISOString(),
    carrier: release.carrier ?? null,
    log_count: release.log_count ?? null,
    comment: release.comment ?? null,
    created_by: user.login,
  }
  releases.push(created)

  // api.md: an open alarm still wins over muted, and a switched-off sensor stays inactive
  sensor.muted_until = created.ends_at
  if (sensor.state === 'ok' || sensor.state === 'silent') {
    stateBeforeRelease.set(sensor.id, sensor.state)
    sensor.state = 'muted'
  }
  return toRelease(created)
}

export async function mockEndRelease(token: string | null, id: number): Promise<Release> {
  await delay()
  const release = releases.find((r) => r.id === id)
  if (!release) throw new ApiError(404, `Nie ma wydania o id ${id}`)
  const sensor = sensors.find((s) => s.id === release.sensor_id)!
  releaserFor(token, sensor)
  if (Date.parse(release.ends_at) <= Date.now()) throw new ApiError(409, 'Wydanie już się zakończyło')

  release.ends_at = new Date().toISOString()
  unmute(sensor)
  return toRelease(release)
}

export async function mockListReleases(token: string | null, filters: ReleaseFilters = {}): Promise<Release[]> {
  await delay()
  unmuteFinished()
  const { user } = accountByToken(token)
  const rangeOf = (sensorId: string) => sensors.find((s) => s.id === sensorId)?.range_id
  return releases
    .filter((r) => user.role !== 'forester' || rangeOf(r.sensor_id) === user.range?.id)
    .filter((r) => !filters.sensor_id || r.sensor_id === filters.sensor_id.toUpperCase())
    .filter((r) => filters.active === undefined || isOngoing(r) === filters.active)
    // [from, to] and the release overlap
    .filter((r) => !filters.from || Date.parse(r.ends_at) >= Date.parse(filters.from))
    .filter((r) => !filters.to || Date.parse(r.starts_at) <= Date.parse(filters.to))
    .sort((a, b) => b.starts_at.localeCompare(a.starts_at) || b.id - a.id)
    .slice(filters.offset ?? 0, (filters.offset ?? 0) + (filters.limit ?? 100))
    .map(toRelease)
}

// Alarms from the examples in api.md, plus a confirmed theft and a new one in the other range.
// Alarm 41 is the open alarm of "Skład przy drodze 5" (open_alarm_id above)
function alarmSensor(id: string) {
  const { name, lat, lon } = sensors.find((s) => s.id === id)!
  return { id, name, lat, lon }
}

const alarms: Alarm[] = [
  {
    id: 41,
    detected_at: '2026-10-16T09:57:40Z',
    last_frame_at: '2026-10-16T09:58:40Z',
    sensor: alarmSensor('70B3D57ED0051234'),
    event_type: 'theft',
    sources: ['microphone', 'vibration'],
    confidence: 87,
    duration_s: 40,
    energy: 180,
    repeats: 3,
    possible_tampering: false,
    status: 'new',
    response: null,
  },
  {
    id: 40,
    detected_at: '2026-10-15T20:10:12Z',
    last_frame_at: '2026-10-15T20:12:12Z',
    sensor: alarmSensor('70B3D57ED0052345'),
    event_type: 'theft',
    sources: ['microphone', 'vibration'],
    confidence: 93,
    duration_s: 95,
    energy: 240,
    repeats: 3,
    possible_tampering: false,
    status: 'theft',
    response: {
      by: 'blazej',
      at: '2026-10-15T21:05:00Z',
      comment: 'przewoźnik ładował 5 dodatkowych kłód',
      lat: 50.0599,
      lon: 19.9603,
    },
  },
  {
    id: 39,
    detected_at: '2026-10-15T14:12:03Z',
    last_frame_at: '2026-10-15T14:13:03Z',
    sensor: alarmSensor('70B3D57ED0051234'),
    event_type: 'theft',
    sources: ['vibration'],
    confidence: 55,
    duration_s: 12,
    energy: 60,
    repeats: 3,
    possible_tampering: true,
    status: 'false_alarm',
    response: { by: 'blazej', at: '2026-10-15T14:40:00Z', comment: 'zwierzę przy stosie', lat: 50.0646, lon: 19.9452 },
  },
  {
    id: 38,
    detected_at: '2026-10-14T21:35:50Z',
    last_frame_at: '2026-10-14T21:35:50Z',
    sensor: alarmSensor('70B3D57ED005DEF0'),
    event_type: 'theft',
    sources: ['vibration'],
    confidence: 48,
    duration_s: 8,
    energy: 35,
    repeats: 1,
    possible_tampering: true,
    status: 'new',
    response: null,
  },
]

export async function mockListAlarms(token: string | null, filters: AlarmFilters = {}): Promise<Alarm[]> {
  await delay()
  const { user } = accountByToken(token)
  const rangeOf = (sensorId: string) => sensors.find((s) => s.id === sensorId)?.range_id
  return alarms
    .filter((a) => user.role !== 'forester' || rangeOf(a.sensor.id) === user.range?.id)
    .filter((a) => !filters.status || a.status === filters.status)
    .filter((a) => !filters.sensor_id || a.sensor.id === filters.sensor_id)
    .slice(0, filters.limit ?? 100)
    .map(copyAlarm)
}

const copyAlarm = (a: Alarm): Alarm => ({ ...a, sensor: { ...a.sensor }, response: a.response && { ...a.response } })

export async function mockRespondToAlarm(token: string | null, id: number, answer: AlarmAnswer): Promise<Alarm> {
  await delay()
  const { user } = accountByToken(token)
  if (user.role === 'district_manager') throw new ApiError(403, 'Brak uprawnień')
  const alarm = alarms.find((a) => a.id === id)
  if (!alarm) throw new ApiError(404, `Nie ma alarmu o id ${id}`)
  const sensor = sensors.find((s) => s.id === alarm.sensor.id)!
  if (user.role === 'forester' && sensor.range_id !== user.range?.id) {
    throw new ApiError(403, 'Alarm dotyczy czujnika z innego leśnictwa')
  }
  if (alarm.status !== 'new') throw new ApiError(409, 'Alarm ma już odpowiedź')

  alarm.status = answer.result
  alarm.response = {
    by: user.login,
    at: new Date().toISOString(),
    comment: answer.comment ?? null,
    lat: answer.lat ?? null,
    lon: answer.lon ?? null,
  }
  // the sensor no longer has an open alarm, so its pin stops being red
  if (sensor.open_alarm_id === id) {
    sensor.open_alarm_id = null
    if (sensor.state === 'alarm') sensor.state = 'ok'
  }
  return copyAlarm(alarm)
}

// Web Push (api.md, section 6). A real P-256 key (the example from api.md), so the browser accepts it in subscribe
const MOCK_VAPID_PUBLIC_KEY =
  'BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U'

interface MockPushSubscription {
  userId: number
  endpoint: string
  keys: PushSubscriptionBody['keys']
  device_label: string | null
}

const pushSubscriptions: MockPushSubscription[] = []

export async function mockVapidPublicKey(token: string | null): Promise<string> {
  await delay()
  accountByToken(token)
  return MOCK_VAPID_PUBLIC_KEY
}

export async function mockSavePushSubscription(token: string | null, subscription: PushSubscriptionBody): Promise<void> {
  await delay()
  const { user } = accountByToken(token)
  if (user.role !== 'forester') throw new ApiError(403, 'Powiadomienia push są tylko dla leśniczych')
  if (!subscription.endpoint || !subscription.keys?.p256dh || !subscription.keys?.auth) {
    throw new ApiError(422, 'Niepełna subskrypcja')
  }
  // the same endpoint again: new keys and owner (e.g. another account on this phone), no duplicate
  const saved: MockPushSubscription = {
    userId: user.id,
    endpoint: subscription.endpoint,
    keys: { ...subscription.keys },
    device_label: subscription.device_label ?? null,
  }
  const index = pushSubscriptions.findIndex((s) => s.endpoint === subscription.endpoint)
  if (index === -1) pushSubscriptions.push(saved)
  else pushSubscriptions[index] = saved
}

export async function mockDeletePushSubscription(token: string | null, endpoint: string): Promise<void> {
  await delay()
  const { user } = accountByToken(token)
  // 204 also when it is not there; someone else's subscription stays
  const index = pushSubscriptions.findIndex((s) => s.endpoint === endpoint && s.userId === user.id)
  if (index !== -1) pushSubscriptions.splice(index, 1)
}

// Not an endpoint: lets tests (and the dev console) see who would get a push
export function mockPushSubscribers(): { login: string; endpoint: string; device_label: string | null }[] {
  return pushSubscriptions.map((s) => ({
    login: accounts.find((a) => a.user.id === s.userId)!.user.login,
    endpoint: s.endpoint,
    device_label: s.device_label,
  }))
}
