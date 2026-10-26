// Udawany backend dla logowania, dopóki /auth nie istnieje w FastAPI.
// Konta testowe (login / hasło):
//   blazej / tajne123          leśniczy
//   bogdan / tajne123          nadleśniczy
//   admin / admin123           admin
//   nowy.lesniczy / Tymczasowe123!   leśniczy, musi zmienić hasło

import { ApiError } from './client'
import type { LoginResponse, User } from './types'

interface MockAccount {
  password: string
  user: User
}

const accounts: MockAccount[] = [
  {
    password: 'tajne123',
    user: {
      id: 3,
      login: 'blazej',
      full_name: 'Błażej Kowalski',
      role: 'forester',
      range: { id: 1, name: 'Leśnictwo Dąbrowa' },
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
      range: { id: 2, name: 'Leśnictwo Olszyny' },
      must_change_password: true,
    },
  },
]

function accountByToken(token: string | null): MockAccount {
  const account = accounts.find((a) => token === `mock-${a.user.id}`)
  if (!account) throw new ApiError(401, 'Sesja wygasła, zaloguj się ponownie')
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
