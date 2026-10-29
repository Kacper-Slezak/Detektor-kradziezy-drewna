import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Search } from 'lucide-react'
import { cn } from 'cn'

import { ApiError } from '@/api/client'
import type { ManagedUser, Range } from '@/api/types'
import { listRanges, listUsers } from '@/api/users'
import { NewUserForm } from '@/components/NewUserForm'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'

interface Credentials {
  login: string
  password: string
}

type Status = 'active' | 'temporaryPassword' | 'inactive'

function statusOf(user: ManagedUser): Status {
  if (!user.active) return 'inactive'
  return user.must_change_password ? 'temporaryPassword' : 'active'
}

const STATUS_DOT: Record<Status, string> = {
  active: 'bg-emerald-500',
  temporaryPassword: 'bg-amber-500',
  inactive: 'bg-muted-foreground',
}

// "Users" section of the admin panel (AdminLayout gives the frame)
export function UsersPage() {
  const { t } = useTranslation()
  const [users, setUsers] = useState<ManagedUser[] | null>(null)
  const [ranges, setRanges] = useState<Range[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  // shown once after creating an account; the backend never returns the password again
  const [created, setCreated] = useState<Credentials | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([listUsers(), listRanges()])
      .then(([loadedUsers, loadedRanges]) => {
        if (cancelled) return
        setUsers(loadedUsers)
        setRanges(loadedRanges)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : t('errors.network'))
      })
    return () => {
      cancelled = true
    }
  }, [t])

  function handleCreated(user: ManagedUser, password: string) {
    setUsers((current) => [...(current ?? []), user])
    setCreated({ login: user.login, password })
    setCopied(false)
    setFormOpen(false)
  }

  async function copyCredentials() {
    if (!created) return
    try {
      await navigator.clipboard.writeText(
        `${t('users.created.login')}: ${created.login}\n${t('users.created.password')}: ${created.password}`,
      )
      setCopied(true)
    } catch {
      // no clipboard access (e.g. plain http); the data is still on screen
    }
  }

  const rangeName = (id: number | null) => ranges.find((r) => r.id === id)?.name

  const query = search.trim().toLowerCase()
  const shown = (users ?? []).filter(
    (u) => !query || u.full_name.toLowerCase().includes(query) || u.login.toLowerCase().includes(query),
  )

  const stats = users && [
    { label: t('users.stats.all'), value: users.length },
    { label: t('users.stats.foresters'), value: users.filter((u) => u.role === 'forester').length },
    { label: t('users.stats.temporaryPassword'), value: users.filter((u) => statusOf(u) === 'temporaryPassword').length },
    { label: t('users.stats.inactive'), value: users.filter((u) => !u.active).length },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">{t('users.title')}</h1>
        <Button onClick={() => setFormOpen(true)}>
          <Plus />
          {t('users.add')}
        </Button>
      </div>

      {created && (
        <Card role="status">
          <CardHeader>
            <CardTitle>{t('users.created.title')}</CardTitle>
            <CardDescription>{t('users.created.description')}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono">
              <dt className="font-sans text-muted-foreground">{t('users.created.login')}</dt>
              <dd>{created.login}</dd>
              <dt className="font-sans text-muted-foreground">{t('users.created.password')}</dt>
              <dd>{created.password}</dd>
            </dl>
            <div className="flex gap-2">
              <Button variant="outline" onClick={copyCredentials}>
                {copied ? t('users.created.copied') : t('users.created.copy')}
              </Button>
              <Button variant="ghost" onClick={() => setCreated(null)}>
                {t('users.created.done')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* stat tiles, like single-value panels in Grafana */}
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
            aria-label={t('users.search')}
            placeholder={t('users.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
          />
        </div>

        {loadError ? (
          <p role="alert" className="p-4 text-sm text-destructive">
            {loadError}
          </p>
        ) : users === null ? (
          <p role="status" className="p-4 text-muted-foreground">
            {t('app.loading')}
          </p>
        ) : (
          // wide table scrolls sideways on phones
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">{t('users.table.name')}</th>
                  <th className="px-3 py-2 font-medium">{t('users.table.login')}</th>
                  <th className="px-3 py-2 font-medium">{t('users.table.role')}</th>
                  <th className="px-3 py-2 font-medium">{t('users.table.range')}</th>
                  <th className="px-3 py-2 font-medium">{t('users.table.status')}</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {shown.map((user) => {
                  const status = statusOf(user)
                  return (
                    <tr key={user.id} className="hover:bg-muted/40">
                      <td className="px-3 py-2 font-medium whitespace-nowrap">{user.full_name}</td>
                      <td className="px-3 py-2 font-mono whitespace-nowrap">{user.login}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{t(`role.${user.role}`)}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{rangeName(user.range_id) ?? '—'}</td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className="inline-flex items-center gap-1.5">
                          <span aria-hidden className={cn('size-2 rounded-full', STATUS_DOT[status])} />
                          {t(`users.status.${status}`)}
                        </span>
                      </td>
                    </tr>
                  )
                })}
                {shown.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">
                      {t('users.noResults')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Sheet open={formOpen} onOpenChange={setFormOpen}>
        <SheetContent closeLabel={t('users.form.close')}>
          <SheetHeader>
            <SheetTitle>{t('users.form.title')}</SheetTitle>
            <SheetDescription>{t('users.form.description')}</SheetDescription>
          </SheetHeader>
          <NewUserForm ranges={ranges} onCreated={handleCreated} />
        </SheetContent>
      </Sheet>
    </div>
  )
}
