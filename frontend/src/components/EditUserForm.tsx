import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api/client'
import type { ManagedUser, Range, Role, UserChanges } from '@/api/types'
import { resetPassword, updateUser } from '@/api/users'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SELECT_CLASS } from '@/lib/select'

const ROLES: Role[] = ['forester', 'district_manager', 'admin']

interface EditUserFormProps {
  user: ManagedUser
  ranges: Range[]
  // the admin cannot deactivate or demote their own account (the backend says 409)
  isSelf: boolean
  onSaved: (user: ManagedUser) => void
  // password is passed separately, because the backend returns it only once
  onPasswordReset: (user: ManagedUser, password: string) => void
}

export function EditUserForm({ user, ranges, isSelf, onSaved, onPasswordReset }: EditUserFormProps) {
  const { t } = useTranslation()
  const [fullName, setFullName] = useState(user.full_name)
  const [role, setRole] = useState<Role>(user.role)
  const [rangeId, setRangeId] = useState(user.range_id === null ? '' : String(user.range_id))
  const [active, setActive] = useState(user.active)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  // resetting makes the old password stop working, so it asks once more
  const [confirmingReset, setConfirmingReset] = useState(false)

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)

    if (role === 'forester' && !rangeId) {
      setError(t('users.form.errors.rangeRequired'))
      return
    }

    // only a forester belongs to a range
    const newRangeId = role === 'forester' ? Number(rangeId) : null
    // send only what changed, like the PATCH in api.md expects
    const changes: UserChanges = {}
    if (fullName.trim() !== user.full_name) changes.full_name = fullName.trim()
    if (role !== user.role) changes.role = role
    if (newRangeId !== user.range_id) changes.range_id = newRangeId
    if (active !== user.active) changes.active = active

    setLoading(true)
    try {
      onSaved(Object.keys(changes).length ? await updateUser(user.id, changes) : user)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'))
    } finally {
      setLoading(false)
    }
  }

  async function handleReset() {
    setError(null)
    setLoading(true)
    try {
      const password = await resetPassword(user.id)
      onPasswordReset({ ...user, must_change_password: true }, password)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'))
      setConfirmingReset(false)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {/* the login never changes, so it is plain text, not a field */}
        <dl className="flex flex-col gap-1">
          <dt className="text-sm font-medium">{t('users.form.login')}</dt>
          <dd className="font-mono">{user.login}</dd>
        </dl>
        <div className="flex flex-col gap-2">
          <Label htmlFor="edit-full-name">{t('users.form.fullName')}</Label>
          <Input
            id="edit-full-name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            maxLength={100}
            required
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="edit-role">{t('users.form.role')}</Label>
          <select
            id="edit-role"
            className={SELECT_CLASS}
            value={role}
            disabled={isSelf}
            onChange={(e) => setRole(e.target.value as Role)}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {t(`role.${r}`)}
              </option>
            ))}
          </select>
        </div>
        {role === 'forester' && (
          <div className="flex flex-col gap-2">
            <Label htmlFor="edit-range">{t('users.form.range')}</Label>
            <select
              id="edit-range"
              className={SELECT_CLASS}
              value={rangeId}
              onChange={(e) => setRangeId(e.target.value)}
            >
              <option value="">{t('users.form.chooseRange')}</option>
              {ranges.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <input
              id="edit-active"
              type="checkbox"
              className="size-4 accent-primary"
              checked={active}
              disabled={isSelf}
              onChange={(e) => setActive(e.target.checked)}
            />
            <Label htmlFor="edit-active">{t('users.edit.active')}</Label>
          </div>
          <p className="text-xs text-muted-foreground">
            {isSelf ? t('users.edit.selfHint') : t('users.edit.activeHint')}
          </p>
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" disabled={loading}>
          {loading ? t('users.edit.saving') : t('users.edit.save')}
        </Button>
      </form>

      <section aria-labelledby="reset-heading" className="flex flex-col gap-2 border-t pt-4">
        <h3 id="reset-heading" className="text-sm font-medium">
          {t('users.edit.resetTitle')}
        </h3>
        <p className="text-xs text-muted-foreground">{t('users.edit.resetHint')}</p>
        {confirmingReset ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="destructive" disabled={loading} onClick={handleReset}>
              {t('users.edit.resetConfirm')}
            </Button>
            <Button variant="ghost" disabled={loading} onClick={() => setConfirmingReset(false)}>
              {t('users.edit.resetCancel')}
            </Button>
          </div>
        ) : (
          <Button variant="outline" className="self-start" onClick={() => setConfirmingReset(true)}>
            {t('users.edit.reset')}
          </Button>
        )}
      </section>
    </div>
  )
}
