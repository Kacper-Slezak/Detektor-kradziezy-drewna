import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Search } from 'lucide-react'
import { cn } from 'cn'

import { ApiError } from '@/api/client'
import { listSensors } from '@/api/sensors'
import type { Range, Sensor } from '@/api/types'
import { listRanges } from '@/api/users'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

// State from api.md, plus "unmounted": registered but without a location yet
type Status = Sensor['state'] | 'unmounted'

function statusOf(sensor: Sensor): Status {
  if (sensor.state === 'inactive' && sensor.lat === null) return 'unmounted'
  return sensor.state
}

const STATUS_DOT: Record<Status, string> = {
  ok: 'bg-emerald-500',
  muted: 'bg-sky-500',
  alarm: 'bg-red-500',
  silent: 'bg-amber-500',
  inactive: 'bg-muted-foreground',
  unmounted: 'bg-muted-foreground',
}

const LOW_BATTERY_PCT = 20

// "Sensors" section of the admin panel (AdminLayout gives the frame)
export function SensorsPage() {
  const { t, i18n } = useTranslation()
  const [sensors, setSensors] = useState<Sensor[] | null>(null)
  const [ranges, setRanges] = useState<Range[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    let cancelled = false
    Promise.all([listSensors(), listRanges()])
      .then(([loadedSensors, loadedRanges]) => {
        if (cancelled) return
        setSensors(loadedSensors)
        setRanges(loadedRanges)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : t('errors.network'))
      })
    return () => {
      cancelled = true
    }
  }, [t])

  const rangeName = (id: number | null) => ranges.find((r) => r.id === id)?.name
  const formatDate = (iso: string) =>
    new Date(iso).toLocaleString(i18n.language, { dateStyle: 'short', timeStyle: 'short' })

  const query = search.trim().toLowerCase()
  const shown = (sensors ?? []).filter(
    (s) => !query || s.id.toLowerCase().includes(query) || s.name?.toLowerCase().includes(query),
  )

  const stats = sensors && [
    { label: t('sensors.stats.all'), value: sensors.length },
    { label: t('sensors.stats.alarm'), value: sensors.filter((s) => s.state === 'alarm').length },
    { label: t('sensors.stats.silent'), value: sensors.filter((s) => s.state === 'silent').length },
    { label: t('sensors.stats.unmounted'), value: sensors.filter((s) => statusOf(s) === 'unmounted').length },
  ]

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">{t('sensors.title')}</h1>

      {stats && (
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {stats.map(({ label, value }) => (
            <div key={label} className="flex flex-col-reverse gap-1 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="text-3xl font-semibold tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      <Card className="gap-0 py-0">
        <div className="flex items-center gap-2 border-b p-3">
          <Search className="size-4 shrink-0 text-muted-foreground" />
          <Input
            type="search"
            aria-label={t('sensors.search')}
            placeholder={t('sensors.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
          />
        </div>

        {loadError ? (
          <p role="alert" className="p-4 text-sm text-destructive">
            {loadError}
          </p>
        ) : sensors === null ? (
          <p role="status" className="p-4 text-muted-foreground">
            {t('app.loading')}
          </p>
        ) : (
          // wide table scrolls sideways on phones
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">{t('sensors.table.name')}</th>
                  <th className="px-3 py-2 font-medium">{t('sensors.table.id')}</th>
                  <th className="px-3 py-2 font-medium">{t('sensors.table.range')}</th>
                  <th className="px-3 py-2 font-medium">{t('sensors.table.state')}</th>
                  <th className="px-3 py-2 text-right font-medium">{t('sensors.table.battery')}</th>
                  <th className="px-3 py-2 font-medium">{t('sensors.table.lastSeen')}</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {shown.map((sensor) => {
                  const status = statusOf(sensor)
                  const lowBattery = sensor.battery_pct !== null && sensor.battery_pct < LOW_BATTERY_PCT
                  return (
                    <tr key={sensor.id} className="hover:bg-muted/40">
                      <td className="px-3 py-2 font-medium whitespace-nowrap">
                        {sensor.name ?? <span className="font-normal text-muted-foreground">{t('sensors.noName')}</span>}
                      </td>
                      <td className="px-3 py-2 font-mono whitespace-nowrap">{sensor.id}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{rangeName(sensor.range_id) ?? '—'}</td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className="inline-flex items-center gap-1.5">
                          <span aria-hidden className={cn('size-2 rounded-full', STATUS_DOT[status])} />
                          {t(`sensors.status.${status}`)}
                        </span>
                      </td>
                      <td
                        className={cn(
                          'px-3 py-2 text-right whitespace-nowrap tabular-nums',
                          lowBattery && 'font-medium text-destructive',
                        )}
                      >
                        {sensor.battery_pct === null ? '—' : `${sensor.battery_pct}%`}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {sensor.last_seen ? formatDate(sensor.last_seen) : '—'}
                      </td>
                    </tr>
                  )
                })}
                {shown.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                      {t('sensors.noResults')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
