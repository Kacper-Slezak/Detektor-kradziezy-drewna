import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getPosition } from './geolocation'

// jsdom has no geolocation, so each test puts in a fake one
function fakeGeolocation(getCurrentPosition: Geolocation['getCurrentPosition']) {
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })
}

// jsdom is not a secure context; the app runs on https or localhost
beforeEach(() => {
  vi.stubGlobal('isSecureContext', true)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('getPosition', () => {
  it('gives the position and its accuracy, asking for the real GPS', async () => {
    const getCurrentPosition = vi.fn<Geolocation['getCurrentPosition']>((ok) =>
      ok({ coords: { latitude: 50.061, longitude: 19.95, accuracy: 8 } } as GeolocationPosition),
    )
    fakeGeolocation(getCurrentPosition)

    await expect(getPosition()).resolves.toEqual({ lat: 50.061, lon: 19.95, accuracy: 8 })
    expect(getCurrentPosition.mock.calls[0][2]).toMatchObject({ enableHighAccuracy: true, maximumAge: 0 })
  })

  it.each([
    [1, 'denied'],
    [2, 'unavailable'],
    [3, 'timeout'],
  ])('turns browser error %i into "%s"', async (code, reason) => {
    fakeGeolocation((_ok, fail) => fail?.({ code } as GeolocationPositionError))
    await expect(getPosition()).rejects.toMatchObject({ reason })
  })

  it('says when the browser has no geolocation', async () => {
    vi.stubGlobal('navigator', {})
    await expect(getPosition()).rejects.toMatchObject({ reason: 'unsupported' })
  })

  it('says when the page is not on https', async () => {
    vi.stubGlobal('isSecureContext', false)
    await expect(getPosition()).rejects.toMatchObject({ reason: 'insecure' })
  })
})
