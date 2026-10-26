import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { setToken } from '@/api/client'
import type { User } from '@/api/types'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { Button } from '@/components/ui/button'
import { ChangePasswordPage } from '@/pages/ChangePasswordPage'
import { LoginPage } from '@/pages/LoginPage'

function App() {
  const { t } = useTranslation()
  const [user, setUser] = useState<User | null>(null)
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordChanged, setPasswordChanged] = useState(false)

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
      <div className="fixed top-2 right-2">
        <LanguageSwitcher />
      </div>
      {renderPage()}
    </>
  )
}

export default App
