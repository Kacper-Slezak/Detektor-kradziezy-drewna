import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api/client'
import type { ManagedUser, Range, Role } from '@/api/types'
import { createUser } from '@/api/users'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { loginFromName } from '@/lib/login'
import { generateTempPassword } from '@/lib/password'

const MIN_PASSWORD_LENGTH = 8
const ROLES: Role[] = ['forester', 'district_manager', 'admin']

// Same look as <Input>, for a native <select> (works well on phones)
const SELECT_CLASS =
  'h-8 w-full rounded-lg border border-input bg-transparent px-2 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 md:text-sm dark:bg-input/30'

interface NewUserFormProps {
  ranges: Range[]
  // password is passed separately, because the backend never returns it
  onCreated: (user: ManagedUser, password: string) => void
}

export function NewUserForm({ ranges, onCreated }: NewUserFormProps) {
  const { t } = useTranslation()
  const [fullName, setFullName] = useState('')
  const [login, setLogin] = useState('')
  // until the admin edits the login, it follows the full name
  const [loginEdited, setLoginEdited] = useState(false)
  const [role, setRole] = useState<Role>('forester')
  const [rangeId, setRangeId] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function handleFullNameChange(value: string) {
    setFullName(value)
    if (!loginEdited) setLogin(loginFromName(value))
  }

  function reset() {
    setFullName('')
    setLogin('')
    setLoginEdited(false)
    setRole('forester')
    setRangeId('')
    setPassword('')
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)

    // Quick check in the browser; the backend does the final validation
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(t('users.form.errors.passwordTooShort', { count: MIN_PASSWORD_LENGTH }))
      return
    }
    if (role === 'forester' && !rangeId) {
      setError(t('users.form.errors.rangeRequired'))
      return
    }

    setLoading(true)
    try {
      const created = await createUser({
        login: login.trim(),
        full_name: fullName.trim(),
        role,
        // only a forester belongs to a range
        range_id: role === 'forester' ? Number(rangeId) : null,
        password,
      })
      onCreated(created, password)
      reset()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="full-name">{t('users.form.fullName')}</Label>
        <Input
          id="full-name"
          value={fullName}
          onChange={(e) => handleFullNameChange(e.target.value)}
          maxLength={100}
          required
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="new-login">{t('users.form.login')}</Label>
        <Input
          id="new-login"
          value={login}
          onChange={(e) => {
            setLogin(e.target.value)
            setLoginEdited(true)
          }}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          maxLength={50}
          required
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="role">{t('users.form.role')}</Label>
        <select id="role" className={SELECT_CLASS} value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`role.${r}`)}
            </option>
          ))}
        </select>
      </div>
      {role === 'forester' && (
        <div className="flex flex-col gap-2">
          <Label htmlFor="range">{t('users.form.range')}</Label>
          <select id="range" className={SELECT_CLASS} value={rangeId} onChange={(e) => setRangeId(e.target.value)}>
            <option value="">{t('users.form.chooseRange')}</option>
            {ranges.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="flex flex-col gap-2">
        <Label htmlFor="temp-password">{t('users.form.password')}</Label>
        <div className="flex gap-2">
          {/* visible on purpose: the admin passes it on to the new user */}
          <Input
            id="temp-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="off"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            className="font-mono"
            required
          />
          <Button type="button" variant="outline" onClick={() => setPassword(generateTempPassword())}>
            {t('users.form.generate')}
          </Button>
        </div>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={loading}>
        {loading ? t('users.form.submitting') : t('users.form.submit')}
      </Button>
    </form>
  )
}
