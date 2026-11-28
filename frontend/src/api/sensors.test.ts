import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The real requests, not the mock: USE_MOCK is read when the module loads
let sensors: typeof import('./sensors')
let client: typeof import('./client')
let fetchMock: ReturnType<typeof vi.fn>

beforeEach(async () => {
  vi.stubEnv('VITE_USE_MOCK', 'false')
  vi.resetModules()
  client = await import('./client')
  sensors = await import('./sensors')
  client.setToken('abc')
  fetchMock = vi.fn().mockImplementation(async () => new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  client.setToken(null)
})

const request = () => {
  const [url, options] = fetchMock.mock.calls[0]
  return { url, method: options.method, auth: new Headers(options.headers).get('Authorization') }
}

describe('deleteSensor', () => {
  it('sends DELETE for the sensor and takes the empty 204', async () => {
    await expect(sensors.deleteSensor('70B3D57ED0059ABC')).resolves.toBeUndefined()

    expect(request()).toEqual({ url: '/api/v1/sensors/70B3D57ED0059ABC', method: 'DELETE', auth: 'Bearer abc' })
  })

  it('gives the 409 of a sensor with history as an ApiError with the backend message', async () => {
    const detail = 'Czujnik ma historię (alarmy: 2, wydania: 1), więc nie można go usunąć.'
    fetchMock.mockResolvedValue(Response.json({ detail }, { status: 409 }))

    await expect(sensors.deleteSensor('70B3D57ED0051234')).rejects.toMatchObject({ status: 409, message: detail })
  })
})
