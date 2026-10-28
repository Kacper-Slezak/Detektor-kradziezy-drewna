import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { me } from '@/api/auth'
import { ApiError, getToken, setToken } from '@/api/client'
import type { User } from '@/api/types'
import { InstallButton } from '@/components/InstallButton'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { Button } from '@/components/ui/button'
import { ChangePasswordPage } from '@/pages/ChangePasswordPage'
import { LoginPage } from '@/pages/LoginPage'

function App() {
  const { t } = useTranslation()
  const [user, setUser] = useState<User | null>(null)
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordChanged, setPasswordChanged] = useState(false)
  // a saved token means we may still be signed in, so check it before showing the login page
  const [restoring, setRestoring] = useState(() => getToken() !== null)

  useEffect(() => {
    if (!getToken()) return
    let cancelled = false
    me()
      .then((restored) => {
        if (!cancelled) setUser(restored)
      })
      .catch((err) => {
        // 401: token expired or invalid; other errors (e.g. no network) keep the token
        if (err instanceof ApiError && err.status === 401) setToken(null)
      })
      .finally(() => {
        if (!cancelled) setRestoring(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function handleLoggedIn(loggedIn: User) {
    setPasswordChanged(false)
    setUser(loggedIn)
  }

  function logout() {
    setToken(null)
    setUser(null)
    setChangingPassword(false)
  }

  function handlePasswordChanged() {
    if (!user) return
    setUser({ ...user, must_change_password: false })
    setChangingPassword(false)
    setPasswordChanged(true)
  }

  function renderPage() {
    if (restoring) {
      return (
        <main className="flex min-h-svh items-center justify-center p-4">
          <p role="status" className="text-muted-foreground">
            {t('app.loading')}
          </p>
        </main>
      )
    }

    if (!user) return <LoginPage onLoggedIn={handleLoggedIn} />

    if (user.must_change_password || changingPassword) {
      const forced = user.must_change_password
      return (
        <ChangePasswordPage
          forced={forced}
          onChanged={handlePasswordChanged}
          onCancel={forced ? logout : () => setChangingPassword(false)}
        />
      )
    }

    return (
      <main className="flex min-h-svh flex-col items-center justify-center gap-4 p-4">
        <h1 className="text-2xl font-semibold">{t('home.welcome', { name: user.full_name })}</h1>
        <p className="text-muted-foreground">
          {t('home.role', { role: t(`role.${user.role}`) })}
          {user.range && ` · ${user.range.name}`}
        </p>
        {passwordChanged && (
          <p role="status" className="text-sm">
            {t('home.passwordChanged')}
          </p>
        )}
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => {
              setPasswordChanged(false)
              setChangingPassword(true)
            }}
          >
            {t('home.changePassword')}
          </Button>
          <Button variant="outline" onClick={logout}>
            {t('home.logout')}
          </Button>
        </div>
      </main>
    )
  }

  return (
    <>
      <div className="fixed top-2 right-2 flex items-center gap-2">
        <InstallButton />
        <ThemeSwitcher />
        <LanguageSwitcher />
      </div>
      {renderPage()}
    </>
  )
}

export default App
