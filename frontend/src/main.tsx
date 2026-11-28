import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './index.css'
import './i18n'
import App from './App.tsx'
import { watchForUpdates } from './lib/pwa-update'

// Service worker of the installed app. With registerType 'autoUpdate' (vite.config.ts)
// a new version is activated as soon as it is downloaded and the page reloads by itself.
registerSW({
  immediate: true,
  onRegisteredSW(_url, registration) {
    if (registration) watchForUpdates(registration)
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
