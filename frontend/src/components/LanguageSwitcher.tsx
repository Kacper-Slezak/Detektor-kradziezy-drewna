import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { changeLanguage, LANGUAGES } from '@/i18n'

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation()

  return (
    <div role="group" aria-label={t('language.label')} className="flex gap-1">
      {LANGUAGES.map((lng) => (
        <Button
          key={lng}
          size="sm"
          variant={i18n.resolvedLanguage === lng ? 'secondary' : 'ghost'}
          aria-pressed={i18n.resolvedLanguage === lng}
          onClick={() => changeLanguage(lng)}
        >
          {lng.toUpperCase()}
        </Button>
      ))}
    </div>
  )
}
