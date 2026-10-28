// Light / dark / system theme for the whole app.
// Dark colours are the .dark block in index.css; this file only toggles the class on <html>.
// index.html applies the saved theme before React loads, so the page does not flash white.

import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark' | 'system'
export const THEMES: Theme[] = ['light', 'dark', 'system']

const THEME_KEY = 'theme'

// matchMedia is missing in some environments (e.g. tests)
const systemDark = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-color-scheme: dark)') : null

function savedTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // no access to localStorage, follow the system
  }
  return 'system'
}

let theme = savedTheme()
const listeners = new Set<() => void>()

function apply() {
  const dark = theme === 'dark' || (theme === 'system' && (systemDark?.matches ?? false))
  document.documentElement.classList.toggle('dark', dark)
}

apply()
// with "system", follow the phone or computer when it switches (e.g. at sunset)
systemDark?.addEventListener('change', apply)

export function setTheme(next: Theme) {
  theme = next
  try {
    if (next === 'system') localStorage.removeItem(THEME_KEY)
    else localStorage.setItem(THEME_KEY, next)
  } catch {
    // the choice lasts until the page is reloaded
  }
  apply()
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, () => theme)
}
