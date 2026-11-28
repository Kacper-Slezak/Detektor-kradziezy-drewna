import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The real requests, not the mock: USE_MOCK is read when the module loads
let push: typeof import('./push')
let client: typeof import('./client')
let fetchMock: ReturnType<typeof vi.fn>

beforeEach(async () => {
  vi.stubEnv('VITE_USE_MOCK', 'false')
  vi.resetModules()
  client = await import('./client')
  push = await import('./push')
  fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
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

describe('push API', () => {
  it('reads the server key', async () => {
    fetchMock.mockResolvedValue(Response.json({ public_key: 'BEl6' }))
    expect(await push.getVapidPublicKey()).toBe('BEl6')
    expect(request().url).toBe('/api/v1/push/vapid-public-key')
  })

  it('sends the subscription as it is, with the device label next to it', async () => {
    client.setToken('abc')
    const subscription = {
      endpoint: 'https://fcm.googleapis.com/fcm/send/x',
      expirationTime: null,
      keys: { p256dh: 'p', auth: 'a' },
      device_label: 'Android – Chrome',
    }
    await push.savePushSubscription(subscription)

    expect(request()).toMatchObject({ url: '/api/v1/push/subscriptions', method: 'POST', auth: 'Bearer abc' })
    expect(JSON.parse(request().body)).toEqual(subscription)
  })

  it('deletes with the token from before logout and an encoded endpoint', async () => {
    client.setToken('abc')
    const token = client.getToken()
    client.setToken(null) // logout clears it first
    await push.deletePushSubscription('https://fcm.googleapis.com/fcm/send/a:b?c', token)

    expect(request()).toMatchObject({
      url: '/api/v1/push/subscriptions?endpoint=https%3A%2F%2Ffcm.googleapis.com%2Ffcm%2Fsend%2Fa%3Ab%3Fc',
      method: 'DELETE',
      auth: 'Bearer abc',
    })
  })
})
