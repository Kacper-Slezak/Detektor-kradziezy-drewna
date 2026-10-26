// UI translations. Texts live in src/locales/<language>.json.
// New language: add a file and register it in resources and LANGUAGES.

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enJson from './locales/en.json'
import pl from './locales/pl.json'

// The type forces en.json to have every key from pl.json
const en: typeof pl = enJson

export const resources = {
  pl: { translation: pl },
  en: { translation: en },
} as const

export type Language = keyof typeof resources
export const LANGUAGES: Language[] = ['pl', 'en']

const LANGUAGE_KEY = 'language'

function savedLanguage(): Language {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY)
    if (saved && saved in resources) return saved as Language
  } catch {
    // no access to localStorage, keep Polish
  }
  return 'pl'
}

export function changeLanguage(lng: Language) {
  try {
    localStorage.setItem(LANGUAGE_KEY, lng)
  } catch {
    // the choice lasts until the page is reloaded
  }
  i18n.changeLanguage(lng)
}

// Keep <html lang> in sync with the chosen language (screen readers, autocorrect)
i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = lng
})

i18n.use(initReactI18next).init({
  resources,
  lng: savedLanguage(),
  fallbackLng: 'pl',
  // React already escapes text against HTML injection
  interpolation: { escapeValue: false },
})

export default i18n
