// Tłumaczenia interfejsu. Teksty są w src/locales/<język>.json.
// Nowy język: dodaj plik i wpisz go do resources i LANGUAGES.

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enJson from './locales/en.json'
import pl from './locales/pl.json'

// Typ wymusza, żeby en.json miał wszystkie klucze z pl.json
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
    // brak dostępu do localStorage, zostaje polski
  }
  return 'pl'
}

export function changeLanguage(lng: Language) {
  try {
    localStorage.setItem(LANGUAGE_KEY, lng)
  } catch {
    // wybór działa do odświeżenia strony
  }
  i18n.changeLanguage(lng)
}

// Atrybut lang na <html> zgodny z wybranym językiem (czytniki ekranu, autokorekta)
i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = lng
})

i18n.use(initReactI18next).init({
  resources,
  lng: savedLanguage(),
  fallbackLng: 'pl',
  // React sam zabezpiecza tekst przed wstrzyknięciem HTML
  interpolation: { escapeValue: false },
})

export default i18n
