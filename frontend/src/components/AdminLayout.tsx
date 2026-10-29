// Admin panel frame in the style of Grafana: side menu on the left, section on the right.
// On phones the menu is hidden behind the ☰ button.

import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { KeyRound, LogOut, Menu, Radio, Trees, Users, X, type LucideIcon } from 'lucide-react'
import { cn } from 'cn'

import type { User } from '@/api/types'
import { InstallButton } from '@/components/InstallButton'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { Button } from '@/components/ui/button'

export type AdminSection = 'users'

interface NavItem {
  id: AdminSection | 'sensors' | 'ranges'
  icon: LucideIcon
  // sections without a screen yet are shown greyed out
  ready: boolean
}

const NAV: NavItem[] = [
  { id: 'users', icon: Users, ready: true },
  { id: 'sensors', icon: Radio, ready: false },
  { id: 'ranges', icon: Trees, ready: false },
]

interface AdminLayoutProps {
  user: User
  section: AdminSection
  onSectionChange: (section: AdminSection) => void
  onChangePassword: () => void
  onLogout: () => void
  children: ReactNode
}

export function AdminLayout({ user, section, onSectionChange, onChangePassword, onLogout, children }: AdminLayoutProps) {
  const { t } = useTranslation()
  const [menuOpen, setMenuOpen] = useState(false)

  // Escape closes the menu on phones
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  return (
    <div className="min-h-svh md:pl-60">
      {/* phone header */}
      <header className="sticky top-0 z-20 flex h-12 items-center gap-2 border-b bg-sidebar px-2 md:hidden">
        <Button variant="ghost" size="icon" aria-label={t('admin.openMenu')} onClick={() => setMenuOpen(true)}>
          <Menu />
        </Button>
        <span className="font-semibold">{t(`admin.nav.${section}`)}</span>
      </header>

      {menuOpen && (
        <div aria-hidden className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setMenuOpen(false)} />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r bg-sidebar text-sidebar-foreground transition-[translate,visibility]',
          // on phones: slides in from the left; invisible also means skipped by Tab and screen readers
          !menuOpen && 'max-md:invisible max-md:-translate-x-full',
        )}
      >
        <div className="flex h-12 items-center gap-2 border-b px-3">
          <img src="/logo.svg" alt="" className="size-6 rounded" />
          <span className="flex-1 truncate font-semibold">{t('app.shortName')}</span>
          <Button
            variant="ghost"
            size="icon-sm"
            className="md:hidden"
            aria-label={t('admin.closeMenu')}
            onClick={() => setMenuOpen(false)}
          >
            <X />
          </Button>
        </div>

        <nav aria-label={t('admin.menu')} className="flex flex-1 flex-col gap-0.5 p-2">
          {NAV.map(({ id, icon: Icon, ready }) => {
            const active = ready && id === section
            return (
              <button
                key={id}
                type="button"
                disabled={!ready}
                aria-current={active ? 'page' : undefined}
                onClick={() => {
                  if (!ready) return
                  onSectionChange(id as AdminSection)
                  setMenuOpen(false)
                }}
                className={cn(
                  'relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm transition-colors',
                  'hover:bg-sidebar-accent disabled:pointer-events-none disabled:opacity-50',
                  // active item: highlighted with a bar on the left, like in Grafana
                  active &&
                    'bg-sidebar-accent font-medium before:absolute before:inset-y-1.5 before:left-0 before:w-1 before:rounded-full before:bg-sidebar-primary',
                )}
              >
                <Icon className="size-4 shrink-0" />
                <span className="flex-1">{t(`admin.nav.${id}`)}</span>
                {!ready && <span className="text-xs">{t('admin.soon')}</span>}
              </button>
            )
          })}
        </nav>

        <div className="flex flex-col gap-2 border-t p-2">
          <div className="px-2.5 py-1">
            <p className="truncate text-sm font-medium">{user.full_name}</p>
            <p className="truncate text-xs text-muted-foreground">
              {user.login} · {t(`role.${user.role}`)}
            </p>
          </div>
          <Button variant="ghost" className="justify-start" onClick={onChangePassword}>
            <KeyRound />
            {t('home.changePassword')}
          </Button>
          <Button variant="ghost" className="justify-start" onClick={onLogout}>
            <LogOut />
            {t('home.logout')}
          </Button>
          <div className="flex flex-wrap items-center justify-between gap-1 px-1">
            <ThemeSwitcher />
            <LanguageSwitcher />
          </div>
          <InstallButton />
        </div>
      </aside>

      <main className="mx-auto w-full max-w-5xl p-4 md:p-6">{children}</main>
    </div>
  )
}
