import { beforeEach, describe, expect, it, vi } from 'vitest'

// Mock accounts are module state (changing a password edits them), so each test gets a fresh copy
let mock: typeof import('./mock')

beforeEach(async () => {
  vi.resetModules()
  mock = await import('./mock')
})

describe('mockLogin', () => {
  it('returns a token and the user for a correct password', async () => {
    const res = await mock.mockLogin('blazej', 'tajne123')
    expect(res.token).toBe('mock-3')
    expect(res.user.role).toBe('forester')
    expect(res.user.range?.name).toBe('Leśnictwo Dąbrowa')
    expect(new Date(res.expires_at).getTime()).toBeGreaterThan(Date.now())
  })

  it('rejects a wrong password with 401', async () => {
    await expect(mock.mockLogin('blazej', 'zle')).rejects.toMatchObject({ status: 401 })
  })

  it('rejects an unknown login with 401', async () => {
    await expect(mock.mockLogin('nikt', 'tajne123')).rejects.toMatchObject({ status: 401 })
  })
})

describe('mockMe', () => {
  it('returns the user for a valid token', async () => {
    const user = await mock.mockMe('mock-4')
    expect(user.login).toBe('bogdan')
  })

  it('rejects a missing or invalid token with 401', async () => {
    await expect(mock.mockMe(null)).rejects.toMatchObject({ status: 401 })
    await expect(mock.mockMe('mock-999')).rejects.toMatchObject({ status: 401 })
  })
})

describe('mockChangePassword', () => {
  it('rejects a wrong old password with 400', async () => {
    await expect(mock.mockChangePassword('mock-3', 'zle', 'NoweHaslo1')).rejects.toMatchObject({
      status: 400,
    })
  })

  it('sets the new password and clears must_change_password', async () => {
    expect((await mock.mockMe('mock-5')).must_change_password).toBe(true)

    await mock.mockChangePassword('mock-5', 'Tymczasowe123!', 'NoweHaslo1')

    expect((await mock.mockMe('mock-5')).must_change_password).toBe(false)
    await expect(mock.mockLogin('nowy.lesniczy', 'Tymczasowe123!')).rejects.toMatchObject({
      status: 401,
    })
    await expect(mock.mockLogin('nowy.lesniczy', 'NoweHaslo1')).resolves.toBeDefined()
  })
})
