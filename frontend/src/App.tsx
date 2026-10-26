import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { setToken } from '@/api/client'
import type { User } from '@/api/types'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { Button } from '@/components/ui/button'
import { LoginPage } from '@/pages/LoginPage'

function App() {
  const { t } = useTranslation()
  const [user, setUser] = useState<User | null>(null)

  function logout() {
    setToken(null)
    setUser(null)
  }

  return (
    <>
      <div className="fixed top-2 right-2">
        <LanguageSwitcher />
      </div>
      {user ? (
        <main className="flex min-h-svh flex-col items-center justify-center gap-4 p-4">
          <h1 className="text-2xl font-semibold">{t('home.welcome', { name: user.full_name })}</h1>
          <p className="text-muted-foreground">
            {t('home.role', { role: t(`role.${user.role}`) })}
            {user.range && ` · ${user.range.name}`}
          </p>
          <Button variant="outline" onClick={logout}>
            {t('home.logout')}
          </Button>
        </main>
      ) : (
        <LoginPage onLoggedIn={setUser} />
      )}
    </>
  )
}

export default App
