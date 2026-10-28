import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api/client'
import type { ManagedUser, Range } from '@/api/types'
import { listRanges, listUsers } from '@/api/users'
import { NewUserForm } from '@/components/NewUserForm'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface Credentials {
  login: string
  password: string
}

interface UsersPageProps {
  onBack: () => void
}

export function UsersPage({ onBack }: UsersPageProps) {
  const { t } = useTranslation()
  const [users, setUsers] = useState<ManagedUser[] | null>(null)
  const [ranges, setRanges] = useState<Range[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
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

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-2xl flex-col gap-4 p-4 pt-14">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">{t('users.title')}</h1>
        <Button variant="outline" onClick={onBack}>
          {t('users.back')}
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

      <Card>
        <CardHeader>
          <CardTitle>{t('users.form.title')}</CardTitle>
          <CardDescription>{t('users.form.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          <NewUserForm ranges={ranges} onCreated={handleCreated} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('users.list.title')}</CardTitle>
        </CardHeader>
        <CardContent>
          {loadError ? (
            <p role="alert" className="text-sm text-destructive">
              {loadError}
            </p>
          ) : users === null ? (
            <p role="status" className="text-muted-foreground">
              {t('app.loading')}
            </p>
          ) : (
            <ul className="flex flex-col divide-y">
              {users.map((user) => (
                <li key={user.id} className="flex flex-col gap-0.5 py-2">
                  <span className="font-medium">{user.full_name}</span>
                  <span className="text-sm text-muted-foreground">
                    {user.login} · {t(`role.${user.role}`)}
                    {rangeName(user.range_id) && ` · ${rangeName(user.range_id)}`}
                  </span>
                  {(!user.active || user.must_change_password) && (
                    <span className="text-xs text-muted-foreground">
                      {!user.active ? t('users.list.inactive') : t('users.list.mustChangePassword')}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
