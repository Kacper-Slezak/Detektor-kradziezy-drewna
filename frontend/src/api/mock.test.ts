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

describe('editing users', () => {
  it('changes the name, role and range', async () => {
    const saved = await mock.mockUpdateUser('mock-1', 3, { full_name: 'Błażej Kowalski-Nowak', range_id: 2 })
    expect(saved).toMatchObject({ full_name: 'Błażej Kowalski-Nowak', range_id: 2, role: 'forester' })

    // a district manager has no range
    const promoted = await mock.mockUpdateUser('mock-1', 3, { role: 'district_manager', range_id: null })
    expect(promoted).toMatchObject({ role: 'district_manager', range_id: null })
  })

  it('a deactivated user cannot sign in and loses the session', async () => {
    const saved = await mock.mockUpdateUser('mock-1', 3, { active: false })
    expect(saved.active).toBe(false)

    await expect(mock.mockLogin('blazej', 'tajne123')).rejects.toMatchObject({ status: 401 })
    await expect(mock.mockMe('mock-3')).rejects.toMatchObject({ status: 401 })

    await mock.mockUpdateUser('mock-1', 3, { active: true })
    await expect(mock.mockLogin('blazej', 'tajne123')).resolves.toBeDefined()
  })

  it('rejects a forester without a range (400), an unknown range (400) and an unknown user (404)', async () => {
    await expect(mock.mockUpdateUser('mock-1', 3, { range_id: null })).rejects.toMatchObject({ status: 400 })
    await expect(mock.mockUpdateUser('mock-1', 3, { range_id: 99 })).rejects.toMatchObject({ status: 400 })
    await expect(mock.mockUpdateUser('mock-1', 99, { active: false })).rejects.toMatchObject({ status: 404 })
  })

  it('the admin cannot deactivate or demote their own account (409)', async () => {
    await expect(mock.mockUpdateUser('mock-1', 1, { active: false })).rejects.toMatchObject({ status: 409 })
    await expect(mock.mockUpdateUser('mock-1', 1, { role: 'forester', range_id: 1 })).rejects.toMatchObject({
      status: 409,
    })
  })

  it('is only for the admin (403 for others)', async () => {
    await expect(mock.mockUpdateUser('mock-3', 4, { active: false })).rejects.toMatchObject({ status: 403 })
    await expect(mock.mockResetPassword('mock-4', 3)).rejects.toMatchObject({ status: 403 })
  })

  it('resets the password to a new temporary one', async () => {
    const temporary = await mock.mockResetPassword('mock-1', 3)

    await expect(mock.mockLogin('blazej', 'tajne123')).rejects.toMatchObject({ status: 401 })
    const res = await mock.mockLogin('blazej', temporary)
    expect(res.user.must_change_password).toBe(true)
  })
})

describe('sensor list', () => {
  it('a forester gets only the sensors of their range', async () => {
    const sensors = await mock.mockListSensors('mock-3', {})
    expect(sensors.length).toBeGreaterThan(0)
    expect(sensors.every((s) => s.range_id === 1)).toBe(true)
  })

  it('a district manager and the admin get the sensors of all ranges', async () => {
    for (const token of ['mock-4', 'mock-1']) {
      const sensors = await mock.mockListSensors(token, {})
      expect(new Set(sensors.map((s) => s.range_id))).toEqual(new Set([1, 2]))
    }
  })

  it('filters by state, range and missing location', async () => {
    const alarms = await mock.mockListSensors('mock-4', { state: 'alarm' })
    expect(alarms.map((s) => s.id)).toEqual(['70B3D57ED0051234'])

    const olszyny = await mock.mockListSensors('mock-4', { range_id: 2 })
    expect(olszyny.every((s) => s.range_id === 2)).toBe(true)

    const unmounted = await mock.mockListSensors('mock-5', { unmounted: true })
    expect(unmounted.map((s) => s.id)).toEqual(['70B3D57ED0059ABC'])
  })

  it('needs a signed-in user (401)', async () => {
    await expect(mock.mockListSensors(null, {})).rejects.toMatchObject({ status: 401 })
  })
})

