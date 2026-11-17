import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setToken } from '@/api/client'

// The mock keeps subscriptions in module state, so each test loads it fresh
let push: typeof import('./push')
let mock: typeof import('@/api/mock')

const ANDROID_CHROME =
  'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36'
const IPHONE_SAFARI =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'

// A fake browser: jsdom has no service worker, push or notifications
function fakeBrowser({
  permission = 'default' as NotificationPermission,
  answer = 'granted' as NotificationPermission,
  registered = true,
  existingKey = null as Uint8Array | null,
  userAgent = ANDROID_CHROME,
} = {}) {
  let subscription: PushSubscription | null = null
  const makeSubscription = (key: Uint8Array) => {
    const sub = {
      endpoint: 'https://fcm.googleapis.com/fcm/send/phone-1',
      options: { applicationServerKey: key.buffer },
      toJSON: () => ({ endpoint: sub.endpoint, expirationTime: null, keys: { p256dh: 'p256', auth: 'auth' } }),
      unsubscribe: vi.fn(async () => {
        subscription = null
        return true
      }),
    }
    return sub as unknown as PushSubscription
  }
  if (existingKey) subscription = makeSubscription(existingKey)

  const pushManager = {
    getSubscription: vi.fn(async () => subscription),
    subscribe: vi.fn(async ({ applicationServerKey }: { applicationServerKey: Uint8Array; userVisibleOnly: boolean }) => {
      subscription = makeSubscription(applicationServerKey)
      return subscription
    }),
  }
  const notification = {
    permission,
    requestPermission: vi.fn(async () => {
      notification.permission = answer
      return answer
    }),
  }

  vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('PushManager', class {})
  vi.stubGlobal('Notification', notification)
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(userAgent)
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: { getRegistration: async () => (registered ? { pushManager } : undefined) },
  })
  return { pushManager, notification, current: () => subscription }
}

beforeEach(async () => {
  vi.resetModules()
  mock = await import('@/api/mock')
  push = await import('./push')
  setToken('mock-3')
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  Reflect.deleteProperty(navigator, 'serviceWorker')
  setToken(null)
})

describe('deviceLabel', () => {
  it.each([
    [ANDROID_CHROME, 'Android – Chrome'],
    [IPHONE_SAFARI, 'iPhone – Safari'],
    [
      'Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36',
      'Android – Samsung Internet',
    ],
    [
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0',
      'Windows – Edge',
    ],
    ['Mozilla/5.0 (Android 14; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0', 'Android – Firefox'],
    ['curl/8.0', 'Nieznane urządzenie'],
  ])('names %s', (userAgent, label) => {
    expect(push.deviceLabel(userAgent)).toBe(label)
  })
})

describe('keyToBytes', () => {
  it('turns the base64url server key into 65 bytes of a P-256 key', async () => {
    const bytes = push.keyToBytes(await mock.mockVapidPublicKey('mock-3'))
    expect(bytes).toHaveLength(65)
    // an uncompressed public key starts with 0x04
    expect(bytes[0]).toBe(4)
  })
})

describe('getPushState', () => {
  it('is unsupported without a service worker (npm run dev)', async () => {
    fakeBrowser({ registered: false })
    expect(await push.getPushState()).toBe('unsupported')
  })

  it('is unsupported over plain http', async () => {
    fakeBrowser()
    vi.stubGlobal('isSecureContext', false)
    expect(await push.getPushState()).toBe('unsupported')
  })

  it('knows when notifications are blocked', async () => {
    fakeBrowser({ permission: 'denied' })
    expect(await push.getPushState()).toBe('denied')
  })

  it('is disabled before the forester agrees, and enabled after', async () => {
    fakeBrowser()
    expect(await push.getPushState()).toBe('disabled')
    await push.enablePush()
    expect(await push.getPushState()).toBe('enabled')
  })
})

describe('enablePush', () => {
  it('subscribes with the server key and sends the subscription to the backend', async () => {
    const browser = fakeBrowser()

    expect(await push.enablePush()).toBe('enabled')

    const [{ applicationServerKey, userVisibleOnly }] = browser.pushManager.subscribe.mock.calls[0]
    expect(userVisibleOnly).toBe(true)
    expect(applicationServerKey).toEqual(push.keyToBytes(await mock.mockVapidPublicKey('mock-3')))
    expect(mock.mockPushSubscribers()).toEqual([
      { login: 'blazej', endpoint: 'https://fcm.googleapis.com/fcm/send/phone-1', device_label: 'Android – Chrome' },
    ])
  })

  it('subscribes nothing when the forester says no', async () => {
    const browser = fakeBrowser({ answer: 'denied' })

    expect(await push.enablePush()).toBe('denied')
    expect(browser.pushManager.subscribe).not.toHaveBeenCalled()
    expect(mock.mockPushSubscribers()).toEqual([])
  })

  it('keeps a subscription made with the same key', async () => {
    const key = push.keyToBytes(await mock.mockVapidPublicKey('mock-3'))
    const browser = fakeBrowser({ permission: 'granted', existingKey: key })
    const existing = browser.current()

    await push.enablePush()

    expect(browser.pushManager.subscribe).not.toHaveBeenCalled()
    expect(existing!.unsubscribe).not.toHaveBeenCalled()
    expect(mock.mockPushSubscribers()).toHaveLength(1)
  })

  it('subscribes again when the server key has changed', async () => {
    const browser = fakeBrowser({ permission: 'granted', existingKey: new Uint8Array(65) })
    const old = browser.current()

    await push.enablePush()

    expect(old!.unsubscribe).toHaveBeenCalled()
    expect(browser.pushManager.subscribe).toHaveBeenCalledOnce()
  })

  it('a district manager gets 403 from the backend', async () => {
    fakeBrowser()
    setToken('mock-4')
    await expect(push.enablePush()).rejects.toMatchObject({ status: 403 })
  })
})

describe('disablePush', () => {
  it('removes the subscription from the backend and from the browser', async () => {
    const browser = fakeBrowser()
    await push.enablePush()
    const sub = browser.current()

    // logout clears the token first, so it is passed in
    await push.disablePush('mock-3')

    expect(mock.mockPushSubscribers()).toEqual([])
    expect(sub!.unsubscribe).toHaveBeenCalled()
  })

  it('unsubscribes the browser even when the backend cannot be reached', async () => {
    const browser = fakeBrowser()
    await push.enablePush()
    const sub = browser.current()

    await expect(push.disablePush('wrong-token')).resolves.toBeUndefined()
    expect(sub!.unsubscribe).toHaveBeenCalled()
  })

  it('does nothing without a service worker', async () => {
    fakeBrowser({ registered: false })
    await expect(push.disablePush('mock-3')).resolves.toBeUndefined()
  })
})
