import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api/client'
import { createSensor } from '@/api/sensors'
import type { Range, Sensor } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SELECT_CLASS } from '@/lib/select'
import { isValidSensorId, normalizeSensorId } from '@/lib/sensor-id'

interface NewSensorFormProps {
  ranges: Range[]
  onCreated: (sensor: Sensor) => void
}

export function NewSensorForm({ ranges, onCreated }: NewSensorFormProps) {
  const { t } = useTranslation()
  const [sensorId, setSensorId] = useState('')
  const [rangeId, setRangeId] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function reset() {
    setSensorId('')
    setRangeId('')
    setName('')
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)

    // Quick check in the browser; the backend does the final validation
    const id = normalizeSensorId(sensorId)
    if (!isValidSensorId(id)) {
      setError(t('sensors.form.errors.invalidId'))
      return
    }
    if (!rangeId) {
      setError(t('sensors.form.errors.rangeRequired'))
      return
    }

    setLoading(true)
    try {
      const created = await createSensor({
        id,
        range_id: Number(rangeId),
        // usually the forester names the sensor when mounting it
        name: name.trim() || null,
      })
      onCreated(created)
      reset()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="sensor-id">{t('sensors.form.id')}</Label>
        <Input
          id="sensor-id"
          value={sensorId}
          onChange={(e) => setSensorId(e.target.value)}
          placeholder="70B3D57ED0051234"
          aria-describedby="sensor-id-hint"
          autoComplete="off"
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
          className="font-mono"
          required
        />
        <p id="sensor-id-hint" className="text-xs text-muted-foreground">
          {t('sensors.form.idHint')}
        </p>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="sensor-range">{t('sensors.form.range')}</Label>
        <select
          id="sensor-range"
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
        <Label htmlFor="sensor-name">{t('sensors.form.name')}</Label>
        <Input
          id="sensor-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          aria-describedby="sensor-name-hint"
          maxLength={100}
        />
        <p id="sensor-name-hint" className="text-xs text-muted-foreground">
          {t('sensors.form.nameHint')}
        </p>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={loading}>
        {loading ? t('sensors.form.submitting') : t('sensors.form.submit')}
      </Button>
    </form>
  )
}
