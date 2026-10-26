// Dzięki temu TypeScript zna klucze z pl.json i zgłosi literówkę w t('...')

import 'i18next'

import type { resources } from './i18n'

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation'
    resources: (typeof resources)['pl']
  }
}
