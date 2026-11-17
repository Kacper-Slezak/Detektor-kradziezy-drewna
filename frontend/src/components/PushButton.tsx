import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell, BellOff, BellRing } from 'lucide-react'

import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { enablePush, getPushState, type PushState } from '@/lib/push'

// Alarm notifications in the forester's menu (api.md, section 6: pushes are only for foresters)
export function PushButton() {
  const { t } = useTranslation()
  const [state, setState] = useState<PushState | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getPushState().then(
      (current) => {
        if (cancelled) return
        setState(current)
        // already on: send it again quietly (no question, permission is granted),
        // so the backend knows this phone belongs to whoever is signed in now
        if (current === 'enabled') enablePush().catch(() => {})
      },
      () => !cancelled && setState('unsupported'),
    )
    return () => {
      cancelled = true
    }
  }, [])

  // the permission question must come from a click, browsers ignore it otherwise
  async function enable() {
    setBusy(true)
    setError(null)
    try {
      setState(await enablePush())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('push.error'))
    } finally {
      setBusy(false)
    }
  }

  if (state === null) return null

  if (state === 'enabled') {
    return (
      <p role="status" className="flex items-center gap-2 px-3 py-2 text-sm">
        <BellRing className="size-4 shrink-0" />
        {t('push.enabled')}
      </p>
    )
  }

  if (state === 'unsupported' || state === 'denied') {
    return (
      <p className="flex items-start gap-2 px-3 py-2 text-sm text-muted-foreground">
        <BellOff className="mt-0.5 size-4 shrink-0" />
        {t(`push.${state}`)}
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-1">
      <Button variant="ghost" className="justify-start" onClick={enable} disabled={busy}>
        <Bell />
        {busy ? t('push.enabling') : t('push.enable')}
      </Button>
      {error && (
        <p role="alert" className="px-3 text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
