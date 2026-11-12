import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell, KeyRound, LogOut, Map as MapIcon, Menu } from 'lucide-react'
import { cn } from 'cn'

import { ApiError } from '@/api/client'
import { listSensors } from '@/api/sensors'
import type { Sensor, User } from '@/api/types'
import { InstallButton } from '@/components/InstallButton'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { SensorMap } from '@/components/SensorMap'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { REFRESH_MS } from '@/lib/refresh'
import { STATUS_DOT, statusOf, type Status } from '@/lib/sensor-status'
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
  const { t } = useTranslation()
  const [sensors, setSensors] = useState<Sensor[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [view, setView] = useState<View>('map')
  // bumping it loads the sensors again, e.g. after answering an alarm
  const [sensorsKey, setSensorsKey] = useState(0)

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
  const unmounted = (sensors ?? []).length - mounted.length
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
            canRespond={user.role === 'forester'}
            onAnswered={() => setSensorsKey((k) => k + 1)}
          />
        ) : sensors === null && !error ? (
          <p role="status" className="flex h-full items-center justify-center text-muted-foreground">
            {t('app.loading')}
          </p>
        ) : (
          <SensorMap sensors={sensors ?? []} />
        )}

        {/* messages float over the map; the map stays usable under them */}
        {view === 'map' && (
          <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex flex-col items-center gap-2 p-3">
            {passwordChanged && (
              <p role="status" className="rounded-lg bg-card px-3 py-2 text-sm shadow ring-1 ring-foreground/10">
                {t('home.passwordChanged')}
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
            {unmounted > 0 && (
              <p className="border-t pt-1 text-xs text-muted-foreground">{t('map.unmounted', { count: unmounted })}</p>
            )}
          </section>
        )}
      </main>

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
