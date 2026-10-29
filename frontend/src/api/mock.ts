// Fake backend for working without FastAPI: run with VITE_USE_MOCK=true.
// Test accounts (login / password):
//   blazej / tajne123          forester
//   bogdan / tajne123          district manager
//   admin / admin123           admin
//   nowy.lesniczy / Tymczasowe123!   forester, must change password

import { ApiError } from './client'
import type { LoginResponse, ManagedUser, NewUser, Range, User } from './types'

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
