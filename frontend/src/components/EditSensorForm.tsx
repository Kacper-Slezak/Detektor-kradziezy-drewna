import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api/client'
import { updateSensor } from '@/api/sensors'
import type { Range, Sensor } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SELECT_CLASS } from '@/lib/select'

interface EditSensorFormProps {
  sensor: Sensor
  ranges: Range[]
  onSaved: (sensor: Sensor) => void
}

export function EditSensorForm({ sensor, ranges, onSaved }: EditSensorFormProps) {
  const { t } = useTranslation()
  const [rangeId, setRangeId] = useState(sensor.range_id === null ? '' : String(sensor.range_id))
  const [name, setName] = useState(sensor.name ?? '')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)

    if (!rangeId) {
      setError(t('sensors.form.errors.rangeRequired'))
      return
    }

    setLoading(true)
    try {
      const saved = await updateSensor(sensor.id, {
        range_id: Number(rangeId),
        name: name.trim() || null,
      })
      onSaved(saved)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {/* the ID comes from the device and never changes, so it is plain text, not a field */}
      <dl className="flex flex-col gap-1">
        <dt className="text-sm font-medium">{t('sensors.form.id')}</dt>
        <dd className="font-mono">{sensor.id}</dd>
      </dl>
      <div className="flex flex-col gap-2">
        <Label htmlFor="edit-sensor-range">{t('sensors.form.range')}</Label>
        <select
          id="edit-sensor-range"
          className={SELECT_CLASS}
          value={rangeId}
          onChange={(e) => setRangeId(e.target.value)}
        >
          <option value="">{t('sensors.form.chooseRange')}</option>
          {ranges.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="edit-sensor-name">{t('sensors.form.name')}</Label>
        <Input
          id="edit-sensor-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={100}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={loading}>
        {loading ? t('sensors.edit.saving') : t('sensors.edit.save')}
      </Button>
    </form>
  )
}
