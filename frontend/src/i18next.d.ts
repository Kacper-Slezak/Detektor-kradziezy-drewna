// Lets TypeScript know the keys from pl.json and report typos in t('...')

import 'i18next'

import type { resources } from './i18n'

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation'
    resources: (typeof resources)['pl']
  }
}
