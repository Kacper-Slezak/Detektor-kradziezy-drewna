import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash2 } from 'lucide-react'

import { ApiError } from '@/api/client'
import { deleteSensor, updateSensor } from '@/api/sensors'
import type { Range, Sensor } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SELECT_CLASS } from '@/lib/select'

interface EditSensorFormProps {
  sensor: Sensor
  ranges: Range[]
  onSaved: (sensor: Sensor) => void
  onDeleted: (id: string) => void
  // a sensor with history cannot be deleted; switching it off is offered instead
  onSwitchedOff: (sensor: Sensor) => void
}

export function EditSensorForm({ sensor, ranges, onSaved, onDeleted, onSwitchedOff }: EditSensorFormProps) {
  const { t } = useTranslation()
  const [rangeId, setRangeId] = useState(sensor.range_id === null ? '' : String(sensor.range_id))
  const [name, setName] = useState(sensor.name ?? '')
  const [active, setActive] = useState(sensor.active)
  // not mounted yet: mounting switches it on, and without a location it would stay inactive anyway
  const mounted = sensor.lat !== null
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  // deleting is asked about once more: it cannot be undone
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  // 409 from the backend: alarms and releases are records, so the sensor stays
  const [hasHistory, setHasHistory] = useState(false)

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
        // only when it changed, so saving a new name does not touch it
        ...(active !== sensor.active && { active }),
      })
      onSaved(saved)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'))
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete() {
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteSensor(sensor.id)
      onDeleted(sensor.id)
    } catch (err) {
      // not an error to show in red: most sensors have history; the backend text is for API users
      if (err instanceof ApiError && err.status === 409) setHasHistory(true)
      else setDeleteError(err instanceof ApiError ? err.message : t('errors.network'))
      setDeleting(false)
    }
  }

  async function switchOff() {
    setDeleting(true)
    setDeleteError(null)
    try {
      onSwitchedOff(await updateSensor(sensor.id, { active: false }))
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : t('errors.network'))
      setDeleting(false)
    }
  }

  function cancelDelete() {
    setConfirmingDelete(false)
    setHasHistory(false)
    setDeleteError(null)
  }

  return (
    <div className="flex flex-col gap-6">
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
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <input
              id="edit-sensor-active"
              type="checkbox"
              className="size-4 accent-primary"
              checked={active}
              disabled={!mounted}
              onChange={(e) => setActive(e.target.checked)}
            />
            <Label htmlFor="edit-sensor-active">{t('sensors.edit.active')}</Label>
          </div>
          <p className="text-xs text-muted-foreground">
            {t(mounted ? 'sensors.edit.activeHint' : 'sensors.edit.activeUnmounted')}
          </p>
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

      {/* apart from the form and only behind a second question: deleting cannot be undone */}
      <section aria-label={t('sensors.delete.section')} className="flex flex-col gap-3 border-t pt-4">
        {hasHistory ? (
          <>
            <div role="status" className="flex flex-col gap-1 rounded-lg bg-muted p-3 text-sm">
              <p className="font-medium">{t('sensors.delete.hasHistory')}</p>
              <p>{t(sensor.active ? 'sensors.delete.switchOffHint' : 'sensors.delete.alreadyOff')}</p>
            </div>
            {deleteError && (
              <p role="alert" className="text-sm text-destructive">
                {deleteError}
              </p>
            )}
            {sensor.active ? (
              <div className="grid grid-cols-2 gap-2">
                <Button type="button" variant="outline" disabled={deleting} onClick={cancelDelete}>
                  {t('sensors.delete.cancel')}
                </Button>
                <Button type="button" disabled={deleting} onClick={switchOff}>
                  {t(deleting ? 'sensors.delete.switchingOff' : 'sensors.delete.switchOff')}
                </Button>
              </div>
            ) : (
              <Button type="button" variant="outline" onClick={cancelDelete}>
                {t('sensors.delete.ok')}
              </Button>
            )}
          </>
        ) : confirmingDelete ? (
          <>
            <p className="text-sm">
              <span className="font-medium">{t('sensors.delete.question', { id: sensor.id })}</span>{' '}
              {t('sensors.delete.cannotUndo')}
            </p>
            {deleteError && (
              <p role="alert" className="text-sm text-destructive">
                {deleteError}
              </p>
            )}
            <div className="grid grid-cols-2 gap-2">
              <Button type="button" variant="outline" disabled={deleting} onClick={cancelDelete}>
                {t('sensors.delete.cancel')}
              </Button>
              <Button type="button" variant="destructive" disabled={deleting} onClick={handleDelete}>
                {t(deleting ? 'sensors.delete.deleting' : 'sensors.delete.confirm')}
              </Button>
            </div>
          </>
        ) : (
          <>
            <Button
              type="button"
              variant="outline"
              className="text-destructive"
              onClick={() => setConfirmingDelete(true)}
            >
              <Trash2 />
              {t('sensors.delete.open')}
            </Button>
            <p className="text-xs text-muted-foreground">{t('sensors.delete.hint')}</p>
          </>
        )}
      </section>
    </div>
  )
}
