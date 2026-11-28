import { describe, expect, it } from 'vitest'

import { loginFromName } from './login'

describe('loginFromName', () => {
  it('joins first and last name with a dot', () => {
    expect(loginFromName('Anna Las')).toBe('anna.las')
  })

  it('replaces Polish letters', () => {
    expect(loginFromName('Błażej Kowalski')).toBe('blazej.kowalski')
    expect(loginFromName('Łucja Źdźbło-Ćwik')).toBe('lucja.zdzblo-cwik')
  })

  it('ignores extra spaces and other characters', () => {
    expect(loginFromName('  Jan   Maria  Nowak ')).toBe('jan.maria.nowak')
    expect(loginFromName("Jan O'Brien")).toBe('jan.obrien')
  })

  it('is empty for an empty name', () => {
    expect(loginFromName('   ')).toBe('')
  })
})
