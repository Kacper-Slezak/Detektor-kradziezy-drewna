import { describe, expect, it } from 'vitest'

import { generateTempPassword } from './password'

describe('generateTempPassword', () => {
  it('has three groups of four readable characters', () => {
    expect(generateTempPassword()).toMatch(/^[a-km-zA-HJ-NP-Z2-9]{4}-[a-km-zA-HJ-NP-Z2-9]{4}-[a-km-zA-HJ-NP-Z2-9]{4}$/)
  })

  it('is long enough for the backend (at least 8 characters)', () => {
    expect(generateTempPassword().length).toBeGreaterThanOrEqual(8)
  })

  it('is different every time', () => {
    const passwords = new Set(Array.from({ length: 20 }, generateTempPassword))
    expect(passwords.size).toBe(20)
  })
})
