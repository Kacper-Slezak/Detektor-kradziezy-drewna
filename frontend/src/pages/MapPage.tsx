import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell, KeyRound, LocateFixed, LogOut, Map as MapIcon, Menu } from 'lucide-react'
import { cn } from 'cn'

import { ApiError } from '@/api/client'
import { listSensors } from '@/api/sensors'
import type { Release, Sensor, User } from '@/api/types'
import { EndReleaseConfirm } from '@/components/EndReleaseConfirm'
import { InstallButton } from '@/components/InstallButton'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { MountSensorForm } from '@/components/MountSensorForm'
import { PushButton } from '@/components/PushButton'
import { ReleaseForm } from '@/components/ReleaseForm'
import { SensorMap } from '@/components/SensorMap'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { REFRESH_MS } from '@/lib/refresh'
import { goTo, parseRoute, type Route } from '@/lib/route'
import { formatDateTime, STATUS_DOT, statusOf, type Status } from '@/lib/sensor-status'
import { AlarmsPage } from '@/pages/AlarmsPage'

type View = 'map' | 'alarms'

// big enough to hit with a thumb (about 44 px)
const VIEW_BUTTON = 'h-11 gap-2 px-3 text-base [&_svg]:size-5!'

// order of the legend: what needs attention first
const LEGEND: Status[] = ['alarm', 'silent', 'muted', 'ok', 'inactive']

interface MapPageProps {
  user: User
  passwordChanged: boolean
  onChangePassword: () => void
  onLogout: () => void
}

