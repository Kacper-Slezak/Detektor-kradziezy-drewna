import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { KeyRound, LogOut, Menu } from 'lucide-react'
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
import { STATUS_DOT, statusOf, type Status } from '@/lib/sensor-status'

// api.md: the app asks for the lists every few dozen seconds, new alarms also come as a push
const REFRESH_MS = 60_000

// order of the legend: what needs attention first
const LEGEND: Status[] = ['alarm', 'silent', 'muted', 'ok', 'inactive']

interface MapPageProps {
  user: User
  passwordChanged: boolean
  onChangePassword: () => void
  onLogout: () => void
}

// Home screen of a forester and a district manager: full-screen map of sensors
export function MapPage({ user, passwordChanged, onChangePassword, onLogout }: MapPageProps) {
  const { t } = useTranslation()
  const [sensors, setSensors] = useState<Sensor[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)

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
  }, [t])

  const mounted = (sensors ?? []).filter((s) => s.lat !== null)
  const unmounted = (sensors ?? []).length - mounted.length
  const counts = LEGEND.map((status) => ({
    status,
    count: mounted.filter((s) => statusOf(s) === status).length,
  })).filter(({ count }) => count > 0)

  return (
    <div className="flex h-svh flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b bg-background px-3">
        <img src="/logo.svg" alt="" className="size-6 rounded" />
        <h1 className="flex-1 truncate font-semibold">{t('map.title')}</h1>
        <span className="hidden truncate text-sm text-muted-foreground sm:inline">
          {user.full_name}
          {user.range && ` · ${user.range.name}`}
        </span>
        <Button variant="ghost" size="icon" aria-label={t('map.menu')} onClick={() => setMenuOpen(true)}>
          <Menu />
        </Button>
      </header>

      <main className="relative flex-1">
        {sensors === null && !error ? (
          <p role="status" className="flex h-full items-center justify-center text-muted-foreground">
            {t('app.loading')}
          </p>
        ) : (
          <SensorMap sensors={sensors ?? []} />
        )}

        {/* messages float over the map; the map stays usable under them */}
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

        {sensors && (
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
