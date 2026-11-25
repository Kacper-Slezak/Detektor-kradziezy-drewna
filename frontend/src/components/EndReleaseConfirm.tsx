import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell } from 'lucide-react'

import { ApiError } from '@/api/client'
import { endRelease, listReleases } from '@/api/releases'
import type { Sensor } from '@/api/types'
import { Button } from '@/components/ui/button'

// big enough to hit with a thumb in the forest
const BIG = 'h-12 text-base [&_svg]:size-5!'

interface EndReleaseConfirmProps {
  // only what the question needs, so the release list can pass its sensor too
  sensor: Pick<Sensor, 'id' | 'name'>
  // known on the release list; from the map it is looked up
  releaseId?: number
  onEnded: () => void
  onCancel: () => void
}

// "The carrier has left": a second tap ends the muting, so a stray tap does not wake the sensor
// in the middle of loading
export function EndReleaseConfirm({ sensor, releaseId, onEnded, onCancel }: EndReleaseConfirmProps) {
  const { t } = useTranslation()
  const [ending, setEnding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function end() {
    setEnding(true)
    setError(null)
    try {
      // a sensor on the map only knows until when it is muted, not which release did it
      const id = releaseId ?? (await listReleases({ sensor_id: sensor.id, active: true }))[0]?.id
      // none: it has just run out or someone else ended it; either way the sensor watches again
      if (id !== undefined) await endRelease(id)
      onEnded()
    } catch (err) {
      // 409: it ended a moment ago, which is what the forester wanted
      if (err instanceof ApiError && err.status === 409) return onEnded()
      setError(err instanceof ApiError ? err.message : t('errors.network'))
      setEnding(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p>{t('release.endQuestion', { name: sensor.name ?? sensor.id })}</p>
      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
      <div className="grid grid-cols-2 gap-2">
        <Button type="button" variant="outline" className={BIG} disabled={ending} onClick={onCancel}>
          {t('release.cancel')}
        </Button>
        <Button type="button" className={BIG} disabled={ending} onClick={end}>
          <Bell />
          {t(ending ? 'release.ending' : 'release.endConfirm')}
        </Button>
      </div>
    </div>
  )
}
