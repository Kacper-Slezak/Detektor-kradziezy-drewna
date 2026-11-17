import { describe, expect, it, vi } from 'vitest'

// public/sw-push.js runs in the service worker, so here its text runs with a fake `self`
import code from '../../public/sw-push.js?raw'

type Handler = (event: unknown) => void

function loadWorker({ windows = [] as unknown[] } = {}) {
  const handlers: Record<string, Handler> = {}
  const self = {
    addEventListener: (type: string, handler: Handler) => {
      handlers[type] = handler
    },
    registration: { showNotification: vi.fn(async () => {}) },
    clients: {
      matchAll: vi.fn(async () => windows),
      openWindow: vi.fn(async () => null),
    },
  }
  new Function('self', code)(self)

  // events keep their work in waitUntil; return it so the test can wait for it
  function fire(type: string, event: object) {
    let work: Promise<unknown> = Promise.resolve()
    handlers[type]({ ...event, waitUntil: (p: Promise<unknown>) => (work = p) })
    return work
  }
  return { self, fire }
}

const pushOf = (data: unknown) => ({
  data: {
    json: () => (typeof data === 'string' ? JSON.parse(data) : data),
    text: () => String(data),
  },
})

const ALARM = {
  type: 'alarm',
  alarm_id: 41,
  sensor_id: '70B3D57ED0051234',
  title: 'Alarm: Skład przy drodze 5',
  body: 'Możliwe podbieranie drewna, pewność 87%',
  url: '/alarms/41',
}

describe('push', () => {
  it('shows the alarm from the backend', async () => {
    const { self, fire } = loadWorker()
    await fire('push', pushOf(ALARM))

    expect(self.registration.showNotification).toHaveBeenCalledWith(
      'Alarm: Skład przy drodze 5',
      expect.objectContaining({
        body: 'Możliwe podbieranie drewna, pewność 87%',
        tag: 'alarm-41',
        renotify: true,
        data: { url: '/alarms/41' },
      }),
    )
  })

  it('shows plain text too (a test push from DevTools)', async () => {
    const { self, fire } = loadWorker()
    await fire('push', pushOf('Test'))

    expect(self.registration.showNotification).toHaveBeenCalledWith(
      'Detektor kradzieży drewna',
      expect.objectContaining({ body: 'Test', tag: undefined, data: { url: '/' } }),
    )
  })

  it.each(['https://example.com/', '//example.com/alarms/41', 'javascript:alert(1)'])(
    'does not let a push open another site: %s',
    async (url) => {
      const { self, fire } = loadWorker()
      await fire('push', pushOf({ ...ALARM, url }))
      expect(self.registration.showNotification).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ data: { url: '/' } }),
      )
    },
  )
})

describe('notificationclick', () => {
  const click = () => {
    const notification = { close: vi.fn(), data: { url: '/alarms/41' } }
    return { notification }
  }

  it('opens the alarm in a new window when the app is closed', async () => {
    const { self, fire } = loadWorker()
    const event = click()
    await fire('notificationclick', event)

    expect(event.notification.close).toHaveBeenCalled()
    expect(self.clients.openWindow).toHaveBeenCalledWith('/alarms/41')
  })

  it('shows the alarm in the open app instead of opening a second window', async () => {
    const focus = vi.fn()
    const app = { navigate: vi.fn(async () => ({ focus })), focus: vi.fn() }
    const { self, fire } = loadWorker({ windows: [app] })
    await fire('notificationclick', click())

    expect(app.navigate).toHaveBeenCalledWith('/alarms/41')
    expect(focus).toHaveBeenCalled()
    expect(self.clients.openWindow).not.toHaveBeenCalled()
  })

  it('still brings the app to the front when it cannot move to the alarm', async () => {
    const app = { navigate: vi.fn(async () => Promise.reject(new TypeError('not allowed'))), focus: vi.fn() }
    const { fire } = loadWorker({ windows: [app] })
    await fire('notificationclick', click())

    expect(app.focus).toHaveBeenCalled()
  })
})
