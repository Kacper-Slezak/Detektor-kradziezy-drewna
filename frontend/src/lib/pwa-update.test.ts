import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { watchForUpdates } from './pwa-update'

function fakeRegistration() {
  return { update: vi.fn().mockResolvedValue(undefined) } as unknown as ServiceWorkerRegistration & {
    update: ReturnType<typeof vi.fn>
  }
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

function setOnline(online: boolean) {
  Object.defineProperty(navigator, 'onLine', { value: online, configurable: true })
}

beforeEach(() => {
  vi.useFakeTimers()
  setOnline(true)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('watchForUpdates', () => {
  it('checks when the app comes back from the background', () => {
    const registration = fakeRegistration()
    watchForUpdates(registration)

    setVisibility('hidden')
    expect(registration.update).not.toHaveBeenCalled()

    setVisibility('visible')
    expect(registration.update).toHaveBeenCalledOnce()
  })

  it('checks every hour while the app stays open', () => {
    const registration = fakeRegistration()
    watchForUpdates(registration)

    vi.advanceTimersByTime(59 * 60 * 1000)
    expect(registration.update).not.toHaveBeenCalled()
    vi.advanceTimersByTime(60 * 1000)
    expect(registration.update).toHaveBeenCalledOnce()
  })

  it('does not check offline', () => {
    const registration = fakeRegistration()
    watchForUpdates(registration)

    setOnline(false)
    setVisibility('visible')
    expect(registration.update).not.toHaveBeenCalled()
  })

  it('ignores a failed check', async () => {
    const registration = fakeRegistration()
    registration.update.mockRejectedValue(new Error('offline'))
    watchForUpdates(registration)

    setVisibility('visible')
    // the rejection is caught, so the test does not fail with an unhandled error
    await vi.runAllTicks()
    expect(registration.update).toHaveBeenCalledOnce()
  })
})
