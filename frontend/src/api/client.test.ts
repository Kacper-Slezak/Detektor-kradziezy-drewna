import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiFetch, getToken, setToken } from './client'

function mockFetch(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('token', () => {
  it('is saved, read and removed', () => {
    setToken('abc')
    expect(getToken()).toBe('abc')
    setToken(null)
    expect(getToken()).toBeNull()
  })
})

describe('apiFetch', () => {
  it('adds the /api/v1 prefix and the Bearer token', async () => {
    setToken('abc')
    const fetchMock = mockFetch(Response.json({ ok: 1 }))

    const data = await apiFetch<{ ok: number }>('/auth/me')

    expect(data).toEqual({ ok: 1 })
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/auth/me')
    expect(new Headers(options.headers).get('Authorization')).toBe('Bearer abc')
  })

  it('sends no Authorization header without a token', async () => {
    const fetchMock = mockFetch(Response.json({}))
    await apiFetch('/auth/login', { method: 'POST' })
    expect(new Headers(fetchMock.mock.calls[0][1].headers).has('Authorization')).toBe(false)
  })

  it('throws ApiError with the backend detail', async () => {
    mockFetch(Response.json({ detail: 'Nieprawidłowy login lub hasło' }, { status: 401 }))

    const err = await apiFetch('/auth/login').catch((e: unknown) => e)

    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 401, message: 'Nieprawidłowy login lub hasło' })
  })

  it('falls back to a generic message when the body has no detail', async () => {
    mockFetch(new Response('Bad Gateway', { status: 502 }))
    await expect(apiFetch('/auth/me')).rejects.toMatchObject({ status: 502, message: 'Błąd 502' })
  })

  it('returns undefined for 204', async () => {
    mockFetch(new Response(null, { status: 204 }))
    await expect(apiFetch('/auth/change-password', { method: 'POST' })).resolves.toBeUndefined()
  })
})
