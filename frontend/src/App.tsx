import { lazy, Suspense, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { me } from '@/api/auth'
import { ApiError, getToken, setToken } from '@/api/client'
import { listLogs } from '@/api/logs'
import type { User } from '@/api/types'
import { AdminLayout, type AdminSection } from '@/components/AdminLayout'
import { InstallButton } from '@/components/InstallButton'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { disablePush } from '@/lib/push'
import { resetRoute } from '@/lib/route'
import { ChangePasswordPage } from '@/pages/ChangePasswordPage'
import { LoginPage } from '@/pages/LoginPage'
import { LogsPage } from '@/pages/LogsPage'
import { SensorsPage } from '@/pages/SensorsPage'
import { UsersPage } from '@/pages/UsersPage'

// the map pulls in Leaflet, so it is loaded only for foresters and district managers
const MapPage = lazy(() => import('@/pages/MapPage').then((m) => ({ default: m.MapPage })))

function App() {
  const { t } = useTranslation()
  const [user, setUser] = useState<User | null>(null)
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordChanged, setPasswordChanged] = useState(false)
  const [adminSection, setAdminSection] = useState<AdminSection>('users')
  // the "Logs" section only when the backend serves them (ADMIN_LOGS_ENABLED, api.md section 7)
  const [logsEnabled, setLogsEnabled] = useState(false)
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
        if (err instanceof ApiError && err.status === 401) {
          setToken(null)
          // signed out without the logout button: this phone should stop getting that user's alarms too
          void disablePush(null)
        }
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
    resetRoute()
    // the next person on this phone must not get this user's alarms. It needs the token,
    // so it gets it before it is cleared; it is not awaited, logging out stays instant
    void disablePush(getToken())
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

  function startChangingPassword() {
    setPasswordChanged(false)
    setChangingPassword(true)
  }

  // the admin works in the panel with a side menu, the others on the map;
  // both have their own menu with the language and theme switchers
  const signedIn = !restoring && user !== null && !user.must_change_password && !changingPassword
  const inAdminPanel = signedIn && user.role === 'admin'

  useEffect(() => {
    if (!inAdminPanel) return
    let cancelled = false
    listLogs(1)
      .then(() => !cancelled && setLogsEnabled(true))
      .catch(() => !cancelled && setLogsEnabled(false))
    return () => {
      cancelled = true
    }
  }, [inAdminPanel])

  const loading = (
    <main className="flex min-h-svh items-center justify-center p-4">
      <p role="status" className="text-muted-foreground">
        {t('app.loading')}
      </p>
    </main>
  )

  function renderPage() {
    if (restoring) return loading

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

    if (inAdminPanel) {
      return (
        <AdminLayout
          user={user}
          section={adminSection}
          onSectionChange={setAdminSection}
          showLogs={logsEnabled}
          onChangePassword={startChangingPassword}
          onLogout={logout}
        >
          {passwordChanged && (
            <p role="status" className="mb-4 text-sm">
              {t('home.passwordChanged')}
            </p>
          )}
          {adminSection === 'users' && <UsersPage currentUserId={user.id} />}
          {adminSection === 'sensors' && <SensorsPage />}
          {adminSection === 'logs' && logsEnabled && <LogsPage />}
        </AdminLayout>
      )
    }

    return (
      <Suspense fallback={loading}>
        <MapPage
          user={user}
          passwordChanged={passwordChanged}
          onChangePassword={startChangingPassword}
          onLogout={logout}
        />
      </Suspense>
    )
  }

  return (
    <>
      {!signedIn && (
        <div className="fixed top-2 right-2 flex items-center gap-2">
          <InstallButton />
          <ThemeSwitcher />
          <LanguageSwitcher />
        </div>
      )}
      {renderPage()}
    </>
  )
}

export default App
