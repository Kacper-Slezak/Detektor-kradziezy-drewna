// "Install app" on Android (Chrome, Edge, Samsung Internet).
// The browser fires beforeinstallprompt when the app can be installed. It can happen
// before React renders, so we listen as soon as this module loads and keep the event.
// Once the app is installed and opened from the home screen, the event never fires.

import { useSyncExternalStore } from 'react'

// Not in TypeScript's DOM types yet (Chromium-only API)
interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

let deferredPrompt: BeforeInstallPromptEvent | null = null
const listeners = new Set<() => void>()

function setDeferredPrompt(event: BeforeInstallPromptEvent | null) {
  deferredPrompt = event
  listeners.forEach((listener) => listener())
}

window.addEventListener('beforeinstallprompt', (event) => {
  // Skip Chrome's own install banner; our button shows the dialog instead
  event.preventDefault()
  setDeferredPrompt(event as BeforeInstallPromptEvent)
})

window.addEventListener('appinstalled', () => setDeferredPrompt(null))

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function useInstallPrompt() {
  const prompt = useSyncExternalStore(subscribe, () => deferredPrompt)

  async function install() {
    if (!prompt) return
    // Each event can show the dialog only once; Chrome sends a new one if the user declines
    setDeferredPrompt(null)
    await prompt.prompt()
  }

  return { canInstall: prompt !== null, install }
}
