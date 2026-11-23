import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The real requests, not the mock: USE_MOCK is read when the module loads
let releases: typeof import('./releases')
let client: typeof import('./client')
let fetchMock: ReturnType<typeof vi.fn>

beforeEach(async () => {
  vi.stubEnv('VITE_USE_MOCK', 'false')
  vi.resetModules()
  client = await import('./client')
  releases = await import('./releases')
  client.setToken('abc')
  fetchMock = vi.fn().mockImplementation(async () => Response.json({}))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  client.setToken(null)
})

const request = (n = 0) => {
  const [url, options] = fetchMock.mock.calls[n]
  return { url, method: options.method ?? 'GET', auth: new Headers(options.headers).get('Authorization'), body: options.body }
}

describe('releases API', () => {
  it('creates a release for a sensor', async () => {
    const release = { ends_at: '2026-10-16T14:05:00Z', carrier: 'Trans-Las', log_count: 30 }
    await releases.createRelease('70B3D57ED0055678', release)

    expect(request()).toMatchObject({
      url: '/api/v1/sensors/70B3D57ED0055678/releases',
      method: 'POST',
      auth: 'Bearer abc',
    })
    expect(JSON.parse(request().body)).toEqual(release)
  })

  it('sends an empty body when nothing is given, so the backend takes 4 h', async () => {
    await releases.createRelease('70B3D57ED0055678')
    expect(JSON.parse(request().body)).toEqual({})
  })

  it('ends a release early', async () => {
    await releases.endRelease(8)
    expect(request()).toMatchObject({ url: '/api/v1/releases/8/end', method: 'POST', body: undefined })
  })

  it('lists releases without filters', async () => {
    fetchMock.mockResolvedValue(Response.json([]))
    expect(await releases.listReleases()).toEqual([])
    expect(request()).toMatchObject({ url: '/api/v1/releases', method: 'GET' })
  })

  it('puts the filters in the address, also active=false', async () => {
    fetchMock.mockResolvedValue(Response.json([]))
    await releases.listReleases({
      sensor_id: '70B3D57ED0055678',
      active: false,
      from: '2026-10-01T00:00:00Z',
      to: '2026-10-31T23:59:59Z',
      limit: 20,
    })

    const params = new URL(request().url, 'http://x').searchParams
    expect(Object.fromEntries(params)).toEqual({
      sensor_id: '70B3D57ED0055678',
      active: 'false',
      from: '2026-10-01T00:00:00Z',
      to: '2026-10-31T23:59:59Z',
      limit: '20',
    })
  })
})
