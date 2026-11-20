import { useEffect, useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { BellOff } from 'lucide-react'

import { ApiError } from '@/api/client'
import { createRelease } from '@/api/releases'
import type { NewRelease, Release, Sensor } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

// api.md, section 3: the forester picks 1, 2 or 4 h; 4 h is also what the backend takes by default
const DURATIONS = [1, 2, 4] as const
type Hours = (typeof DURATIONS)[number]

// limits of the backend (ReleaseCreate in schemas.py)
const CARRIER_MAX = 100
const LOG_COUNT_MAX = 100_000
const COMMENT_MAX = 500

// big enough to hit with a thumb in the forest
const BIG = 'h-12 text-base [&_svg]:size-5!'

const HOUR_MS = 60 * 60 * 1000

interface ReleaseFormProps {
  sensor: Sensor
  onReleased: (release: Release) => void
}

// The forester hands the timber over to the carrier: the sensor stays quiet for 1-4 h,
// so loading the timber does not raise an alarm
export function ReleaseForm({ sensor, onReleased }: ReleaseFormProps) {
  const { t, i18n } = useTranslation()
  const ids = { carrier: useId(), logs: useId(), comment: useId() }
  const [hours, setHours] = useState<Hours>(4)
  const [carrier, setCarrier] = useState('')
  const [logCount, setLogCount] = useState('')
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // the clock for the end shown under the buttons; it moves on while the form is open,
  // and the real end is counted again when saving
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(timer)
  }, [])
  const until = new Date(now + hours * HOUR_MS).toLocaleTimeString(i18n.language, { timeStyle: 'short' })

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    // empty optional fields are left out, not sent as ""
    const release: NewRelease = { ends_at: new Date(Date.now() + hours * HOUR_MS).toISOString() }
    if (carrier.trim()) release.carrier = carrier.trim()
    if (logCount !== '') release.log_count = Number(logCount)
    if (comment.trim()) release.comment = comment.trim()
    try {
      onReleased(await createRelease(sensor.id, release))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'))
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <p className="font-semibold">{sensor.name ?? sensor.id}</p>

      <div role="group" aria-label={t('release.duration')} className="flex flex-col gap-2">
        <p className="text-sm font-medium">{t('release.duration')}</p>
        <div className="grid grid-cols-3 gap-2">
          {DURATIONS.map((h) => (
            <Button
              key={h}
              type="button"
              variant={hours === h ? 'default' : 'outline'}
              aria-pressed={hours === h}
              className={BIG}
              onClick={() => setHours(h)}
            >
              {t('release.hours', { hours: h })}
            </Button>
          ))}
        </div>
        <p className="text-sm text-muted-foreground tabular-nums">{t('release.until', { time: until })}</p>
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.carrier}>{t('release.carrier')}</Label>
        <Input
          id={ids.carrier}
          value={carrier}
          onChange={(e) => setCarrier(e.target.value)}
          maxLength={CARRIER_MAX}
          className="h-12 text-base md:text-base"
        />
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.logs}>{t('release.logCount')}</Label>
        <Input
          id={ids.logs}
          type="number"
          inputMode="numeric"
          min={0}
          max={LOG_COUNT_MAX}
          step={1}
          value={logCount}
          onChange={(e) => setLogCount(e.target.value)}
          className="h-12 text-base md:text-base"
        />
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.comment}>{t('release.comment')}</Label>
        <textarea
          id={ids.comment}
          rows={2}
          maxLength={COMMENT_MAX}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          className="w-full rounded-lg border border-input bg-transparent px-3 py-2 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        />
      </div>

      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}

      <Button type="submit" className={BIG} disabled={saving}>
        <BellOff />
        {t(saving ? 'release.saving' : 'release.save')}
      </Button>
    </form>
  )
}
