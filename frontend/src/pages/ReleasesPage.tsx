import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell } from 'lucide-react'

import { ApiError } from '@/api/client'
import { listReleases } from '@/api/releases'
import type { Release, Sensor } from '@/api/types'
import { EndReleaseConfirm } from '@/components/EndReleaseConfirm'
import { ReleaseCard } from '@/components/ReleaseCard'
import { ReleaseHistory } from '@/components/ReleaseHistory'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { REFRESH_MS } from '@/lib/refresh'
import { formatDateTime } from '@/lib/sensor-status'

type Tab = 'ongoing' | 'history'
const TABS: Tab[] = ['ongoing', 'history']

const MINUTE_MS = 60_000

// "18:05" when it ends today, with the date when it ends tomorrow (a release lasts up to 24 h)
function endTime(iso: string, now: number, language: string): string {
  const end = new Date(iso)
  return end.toDateString() === new Date(now).toDateString()
    ? end.toLocaleTimeString(language, { timeStyle: 'short' })
    : formatDateTime(iso, language)
}

interface ReleasesPageProps {
  // the sensors the map has loaded, for the sensor filter of the history
  sensors: Sensor[]
  // api.md section 3: the forester ends a release, the district manager only reads
  canEnd: boolean
  // after ending one: the sensor watches again, so the map (and the badge) should refresh
  onEnded?: () => void
  // release from the address (/releases/7, opened by the push about its end): the history opens
  focusId?: number | null
}

// Timber releases of the forester's range (all ranges for the district manager):
// which sensors are muted now, until when, and for which carrier
export function ReleasesPage({ sensors, canEnd, onEnded, focusId = null }: ReleasesPageProps) {
  const { t, i18n } = useTranslation()
  // an ended release is only in the history
  const [tab, setTab] = useState<Tab>(focusId === null ? 'ongoing' : 'history')
  // dropped when the forester changes the tab: coming back to the history does not light it again
  const [focus, setFocus] = useState(focusId)
  const [releases, setReleases] = useState<Release[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // bumping it loads the list again, e.g. after ending a release
  const [reloadKey, setReloadKey] = useState(0)
  // the release whose end the forester is confirming, and the message after it
  const [ending, setEnding] = useState<Release | null>(null)
  const [ended, setEnded] = useState<string | null>(null)

  useEffect(() => {
    // the history loads itself
    if (tab !== 'ongoing') return
    let cancelled = false
    function load() {
      listReleases({ active: true })
        .then((loaded) => {
          if (cancelled) return
          setReleases(loaded)
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
  }, [reloadKey, t, tab])

  // the clock for "1 h 20 min left"; it ticks between the refreshes of the list
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(timer)
  }, [])

  function timeLeft(release: Release): string {
    // round up: "1 min left" until the very end, never "0 min"
    const minutes = Math.max(1, Math.ceil((Date.parse(release.ends_at) - now) / MINUTE_MS))
    const hours = Math.floor(minutes / 60)
    const rest = minutes % 60
    if (hours === 0) return t('releases.leftMinutes', { minutes })
    if (rest === 0) return t('releases.leftHours', { hours })
    return t('releases.leftHoursMinutes', { hours, minutes: rest })
  }

  // one that has just run out leaves at once, without waiting for the next refresh
  const ongoing = releases?.filter((r) => Date.parse(r.ends_at) > now)

  const nameOf = (release: Release) => release.sensor_name ?? release.sensor_id

  function changeTab(next: Tab) {
    setEnded(null)
    setFocus(null)
    setTab(next)
  }

  function startEnding(release: Release) {
    setEnded(null)
    setEnding(release)
  }

  function handleEnded() {
    if (!ending) return
    setEnded(t('release.ended', { name: nameOf(ending) }))
    // gone from the list at once; the reload confirms it with the backend
    setReleases((current) => current?.filter((r) => r.id !== ending.id) ?? null)
    setEnding(null)
    setReloadKey((k) => k + 1)
    onEnded?.()
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-2xl flex-col gap-3 p-3">
        {/* full-width segmented control like the alarm filter: big targets for a thumb */}
        <div role="group" aria-label={t('releases.tabs')} className="grid grid-cols-2 gap-1 rounded-xl bg-muted p-1">
          {TABS.map((tb) => (
            <Button
              key={tb}
              variant="ghost"
              aria-pressed={tb === tab}
              className="h-10 text-base aria-pressed:bg-background aria-pressed:font-semibold aria-pressed:shadow-sm"
              onClick={() => changeTab(tb)}
            >
              {t(`releases.tab.${tb}`)}
            </Button>
          ))}
        </div>

        {tab === 'history' ? (
          <ReleaseHistory sensors={sensors} focusId={focus} />
        ) : (
          <>
            {ended && (
              <div role="status" className="flex items-center justify-between gap-2 rounded-xl bg-card p-3 ring-1 ring-foreground/10">
                <p>{ended}</p>
                <Button variant="ghost" className="h-10 text-base" onClick={() => setEnded(null)}>
                  {t('alarms.answer.ok')}
                </Button>
              </div>
            )}

            {error && (
              <p role="alert" className="text-destructive">
                {error}
              </p>
            )}

            {ongoing === undefined ? (
              !error && (
                <p role="status" className="text-muted-foreground">
                  {t('app.loading')}
                </p>
              )
            ) : ongoing.length === 0 ? (
              <p className="py-6 text-center text-muted-foreground">{t('releases.noOngoing')}</p>
            ) : (
              <ul aria-label={t('releases.ongoing')} className="flex flex-col gap-3">
                {ongoing.map((release) => (
                  <ReleaseCard
                    key={release.id}
                    release={release}
                    when={`${t('releases.until', { time: endTime(release.ends_at, now, i18n.language) })} · ${timeLeft(release)}`}
                    who={[release.created_by, t('releases.since', { time: formatDateTime(release.starts_at, i18n.language) })]
                      .filter(Boolean)
                      .join(' · ')}
                  >
                    {canEnd && (
                      <Button
                        variant="outline"
                        className="mt-1 h-12 text-base [&_svg]:size-5!"
                        onClick={() => startEnding(release)}
                      >
                        <Bell />
                        {t('release.end')}
                      </Button>
                    )}
                  </ReleaseCard>
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      {/* the same question as on the map: a stray tap must not wake the sensor during loading */}
      <Sheet open={ending !== null} onOpenChange={(open) => !open && setEnding(null)}>
        <SheetContent closeLabel={t('mount.close')}>
          <SheetHeader>
            <SheetTitle>{t('release.endTitle')}</SheetTitle>
            <SheetDescription>{t('release.endDescription')}</SheetDescription>
          </SheetHeader>
          {ending && (
            <EndReleaseConfirm
              key={ending.id}
              sensor={{ id: ending.sensor_id, name: ending.sensor_name }}
              releaseId={ending.id}
              onEnded={handleEnded}
              onCancel={() => setEnding(null)}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
