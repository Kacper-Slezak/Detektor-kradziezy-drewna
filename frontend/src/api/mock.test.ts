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

describe('user management', () => {
  const newForester = {
    login: 'anna',
    full_name: 'Anna Las',
    role: 'forester' as const,
    range_id: 2,
    password: 'Kx7p-Qm2r-Zt9w',
  }

  it('is only for the admin (403 for others)', async () => {
    await expect(mock.mockListUsers('mock-3')).rejects.toMatchObject({ status: 403 })
    await expect(mock.mockCreateUser('mock-4', newForester)).rejects.toMatchObject({ status: 403 })
    await expect(mock.mockListRanges('mock-3')).rejects.toMatchObject({ status: 403 })
  })

  it('lists users and ranges for the admin', async () => {
    const users = await mock.mockListUsers('mock-1')
    expect(users.map((u) => u.login)).toEqual(['admin', 'blazej', 'bogdan', 'nowy.lesniczy'])
    expect(users.find((u) => u.login === 'blazej')?.range_id).toBe(1)
    expect(await mock.mockListRanges('mock-1')).toHaveLength(2)
  })

  it('creates a user who must change the temporary password', async () => {
    const created = await mock.mockCreateUser('mock-1', newForester)
    expect(created).toMatchObject({ login: 'anna', range_id: 2, must_change_password: true })

    const res = await mock.mockLogin('anna', 'Kx7p-Qm2r-Zt9w')
    expect(res.user.range?.name).toBe('Leśnictwo Olszyny')
    expect(res.user.must_change_password).toBe(true)
  })

  it('rejects a taken login with 409', async () => {
    await expect(mock.mockCreateUser('mock-1', { ...newForester, login: 'blazej' })).rejects.toMatchObject({
      status: 409,
    })
  })

  it('rejects a forester without a range with 400', async () => {
    await expect(mock.mockCreateUser('mock-1', { ...newForester, range_id: null })).rejects.toMatchObject({
      status: 400,
    })
  })
})

describe('sensor management', () => {
  const newSensor = { id: '70b3d57ed0060001', range_id: 1, name: null }

  it('is only for the admin (403 for others)', async () => {
    await expect(mock.mockListSensors('mock-3')).rejects.toMatchObject({ status: 403 })
    await expect(mock.mockCreateSensor('mock-4', newSensor)).rejects.toMatchObject({ status: 403 })
  })

  it('adds an inactive, unmounted sensor with the ID in upper case', async () => {
    const created = await mock.mockCreateSensor('mock-1', newSensor)
    expect(created).toMatchObject({
      id: '70B3D57ED0060001',
      range_id: 1,
      active: false,
      state: 'inactive',
      lat: null,
    })
    expect((await mock.mockListSensors('mock-1')).map((s) => s.id)).toContain('70B3D57ED0060001')
  })

  it('rejects an ID that is not 16 hex characters with 400', async () => {
    await expect(mock.mockCreateSensor('mock-1', { ...newSensor, id: '70B3D57ED00' })).rejects.toMatchObject({
      status: 400,
    })
    await expect(
      mock.mockCreateSensor('mock-1', { ...newSensor, id: '70B3D57ED005XYZW' }),
    ).rejects.toMatchObject({ status: 400 })
  })

  it('rejects a sensor that is already added with 409', async () => {
    await expect(
      mock.mockCreateSensor('mock-1', { ...newSensor, id: '70b3d57ed0051234' }),
    ).rejects.toMatchObject({ status: 409 })
  })

  it('rejects an unknown range with 400', async () => {
    await expect(mock.mockCreateSensor('mock-1', { ...newSensor, range_id: 99 })).rejects.toMatchObject({
      status: 400,
    })
  })

  it('moves a sensor to another range and renames it', async () => {
    const saved = await mock.mockUpdateSensor('mock-1', '70B3D57ED0051234', { range_id: 2, name: 'Nowa nazwa' })
    expect(saved).toMatchObject({ range_id: 2, name: 'Nowa nazwa', state: 'alarm' })

    const listed = (await mock.mockListSensors('mock-1')).find((s) => s.id === '70B3D57ED0051234')
    expect(listed?.range_id).toBe(2)
  })

  it('rejects editing by a non-admin (403), an unknown sensor (404) and an unknown range (400)', async () => {
    await expect(mock.mockUpdateSensor('mock-3', '70B3D57ED0051234', { range_id: 2 })).rejects.toMatchObject({
      status: 403,
    })
    await expect(mock.mockUpdateSensor('mock-1', '0000000000000000', { range_id: 2 })).rejects.toMatchObject({
      status: 404,
    })
    await expect(mock.mockUpdateSensor('mock-1', '70B3D57ED0051234', { range_id: 99 })).rejects.toMatchObject({
      status: 400,
    })
  })
})
