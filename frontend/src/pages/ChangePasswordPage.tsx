import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { changePassword } from '@/api/auth'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const MIN_PASSWORD_LENGTH = 8

interface ChangePasswordPageProps {
  forced: boolean
  onChanged: () => void
  onCancel: () => void
}

export function ChangePasswordPage({ forced, onChanged, onCancel }: ChangePasswordPageProps) {
  const { t } = useTranslation()
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [repeatPassword, setRepeatPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)

    // Quick check in the browser; the backend does the final validation
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setError(t('changePassword.errors.tooShort', { count: MIN_PASSWORD_LENGTH }))
      return
    }
    if (newPassword !== repeatPassword) {
      setError(t('changePassword.errors.mismatch'))
      return
    }
    if (newPassword === oldPassword) {
      setError(t('changePassword.errors.sameAsOld'))
      return
    }

    setLoading(true)
    try {
      await changePassword(oldPassword, newPassword)
      onChanged()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">{t('changePassword.title')}</CardTitle>
          <CardDescription>
            {forced ? t('changePassword.forcedDescription') : t('changePassword.description')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="old-password">
                {forced ? t('changePassword.temporaryPassword') : t('changePassword.oldPassword')}
              </Label>
              <Input
                id="old-password"
                type="password"
                autoComplete="current-password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="new-password">{t('changePassword.newPassword')}</Label>
              <Input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="repeat-password">{t('changePassword.repeatPassword')}</Label>
              <Input
                id="repeat-password"
                type="password"
                autoComplete="new-password"
                value={repeatPassword}
                onChange={(e) => setRepeatPassword(e.target.value)}
                required
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" disabled={loading}>
              {loading ? t('changePassword.submitting') : t('changePassword.submit')}
            </Button>
            <Button type="button" variant="ghost" onClick={onCancel} disabled={loading}>
              {forced ? t('home.logout') : t('changePassword.cancel')}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
