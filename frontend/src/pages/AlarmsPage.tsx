import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity, Clock, TriangleAlert } from 'lucide-react'
import { cn } from 'cn'

import { listAlarms } from '@/api/alarms'
import { ApiError } from '@/api/client'
import type { Alarm, AlarmStatus } from '@/api/types'
import { AlarmAnswerForm } from '@/components/AlarmAnswerForm'
import { Button } from '@/components/ui/button'
import { REFRESH_MS } from '@/lib/refresh'
import { formatDateTime } from '@/lib/sensor-status'

type Filter = AlarmStatus | 'all'

// new alarms first: they wait for the forester
const FILTERS: Filter[] = ['new', 'theft', 'false_alarm', 'all']

const STATUS_BADGE: Record<AlarmStatus, string> = {
  new: 'bg-red-600 text-white',
  theft: 'bg-destructive/10 text-destructive',
  false_alarm: 'bg-muted text-muted-foreground',
}

interface AlarmsPageProps {
  // api.md: the forester answers, the district manager only reads
  canRespond: boolean
  // after an answer (ours or someone else's, found out by 409): the sensor is no longer in alarm, so the map should refresh
  onAnswered?: () => void
}

// Alarm list of a forester and a district manager, newest first
export function AlarmsPage({ canRespond, onAnswered }: AlarmsPageProps) {
  const { t, i18n } = useTranslation()
  const [filter, setFilter] = useState<Filter>('new')
  const [alarms, setAlarms] = useState<Alarm[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // bumping it loads the list again (e.g. after someone else answered first)
  const [reloadKey, setReloadKey] = useState(0)
  const [answered, setAnswered] = useState<Alarm | null>(null)
  // "already answered" from the backend; stays after the list reloads
  const [conflict, setConflict] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    function load() {
      listAlarms(filter === 'all' ? {} : { status: filter })
        .then((loaded) => {
          if (cancelled) return
          setAlarms(loaded)
          setError(null)
        })
        .catch((err) => {
          // a failed refresh keeps the last list
          if (!cancelled) setError(err instanceof ApiError ? err.message : t('errors.network'))
        })
    }
    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [filter, reloadKey, t])

  function changeFilter(next: Filter) {
    if (next === filter) return
    setAlarms(null)
    setError(null)
    setAnswered(null)
    setConflict(null)
    setFilter(next)
  }

  function handleConflict(message: string) {
    setAnswered(null)
    setConflict(message)
    setReloadKey((k) => k + 1)
    // the alarm is closed anyway, so the map should not wait for its next refresh
    onAnswered?.()
  }

  function handleAnswered(alarm: Alarm) {
    setConflict(null)
    // under "new" the answered alarm leaves the list, elsewhere it shows its new status
    setAlarms((current) =>
      (current ?? []).flatMap((a) => (a.id !== alarm.id ? [a] : filter === 'new' ? [] : [alarm])),
    )
    setAnswered(alarm)
    onAnswered?.()
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-2xl flex-col gap-3 p-3">
        {/* full-width segmented control: big targets for a thumb */}
        <div role="group" aria-label={t('alarms.filter')} className="grid grid-cols-4 gap-1 rounded-xl bg-muted p-1">
          {FILTERS.map((f) => (
            <Button
              key={f}
              variant="ghost"
              aria-pressed={f === filter}
              className="h-10 px-1 text-sm aria-pressed:bg-background aria-pressed:font-semibold aria-pressed:shadow-sm sm:text-base"
              onClick={() => changeFilter(f)}
            >
              {t(`alarms.filters.${f}`)}
            </Button>
          ))}
        </div>

        {answered && (
          <div role="status" className="flex items-center justify-between gap-2 rounded-xl bg-card p-3 ring-1 ring-foreground/10">
            <p>
              {t('alarms.answer.saved', {
                result: t(`alarms.status.${answered.status}`),
                sensor: answered.sensor.name ?? answered.sensor.id,
              })}
            </p>
            <Button variant="ghost" className="h-10 text-base" onClick={() => setAnswered(null)}>
              {t('alarms.answer.ok')}
            </Button>
          </div>
        )}

        {conflict && (
          <div role="alert" className="flex items-center justify-between gap-2 rounded-xl bg-card p-3 text-destructive ring-1 ring-foreground/10">
            <p>{conflict}</p>
            <Button variant="ghost" className="h-10 text-base" onClick={() => setConflict(null)}>
              {t('alarms.answer.ok')}
            </Button>
          </div>
        )}

        {error && (
          <p role="alert" className="text-destructive">
            {error}
          </p>
        )}

        {alarms === null ? (
          !error && (
            <p role="status" className="text-muted-foreground">
              {t('app.loading')}
            </p>
          )
        ) : alarms.length === 0 ? (
          <p className="py-6 text-center text-muted-foreground">
            {t(filter === 'new' ? 'alarms.noNew' : 'alarms.empty')}
          </p>
        ) : (
          <ul aria-label={t('alarms.title')} className="flex flex-col gap-3">
            {alarms.map((alarm) => (
              <li key={alarm.id} className="flex flex-col gap-2 rounded-xl bg-card p-4 text-base ring-1 ring-foreground/10">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-lg leading-snug font-semibold">{alarm.sensor.name ?? alarm.sensor.id}</p>
                  <span className={cn('shrink-0 rounded-full px-3 py-1 text-sm font-semibold', STATUS_BADGE[alarm.status])}>
                    {t(`alarms.status.${alarm.status}`)}
                  </span>
                </div>
                <p className="flex items-center gap-2 text-muted-foreground">
                  <Clock className="size-5 shrink-0" />
                  {formatDateTime(alarm.detected_at, i18n.language)}
                </p>
                <p className="flex items-center gap-2 text-muted-foreground">
                  <Activity className="size-5 shrink-0" />
                  {t('alarms.confidence', { value: alarm.confidence })}
                  {' · '}
                  {alarm.sources.map((s) => t(`alarms.sources.${s}`)).join(' + ')}
                </p>
                {alarm.possible_tampering && (
                  <p className="flex items-start gap-2 rounded-lg bg-amber-500/10 p-2 font-medium text-amber-800 dark:text-amber-300">
                    <TriangleAlert className="mt-0.5 size-5 shrink-0" />
                    {t('alarms.tampering')}
                  </p>
                )}
                {canRespond && alarm.status === 'new' && (
                  <AlarmAnswerForm
                    alarm={alarm}
                    onAnswered={handleAnswered}
                    onConflict={handleConflict}
                  />
                )}
                {alarm.response && (
                  <p className="border-t pt-2 text-muted-foreground">
                    {t('alarms.responded', {
                      by: alarm.response.by,
                      time: formatDateTime(alarm.response.at, i18n.language),
                    })}
                    {alarm.response.comment && `: ${t('alarms.comment', { comment: alarm.response.comment })}`}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
