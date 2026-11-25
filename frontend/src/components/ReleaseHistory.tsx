import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from 'cn'

import { ApiError } from '@/api/client'
import { listReleases } from '@/api/releases'
import type { Release, ReleaseFilters, Sensor } from '@/api/types'
import { ReleaseCard } from '@/components/ReleaseCard'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { SELECT_CLASS } from '@/lib/select'
import { formatDateTime } from '@/lib/sensor-status'

// how many finished releases come at once; "Show older" brings the next ones
export const HISTORY_PAGE = 50

// quick periods instead of two date fields: easier with a thumb in the forest
type Period = 7 | 30 | 365 | 'all'
const PERIODS: Period[] = [7, 30, 365, 'all']
const DAY_MS = 24 * 60 * 60 * 1000

// what goes to the backend for the chosen filters; "from" is counted when the filter is picked
function queryFor(sensorId: string, period: Period): ReleaseFilters {
  const query: ReleaseFilters = {}
  if (sensorId) query.sensor_id = sensorId
  if (period !== 'all') query.from = new Date(Date.now() - period * DAY_MS).toISOString()
  return query
}

// "14.10.2026, 08:00 – 11:20", or with both dates when it went past midnight
function timeSpan(release: Release, language: string): string {
  const start = new Date(release.starts_at)
  const end = new Date(release.ends_at)
  const to =
    start.toDateString() === end.toDateString()
      ? end.toLocaleTimeString(language, { timeStyle: 'short' })
      : formatDateTime(release.ends_at, language)
  return `${formatDateTime(release.starts_at, language)} – ${to}`
}

interface ReleaseHistoryProps {
  // the sensors the user may see (the forester's range), for the sensor filter
  sensors: Sensor[]
}

// Finished timber releases, newest first: a record for the reports and for disputes with a carrier
export function ReleaseHistory({ sensors }: ReleaseHistoryProps) {
  const { t, i18n } = useTranslation()
  const sensorFieldId = useId()
  const [sensorId, setSensorId] = useState('')
  const [period, setPeriod] = useState<Period>(30)
  const [query, setQuery] = useState<ReleaseFilters>(() => queryFor('', 30))
  // the filters of the list on screen: an older page asked for under other filters must not be
  // added to it when the forester changed the filters while it was loading
  const shownQuery = useRef(query)
  const [releases, setReleases] = useState<Release[] | null>(null)
  // whether the backend has more than what is shown
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // the history does not change by itself, so it is loaded once per filter, not every 20 s
  useEffect(() => {
    let cancelled = false
    // one more than a page is asked for: if it comes, there is something older to show
    listReleases({ ...query, active: false, limit: HISTORY_PAGE + 1 })
      .then((page) => {
        if (cancelled) return
        setHasMore(page.length > HISTORY_PAGE)
        setReleases(page.slice(0, HISTORY_PAGE))
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : t('errors.network'))
      })
    return () => {
      cancelled = true
    }
  }, [query, t])

  function changeFilters(nextSensorId: string, nextPeriod: Period) {
    const next = queryFor(nextSensorId, nextPeriod)
    shownQuery.current = next
    setSensorId(nextSensorId)
    setPeriod(nextPeriod)
    setReleases(null)
    setHasMore(false)
    setLoadingMore(false)
    setError(null)
    setQuery(next)
  }

  const sensorOptions = [...sensors].sort((a, b) => (a.name ?? a.id).localeCompare(b.name ?? b.id, i18n.language))
  const filtered = sensorId !== '' || period !== 'all'

  async function showOlder() {
    const asked = query
    // the answer is for the list on screen only while its filters stay the same
    const stillShown = () => shownQuery.current === asked
    setLoadingMore(true)
    setError(null)
    try {
      const page = await listReleases({
        ...asked,
        active: false,
        limit: HISTORY_PAGE + 1,
        offset: releases?.length ?? 0,
      })
      if (!stillShown()) return
      setHasMore(page.length > HISTORY_PAGE)
      setReleases((current) => [...(current ?? []), ...page.slice(0, HISTORY_PAGE)])
    } catch (err) {
      if (stillShown()) setError(err instanceof ApiError ? err.message : t('errors.network'))
    } finally {
      if (stillShown()) setLoadingMore(false)
    }
  }

  return (
    <>
      <div className="flex flex-col gap-2">
        <Label htmlFor={sensorFieldId}>{t('releases.filters.sensor')}</Label>
        <select
          id={sensorFieldId}
          className={cn(SELECT_CLASS, 'h-12 md:text-base')}
          value={sensorId}
          onChange={(e) => changeFilters(e.target.value, period)}
        >
          <option value="">{t('releases.filters.allSensors')}</option>
          {sensorOptions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name ?? s.id}
            </option>
          ))}
        </select>
      </div>

      <div role="group" aria-label={t('releases.filters.period')} className="grid grid-cols-4 gap-1 rounded-xl bg-muted p-1">
        {PERIODS.map((p) => (
          <Button
            key={p}
            variant="ghost"
            aria-pressed={p === period}
            className="h-10 px-1 text-sm aria-pressed:bg-background aria-pressed:font-semibold aria-pressed:shadow-sm sm:text-base"
            onClick={() => p !== period && changeFilters(sensorId, p)}
          >
            {t(`releases.filters.periods.${p}`)}
          </Button>
        ))}
      </div>

      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}

      {releases === null ? (
        !error && (
          <p role="status" className="text-muted-foreground">
            {t('app.loading')}
          </p>
        )
      ) : releases.length === 0 ? (
        <p className="py-6 text-center text-muted-foreground">{t(filtered ? 'releases.noHistoryFiltered' : 'releases.noHistory')}</p>
      ) : (
        <ul aria-label={t('releases.history')} className="flex flex-col gap-3">
          {releases.map((release) => (
            <ReleaseCard
              key={release.id}
              release={release}
              when={timeSpan(release, i18n.language)}
              who={release.created_by ?? ''}
            />
          ))}
        </ul>
      )}

      {hasMore && (
        <Button variant="outline" className="h-12 text-base" disabled={loadingMore} onClick={showOlder}>
          {t(loadingMore ? 'releases.loadingMore' : 'releases.more')}
        </Button>
      )}
    </>
  )
}
