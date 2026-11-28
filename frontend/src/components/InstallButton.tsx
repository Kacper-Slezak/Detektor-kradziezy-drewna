import { Download } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { useInstallPrompt } from '@/lib/install-prompt'

export function InstallButton() {
  const { t } = useTranslation()
  const { canInstall, install } = useInstallPrompt()

  if (!canInstall) return null

  return (
    <Button size="sm" onClick={install}>
      <Download />
      {t('install.button')}
    </Button>
  )
}