// Home screen of a forester and a district manager: full-screen map of sensors, or the alarm list
export function MapPage({ user, passwordChanged, onChangePassword, onLogout }: MapPageProps) {
  const { t, i18n } = useTranslation()
  const [sensors, setSensors] = useState<Sensor[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  // the view comes from the address, so a push can open a given alarm
  const [route, setRoute] = useState<Route>(() => parseRoute())
  const view = route.view
  // bumping it loads the sensors again, e.g. after answering an alarm
  const [sensorsKey, setSensorsKey] = useState(0)
  const [mountOpen, setMountOpen] = useState(false)
  // the mounted sensor the forester is moving to another stack (same panel as mounting)
  const [moving, setMoving] = useState<Sensor | null>(null)
  // the sensor being muted for timber pickup, and the one whose muting is being ended
  const [releasing, setReleasing] = useState<Sensor | null>(null)
  const [endingRelease, setEndingRelease] = useState<Sensor | null>(null)
  // what the forester has just done (mounted, moved, muted...), for the message over the map
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    // the phone's back button
    const onPopState = () => setRoute(parseRoute())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  function setView(next: View) {
    const nextRoute: Route = next === 'map' ? { view: 'map' } : { view: 'alarms', alarmId: null }
    goTo(nextRoute)
    setRoute(nextRoute)
  }

  useEffect(() => {
    let cancelled = false
    function load() {
      listSensors()
        .then((loaded) => {
          if (cancelled) return
          setSensors(loaded)
          setError(null)
        })
        .catch((err) => {
          // a failed refresh keeps the last pins on the map
          if (!cancelled) setError(err instanceof ApiError ? err.message : t('errors.network'))
        })
    }
    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [sensorsKey, t])

  const mounted = (sensors ?? []).filter((s) => s.lat !== null)
  const unmountedSensors = (sensors ?? []).filter((s) => s.lat === null)
  // api.md: only a forester mounts (the district manager would get 403)
  const canMount = user.role === 'forester' && unmountedSensors.length > 0

  // after any change the pins load again at once, not after REFRESH_MS
  const reloadSensors = () => setSensorsKey((k) => k + 1)

  function handleMounted(sensor: Sensor) {
    setNotice(t(moving ? 'mount.moved' : 'mount.saved', { name: sensor.name ?? sensor.id }))
    closeMount()
    reloadSensors()
  }

  function startMove(sensor: Sensor) {
    setNotice(null)
    setMoving(sensor)
  }

  function startRelease(sensor: Sensor) {
    setNotice(null)
    setReleasing(sensor)
  }

  function handleReleased(release: Release) {
    const name = releasing?.name ?? release.sensor_name ?? release.sensor_id
    setNotice(t('release.saved', { name, time: formatDateTime(release.ends_at, i18n.language) }))
    setReleasing(null)
    reloadSensors()
  }

  function startEndRelease(sensor: Sensor) {
    setNotice(null)
    setEndingRelease(sensor)
  }

  function handleReleaseEnded() {
    if (endingRelease) setNotice(t('release.ended', { name: endingRelease.name ?? endingRelease.id }))
    setEndingRelease(null)
    reloadSensors()
  }

  function closeMount() {
    setMountOpen(false)
    setMoving(null)
  }
  const counts = LEGEND.map((status) => ({
    status,
    count: mounted.filter((s) => statusOf(s) === status).length,
  })).filter(({ count }) => count > 0)
  // sensors with an alarm that waits for the forester; refreshed together with the map
  const openAlarms = (sensors ?? []).filter((s) => s.open_alarm_id !== null).length

  return (
    <div className="flex h-svh flex-col">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b bg-background px-3">
        <img src="/logo.svg" alt="" className="size-7 rounded" />
        {/* on phones the view buttons already say where we are */}
        <h1 className="truncate font-semibold max-sm:sr-only">{t(view === 'map' ? 'map.title' : 'alarms.title')}</h1>
        <nav aria-label={t('map.views')} className="flex flex-1 items-center gap-1 sm:justify-center">
          <Button
            variant={view === 'map' ? 'secondary' : 'ghost'}
            aria-current={view === 'map' ? 'page' : undefined}
            className={VIEW_BUTTON}
            onClick={() => setView('map')}
          >
            <MapIcon />
            {t('map.viewMap')}
          </Button>
          <Button
            variant={view === 'alarms' ? 'secondary' : 'ghost'}
            aria-current={view === 'alarms' ? 'page' : undefined}
            aria-label={openAlarms > 0 ? t('map.viewAlarmsOpen', { count: openAlarms }) : t('map.viewAlarms')}
            className={VIEW_BUTTON}
            onClick={() => setView('alarms')}
          >
            <Bell />
            {t('map.viewAlarms')}
            {openAlarms > 0 && (
              <span className="min-w-6 rounded-full bg-red-600 px-1.5 text-sm leading-6 text-white tabular-nums">
                {openAlarms}
              </span>
            )}
          </Button>
        </nav>
        <span className="hidden truncate text-sm text-muted-foreground lg:inline">
          {user.full_name}
          {user.range && ` · ${user.range.name}`}
        </span>
        <Button variant="ghost" size="icon" aria-label={t('map.menu')} className="size-11 [&_svg]:size-6!" onClick={() => setMenuOpen(true)}>
          <Menu />
        </Button>
      </header>

      <main className="relative min-h-0 flex-1">
        {view === 'alarms' ? (
          <AlarmsPage
            // a new alarm from the address starts the list again
            key={route.alarmId ?? 'list'}
            focusId={route.alarmId}
            canRespond={user.role === 'forester'}
            onAnswered={() => setSensorsKey((k) => k + 1)}
          />
        ) : sensors === null && !error ? (
          <p role="status" className="flex h-full items-center justify-center text-muted-foreground">
            {t('app.loading')}
          </p>
        ) : (
          <SensorMap
            sensors={sensors ?? []}
            // api.md: a forester moves and mutes sensors of their range (the district manager would get 403)
            onMove={user.role === 'forester' ? startMove : undefined}
            onRelease={user.role === 'forester' ? startRelease : undefined}
            onEndRelease={user.role === 'forester' ? startEndRelease : undefined}
          />
        )}

        {/* messages float over the map; the map stays usable under them */}
        {view === 'map' && (
          <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex flex-col items-center gap-2 p-3">
            {passwordChanged && (
              <p role="status" className="rounded-lg bg-card px-3 py-2 text-sm shadow ring-1 ring-foreground/10">
                {t('home.passwordChanged')}
              </p>
            )}
            {notice && (
              <p role="status" className="rounded-lg bg-card px-3 py-2 text-sm shadow ring-1 ring-foreground/10">
                {notice}
              </p>
            )}
            {error && (
              <p role="alert" className="rounded-lg bg-card px-3 py-2 text-sm text-destructive shadow ring-1 ring-foreground/10">
                {error}
              </p>
            )}
          </div>
        )}

        {view === 'map' && sensors && (
          <section
            aria-label={t('map.legend')}
            className="absolute bottom-6 left-3 z-10 flex flex-col gap-1 rounded-lg bg-card/95 p-3 text-sm shadow ring-1 ring-foreground/10"
          >
            {counts.length === 0 && <p className="text-muted-foreground">{t('map.noSensors')}</p>}
            <ul className="flex flex-col gap-1">
              {counts.map(({ status, count }) => (
                <li key={status} className="flex items-center gap-2">
                  <span aria-hidden className={cn('size-2.5 rounded-full', STATUS_DOT[status])} />
                  <span className="flex-1">{t(`sensors.status.${status}`)}</span>
                  <span className="font-medium tabular-nums">{count}</span>
                </li>
              ))}
            </ul>
            {unmountedSensors.length > 0 && (
              <p className="border-t pt-1 text-xs text-muted-foreground">
                {t('map.unmounted', { count: unmountedSensors.length })}
              </p>
            )}
            {canMount && (
              <Button
                className="mt-1 h-11 text-base [&_svg]:size-5!"
                onClick={() => {
                  setNotice(null)
                  setMountOpen(true)
                }}
              >
                <LocateFixed />
                {t('mount.open')}
              </Button>
            )}
          </section>
        )}
      </main>

      <Sheet open={mountOpen || moving !== null} onOpenChange={(open) => !open && closeMount()}>
        <SheetContent closeLabel={t('mount.close')}>
          <SheetHeader>
            <SheetTitle>{t(moving ? 'mount.moveTitle' : 'mount.title')}</SheetTitle>
            <SheetDescription>{t(moving ? 'mount.moveDescription' : 'mount.description')}</SheetDescription>
          </SheetHeader>
          {/* the form starts empty each time the panel opens */}
          {moving ? (
            <MountSensorForm key={moving.id} sensors={[moving]} onMounted={handleMounted} moving />
          ) : (
            mountOpen && <MountSensorForm sensors={unmountedSensors} onMounted={handleMounted} />
          )}
        </SheetContent>
      </Sheet>

      <Sheet open={releasing !== null} onOpenChange={(open) => !open && setReleasing(null)}>
        <SheetContent closeLabel={t('mount.close')}>
          <SheetHeader>
            <SheetTitle>{t('release.title')}</SheetTitle>
            <SheetDescription>{t('release.description')}</SheetDescription>
          </SheetHeader>
          {releasing && <ReleaseForm key={releasing.id} sensor={releasing} onReleased={handleReleased} />}
        </SheetContent>
      </Sheet>

      <Sheet open={endingRelease !== null} onOpenChange={(open) => !open && setEndingRelease(null)}>
        <SheetContent closeLabel={t('mount.close')}>
          <SheetHeader>
            <SheetTitle>{t('release.endTitle')}</SheetTitle>
            <SheetDescription>{t('release.endDescription')}</SheetDescription>
          </SheetHeader>
          {endingRelease && (
            <EndReleaseConfirm
              key={endingRelease.id}
              sensor={endingRelease}
              onEnded={handleReleaseEnded}
              onCancel={() => setEndingRelease(null)}
            />
          )}
        </SheetContent>
      </Sheet>

      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent closeLabel={t('admin.closeMenu')}>
          <SheetHeader>
            <SheetTitle>{user.full_name}</SheetTitle>
            <SheetDescription>
              {t(`role.${user.role}`)}
              {user.range && ` · ${user.range.name}`}
            </SheetDescription>
          </SheetHeader>
          <div className="flex flex-col gap-2">
            {/* api.md: pushes are only for foresters */}
            {user.role === 'forester' && <PushButton />}
            <Button
              variant="ghost"
              className="justify-start"
              onClick={() => {
                setMenuOpen(false)
                onChangePassword()
              }}
            >
              <KeyRound />
              {t('home.changePassword')}
            </Button>
            <Button variant="ghost" className="justify-start" onClick={onLogout}>
              <LogOut />
              {t('home.logout')}
            </Button>
            <div className="flex flex-wrap items-center justify-between gap-1 border-t px-1 pt-2">
              <ThemeSwitcher />
              <LanguageSwitcher />
            </div>
            <InstallButton />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
