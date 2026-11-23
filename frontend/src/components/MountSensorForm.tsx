import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { LocateFixed } from 'lucide-react'
import { cn } from 'cn'

import { ApiError } from '@/api/client'
import { mountSensor } from '@/api/sensors'
import type { Sensor } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { getPosition, PositionFailure, type Position } from '@/lib/geolocation'
import { SELECT_CLASS } from '@/lib/select'

// big enough to hit with a thumb in the forest
const BIG = 'h-12 text-base [&_svg]:size-5!'

// worse than this the pin may land on the wrong stack, so we warn (saving is still allowed)
const POOR_ACCURACY_M = 50

interface MountSensorFormProps {
  // sensors of the forester's range without a location yet (or the one being moved)
  sensors: Sensor[]
  onMounted: (sensor: Sensor) => void
  // moving one sensor that is already mounted: the new location overwrites the old one
  moving?: boolean
}

// The forester stands by the timber stack, picks the sensor, names it and takes the phone's location
export function MountSensorForm({ sensors, onMounted, moving = false }: MountSensorFormProps) {
  const { t } = useTranslation()
  const ids = { sensor: useId(), name: useId(), hint: useId() }
  // with a single sensor to mount there is nothing to choose
  const [sensorId, setSensorId] = useState(sensors.length === 1 ? sensors[0].id : '')
  const [name, setName] = useState(sensors.length === 1 ? (sensors[0].name ?? '') : '')
  const [position, setPosition] = useState<Position | null>(null)
  const [locating, setLocating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // where the sensor stands now, so the forester sees what gets overwritten
  const current = moving ? sensors.find((s) => s.id === sensorId) : undefined

  function chooseSensor(id: string) {
    setSensorId(id)
    // the admin may have named it already
    setName(sensors.find((s) => s.id === id)?.name ?? '')
  }

  async function locate() {
    setLocating(true)
    setError(null)
    try {
      setPosition(await getPosition())
    } catch (err) {
      setError(t(`mount.errors.${err instanceof PositionFailure ? err.reason : 'unavailable'}`))
    } finally {
      setLocating(false)
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!sensorId || !name.trim() || !position) return
    setSaving(true)
    setError(null)
    try {
      onMounted(await mountSensor(sensorId, { name: name.trim(), lat: position.lat, lon: position.lon }))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'))
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.sensor}>{t('mount.sensor')}</Label>
        <select
          id={ids.sensor}
          className={cn(SELECT_CLASS, 'h-12 font-mono text-base md:text-base')}
          value={sensorId}
          onChange={(e) => chooseSensor(e.target.value)}
          required
        >
          {sensors.length > 1 && <option value="">–</option>}
          {sensors.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name ? `${s.name} (${s.id})` : s.id}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.name}>{t('mount.name')}</Label>
        <Input
          id={ids.name}
          value={name}
          onChange={(e) => setName(e.target.value)}
          aria-describedby={ids.hint}
          maxLength={100}
          className="h-12 text-base md:text-base"
          required
        />
        <p id={ids.hint} className="text-xs text-muted-foreground">
          {t('mount.nameHint')}
        </p>
      </div>

      <div role="group" aria-label={t('mount.location')} className="flex flex-col gap-2">
        <p className="text-sm font-medium">{t('mount.location')}</p>
        {current?.lat != null && current.lon != null && (
          <p className="text-sm text-muted-foreground tabular-nums">
            {t('mount.current', { lat: current.lat.toFixed(5), lon: current.lon.toFixed(5) })}
          </p>
        )}
        {position && (
          <p className="tabular-nums">
            {position.lat.toFixed(5)}, {position.lon.toFixed(5)}
            {' · '}
            {t('mount.accuracy', { meters: Math.round(position.accuracy) })}
          </p>
        )}
        {position && position.accuracy > POOR_ACCURACY_M && (
          <p className="rounded-lg bg-amber-500/10 p-2 text-sm font-medium text-amber-800 dark:text-amber-300">
            {t('mount.poorAccuracy')}
          </p>
        )}
        <Button type="button" variant="outline" className={BIG} disabled={locating || saving} onClick={locate}>
          <LocateFixed />
          {t(locating ? 'mount.locating' : position ? 'mount.relocate' : 'mount.locate')}
        </Button>
      </div>

      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}

      <Button type="submit" className={BIG} disabled={saving || locating || !sensorId || !name.trim() || !position}>
        {t(saving ? 'mount.saving' : moving ? 'mount.saveMove' : 'mount.save')}
      </Button>
    </form>
  )
}
