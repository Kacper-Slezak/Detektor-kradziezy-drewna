// Phone location for mounting a sensor (navigator.geolocation).
// Browsers only give it on https or localhost, and only after the user allows it.

export interface Position {
  lat: number
  lon: number
  // radius in metres within which the real position is, e.g. 8 = "±8 m"
  accuracy: number
}

// The form translates these into a message
export type PositionError = 'unsupported' | 'insecure' | 'denied' | 'unavailable' | 'timeout'

export class PositionFailure extends Error {
  readonly reason: PositionError

  constructor(reason: PositionError) {
    super(reason)
    this.name = 'PositionFailure'
    this.reason = reason
  }
}

// GeolocationPositionError.code: 1 permission denied, 2 position unavailable, 3 timeout
const REASONS: Record<number, PositionError> = { 1: 'denied', 2: 'unavailable', 3: 'timeout' }

export function getPosition(): Promise<Position> {
  return new Promise((resolve, reject) => {
    // on plain http (e.g. a phone opening the laptop by its IP) the browser blocks it
    if (!window.isSecureContext) return reject(new PositionFailure('insecure'))
    if (!('geolocation' in navigator)) return reject(new PositionFailure('unsupported'))

    navigator.geolocation.getCurrentPosition(
      ({ coords }) => resolve({ lat: coords.latitude, lon: coords.longitude, accuracy: coords.accuracy }),
      (err) => reject(new PositionFailure(REASONS[err.code] ?? 'unavailable')),
      // the real GPS, not a guess from Wi-Fi; in a forest the fix can take a while
      { enableHighAccuracy: true, timeout: 20_000, maximumAge: 0 },
    )
  })
}
