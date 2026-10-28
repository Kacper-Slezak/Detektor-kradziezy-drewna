import { Monitor, Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { setTheme, THEMES, useTheme, type Theme } from '@/lib/theme'

const ICONS: Record<Theme, typeof Sun> = { light: Sun, dark: Moon, system: Monitor }

export function ThemeSwitcher() {
  const { t } = useTranslation()
  const theme = useTheme()

  return (
    <div role="group" aria-label={t('theme.label')} className="flex gap-1">
      {THEMES.map((option) => {
        const Icon = ICONS[option]
        return (
          <Button
            key={option}
            size="icon-sm"
            variant={theme === option ? 'secondary' : 'ghost'}
            aria-pressed={theme === option}
            aria-label={t(`theme.${option}`)}
            title={t(`theme.${option}`)}
            onClick={() => setTheme(option)}
          >
            <Icon />
          </Button>
        )
      })}
    </div>
  )
}
