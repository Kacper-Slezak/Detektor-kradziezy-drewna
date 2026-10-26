// Wspólna funkcja do zapytań: dokleja prefiks /api/v1 i token JWT

import i18n from '@/i18n'

const TOKEN_KEY = 'token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

// Błąd z backendu: kod HTTP + pole "detail" (patrz api.md, sekcja Błędy)
export class ApiError extends Error {
  status: number

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`/api/v1${path}`, { ...options, headers })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : i18n.t('errors.http', { status: res.status })
    throw new ApiError(res.status, detail)
  }

  // 204 nie ma treści (np. change-password)
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}