describe('sensor management', () => {
  const newSensor = { id: '70b3d57ed0060001', range_id: 1, name: null }

  it('is only for the admin (403 for others)', async () => {
    await expect(mock.mockCreateSensor('mock-3', newSensor)).rejects.toMatchObject({ status: 403 })
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

describe('mounting a sensor', () => {
  const mount = { name: '  Skład przy brzozach  ', lat: 50.061, lon: 19.95 }

  it('the forester of Dąbrowa has a sensor to mount', async () => {
    const unmounted = await mock.mockListSensors('mock-3', { unmounted: true })
    expect(unmounted.map((s) => s.id)).toEqual(['70B3D57ED005A1B2'])
  })

  it('gives the sensor a name and a location and turns it on', async () => {
    const mounted = await mock.mockMountSensor('mock-3', '70B3D57ED005A1B2', mount)
    expect(mounted).toMatchObject({
      name: 'Skład przy brzozach',
      lat: 50.061,
      lon: 19.95,
      active: true,
      // it has not sent anything yet
      state: 'silent',
    })
    // it is not waiting to be mounted any more
    expect(await mock.mockListSensors('mock-3', { unmounted: true })).toEqual([])
  })

  it('moves a mounted sensor and keeps its state', async () => {
    const moved = await mock.mockMountSensor('mock-3', '70B3D57ED0051234', mount)
    expect(moved).toMatchObject({ name: 'Skład przy brzozach', lat: 50.061, state: 'alarm' })
  })

  it('is not for the district manager or a forester of another range (403)', async () => {
    await expect(mock.mockMountSensor('mock-4', '70B3D57ED005A1B2', mount)).rejects.toMatchObject({ status: 403 })
    await expect(mock.mockMountSensor('mock-5', '70B3D57ED005A1B2', mount)).rejects.toMatchObject({ status: 403 })
  })

  it('rejects an unknown sensor (404), an empty name and a wrong location (422)', async () => {
    await expect(mock.mockMountSensor('mock-3', '0000000000000000', mount)).rejects.toMatchObject({ status: 404 })
    await expect(
      mock.mockMountSensor('mock-3', '70B3D57ED005A1B2', { ...mount, name: '   ' }),
    ).rejects.toMatchObject({ status: 422 })
    await expect(
      mock.mockMountSensor('mock-3', '70B3D57ED005A1B2', { ...mount, lat: 91 }),
    ).rejects.toMatchObject({ status: 422 })
  })
})

describe('push subscriptions', () => {
  const phone = {
    endpoint: 'https://fcm.googleapis.com/fcm/send/abc',
    expirationTime: null,
    keys: { p256dh: 'BNcR', auth: 'tBHI' },
    device_label: 'Android – Chrome',
  }

  it('gives the server key to a signed-in user', async () => {
    expect(await mock.mockVapidPublicKey('mock-3')).toMatch(/^B[A-Za-z0-9_-]{86}$/)
    await expect(mock.mockVapidPublicKey(null)).rejects.toMatchObject({ status: 401 })
  })

  it('saves the subscription of a forester', async () => {
    await mock.mockSavePushSubscription('mock-3', phone)
    expect(mock.mockPushSubscribers()).toEqual([
      { login: 'blazej', endpoint: phone.endpoint, device_label: 'Android – Chrome' },
    ])
  })

  it('sends pushes only to foresters', async () => {
    await expect(mock.mockSavePushSubscription('mock-4', phone)).rejects.toMatchObject({ status: 403 })
    await expect(mock.mockSavePushSubscription('mock-1', phone)).rejects.toMatchObject({ status: 403 })
    expect(mock.mockPushSubscribers()).toEqual([])
  })

  it('rejects a subscription without keys', async () => {
    await expect(
      mock.mockSavePushSubscription('mock-3', { ...phone, keys: { p256dh: '', auth: '' } }),
    ).rejects.toMatchObject({ status: 422 })
  })

  it('gives the same phone to the account that signed in last, without a duplicate', async () => {
    await mock.mockSavePushSubscription('mock-3', phone)
    await mock.mockSavePushSubscription('mock-5', { ...phone, device_label: undefined })
    expect(mock.mockPushSubscribers()).toEqual([
      { login: 'nowy.lesniczy', endpoint: phone.endpoint, device_label: null },
    ])
  })

  it('deletes only your own subscription, and says nothing when it is not there', async () => {
    await mock.mockSavePushSubscription('mock-3', phone)

    await mock.mockDeletePushSubscription('mock-5', phone.endpoint)
    expect(mock.mockPushSubscribers()).toHaveLength(1)

    await mock.mockDeletePushSubscription('mock-3', phone.endpoint)
    expect(mock.mockPushSubscribers()).toEqual([])
    await expect(mock.mockDeletePushSubscription('mock-3', phone.endpoint)).resolves.toBeUndefined()
  })
})

describe('timber releases', () => {
  const PASNIK = '70B3D57ED0052345' // ok, Dąbrowa
  const DROGA = '70B3D57ED0051234' // open alarm 41, Dąbrowa
  const SZLABAN = '70B3D57ED0055678' // muted by release 8, Dąbrowa
  const LESNICZOWKA = '70B3D57ED005DEF0' // Olszyny
  const UNMOUNTED = '70B3D57ED005A1B2' // Dąbrowa, no location
  const HOUR = 60 * 60 * 1000

  const sensor = async (id: string) => (await mock.mockListSensors('mock-4')).find((s) => s.id === id)!

  it('a forester sees the releases of their range, newest first', async () => {
    const list = await mock.mockListReleases('mock-3')
    // 11 and 14 are in Olszyny
    expect(list.map((r) => r.id)).toEqual([8, 9, 10, 12, 13, 7, 15, 16, 17])
    expect(list[0]).toMatchObject({ sensor_name: 'Skład przy szlabanie', active: true })
    expect(list.slice(1).every((r) => !r.active)).toBe(true)
    // the ongoing release is the one muting the sensor on the map
    expect(list[0].ends_at).toBe((await sensor(SZLABAN)).muted_until)
  })

  it('a district manager sees all ranges and can filter', async () => {
    const ids = async (filters: Parameters<typeof mock.mockListReleases>[1]) =>
      (await mock.mockListReleases('mock-4', filters)).map((r) => r.id)

    expect(await ids({})).toEqual([8, 9, 10, 11, 12, 13, 14, 7, 6, 15, 16, 17])
    expect(await ids({ active: true })).toEqual([8])
    expect(await ids({ active: false })).toEqual([9, 10, 11, 12, 13, 14, 7, 6, 15, 16, 17])
    expect(await ids({ sensor_id: DROGA })).toEqual([10, 7, 16])
    // releases that lasted at least partly during release 7
    const seven = (await mock.mockListReleases('mock-4')).find((r) => r.id === 7)!
    expect(await ids({ from: seven.starts_at, to: seven.starts_at })).toEqual([7])
  })

  it('gives the history of the last days, a page at a time', async () => {
    const daysAgo = (days: number) => new Date(Date.now() - days * 24 * HOUR).toISOString()
    const ids = async (filters: Parameters<typeof mock.mockListReleases>[1]) =>
      (await mock.mockListReleases('mock-4', filters)).map((r) => r.id)

    expect(await ids({ active: false, from: daysAgo(7) })).toEqual([9, 10, 11])
    expect(await ids({ active: false, from: daysAgo(30) })).toEqual([9, 10, 11, 12, 13, 14])
    // "show older": the next page starts where the first one ended
    expect(await ids({ active: false, limit: 4 })).toEqual([9, 10, 11, 12])
    expect(await ids({ active: false, limit: 4, offset: 4 })).toEqual([13, 14, 7, 6])
    expect(await ids({ active: false, limit: 4, offset: 12 })).toEqual([])
  })

  it('mutes a sensor for 4 h by default', async () => {
    const before = Date.now()
    const release = await mock.mockCreateRelease('mock-3', PASNIK, { carrier: 'Trans-Las', log_count: 12 })

    expect(release).toMatchObject({
      id: 18,
      sensor_id: PASNIK,
      sensor_name: 'Skład przy paśniku',
      active: true,
      carrier: 'Trans-Las',
      log_count: 12,
      comment: null,
      created_by: 'blazej',
    })
    const hours = (Date.parse(release.ends_at) - before) / HOUR
    expect(hours).toBeGreaterThanOrEqual(4)
    expect(hours).toBeLessThan(4.1)
    expect(await sensor(PASNIK)).toMatchObject({ state: 'muted', muted_until: release.ends_at })
  })

  it('takes the end the forester chose', async () => {
    const ends_at = new Date(Date.now() + 2 * HOUR).toISOString()
    const release = await mock.mockCreateRelease('mock-3', PASNIK, { ends_at })
    expect(Date.parse(release.ends_at)).toBe(Date.parse(ends_at))
  })

  it('ending early lets the sensor watch again, and only once', async () => {
    const release = await mock.mockEndRelease('mock-3', 8)

    expect(release.active).toBe(false)
    expect(Date.parse(release.ends_at)).toBeLessThanOrEqual(Date.now())
    expect(await sensor(SZLABAN)).toMatchObject({ state: 'ok', muted_until: null })
    await expect(mock.mockEndRelease('mock-3', 8)).rejects.toMatchObject({ status: 409 })
    await expect(mock.mockEndRelease('mock-3', 7)).rejects.toMatchObject({ status: 409 })
  })

  it('keeps the alarm pin red while the timber is taken away', async () => {
    const release = await mock.mockCreateRelease('mock-3', DROGA, {})
    expect(await sensor(DROGA)).toMatchObject({ state: 'alarm', muted_until: release.ends_at })

    await mock.mockEndRelease('mock-3', release.id)
    expect(await sensor(DROGA)).toMatchObject({ state: 'alarm', muted_until: null })
  })

  it('watches again by itself when the release runs out', async () => {
    // only the clock moves; the mock's delays stay real
    vi.useFakeTimers({ toFake: ['Date'] })
    try {
      vi.setSystemTime(Date.now() + 3 * HOUR)
      expect(await sensor(SZLABAN)).toMatchObject({ state: 'ok', muted_until: null })
      expect((await mock.mockListReleases('mock-3', { active: true }))).toEqual([])
    } finally {
      vi.useRealTimers()
    }
  })

  it.each([
    ['the district manager', 'mock-4', PASNIK, {}, 403],
    ['a forester of another range', 'mock-3', LESNICZOWKA, {}, 403],
    ['a sensor that does not exist', 'mock-3', 'FFFFFFFFFFFFFFFF', {}, 404],
    ['a sensor that is not mounted', 'mock-3', UNMOUNTED, {}, 409],
    ['a sensor that is muted already', 'mock-3', SZLABAN, {}, 409],
    ['an end in the past', 'mock-3', PASNIK, { ends_at: '2026-01-01T00:00:00Z' }, 422],
    ['more than 24 h', 'mock-3', PASNIK, { ends_at: new Date(Date.now() + 25 * HOUR).toISOString() }, 422],
    ['a too long carrier', 'mock-3', PASNIK, { carrier: 'x'.repeat(101) }, 422],
    ['a negative number of logs', 'mock-3', PASNIK, { log_count: -1 }, 422],
  ])('refuses %s', async (_, token, sensorId, release, status) => {
    await expect(mock.mockCreateRelease(token, sensorId, release)).rejects.toMatchObject({ status })
  })

  it('says which release lasts already, so the app can end it', async () => {
    await expect(mock.mockCreateRelease('mock-3', SZLABAN, {})).rejects.toMatchObject({
      status: 409,
      message: expect.stringContaining('id 8'),
    })
  })

  it('lets only the sensor range end a release', async () => {
    await expect(mock.mockEndRelease('mock-4', 8)).rejects.toMatchObject({ status: 403 })
    await expect(mock.mockEndRelease('mock-5', 8)).rejects.toMatchObject({ status: 403 })
    await expect(mock.mockEndRelease('mock-3', 99)).rejects.toMatchObject({ status: 404 })
  })
})
