import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

// The theme is module state read from localStorage on load, so each test loads it fresh
let ThemeSwitcher: typeof import('./ThemeSwitcher').ThemeSwitcher

async function load() {
  vi.resetModules()
  ThemeSwitcher = (await import('./ThemeSwitcher')).ThemeSwitcher
}

// The first import (with the icons) is slow when all test files run at once,
// so do it here, where the time limit is longer than in a single test
beforeAll(async () => {
  await import('./ThemeSwitcher')
})

const isDark = () => document.documentElement.classList.contains('dark')

beforeEach(() => {
  document.documentElement.classList.remove('dark')
})

describe('ThemeSwitcher', () => {
  it('follows the system by default', async () => {
    await load()
    render(<ThemeSwitcher />)
    expect(screen.getByRole('button', { name: 'Jak w systemie' })).toHaveAttribute('aria-pressed', 'true')
    // jsdom has no system preference, so light
    expect(isDark()).toBe(false)
  })

  it('switches to dark and remembers it', async () => {
    await load()
    render(<ThemeSwitcher />)
    await userEvent.click(screen.getByRole('button', { name: 'Ciemny' }))

    expect(isDark()).toBe(true)
    expect(screen.getByRole('button', { name: 'Ciemny' })).toHaveAttribute('aria-pressed', 'true')
    expect(localStorage.getItem('theme')).toBe('dark')
  })

  it('restores the saved theme on the next visit', async () => {
    localStorage.setItem('theme', 'dark')
    await load()
    expect(isDark()).toBe(true)

    render(<ThemeSwitcher />)
    await userEvent.click(screen.getByRole('button', { name: 'Jasny' }))
    expect(isDark()).toBe(false)
    expect(localStorage.getItem('theme')).toBe('light')
  })
})
