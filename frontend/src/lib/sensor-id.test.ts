import { describe, expect, it } from 'vitest'

import { isValidSensorId, normalizeSensorId } from './sensor-id'

describe('normalizeSensorId', () => {
  it('removes spaces, dashes and colons and uses upper case', () => {
    expect(normalizeSensorId('70b3d57ed0051234')).toBe('70B3D57ED0051234')
    expect(normalizeSensorId(' 70-B3-D5-7E-D0-05-12-34 ')).toBe('70B3D57ED0051234')
    expect(normalizeSensorId('70:b3:d5:7e:d0:05:12:34')).toBe('70B3D57ED0051234')
  })
})

describe('isValidSensorId', () => {
  it('accepts exactly 16 hex characters', () => {
    expect(isValidSensorId('70B3D57ED0051234')).toBe(true)
    expect(isValidSensorId('70B3D57ED005123')).toBe(false)
    expect(isValidSensorId('70B3D57ED00512345')).toBe(false)
    expect(isValidSensorId('70B3D57ED005XYZW')).toBe(false)
  })
})
