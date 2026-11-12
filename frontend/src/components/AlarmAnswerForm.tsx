import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { CircleCheck, ShieldAlert } from 'lucide-react'

import { respondToAlarm } from '@/api/alarms'
import { ApiError } from '@/api/client'
import type { Alarm, AlarmResult } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'

const COMMENT_MAX = 500

// big enough to hit with a thumb in the forest
const BIG = 'h-12 text-base [&_svg]:size-5!'

interface AlarmAnswerFormProps {
  alarm: Alarm
  onAnswered: (alarm: Alarm) => void
  // 409: someone answered first; the list loads again and this alarm may leave it, so the page shows the message
  onConflict: (message: string) => void
}

// Under a new alarm: "theft" or "false alarm". The choice is confirmed in a second step,
// so a stray tap in a pocket does not close the alarm
export function AlarmAnswerForm({ alarm, onAnswered, onConflict }: AlarmAnswerFormProps) {
  const { t } = useTranslation()
  const commentId = useId()
  const [result, setResult] = useState<AlarmResult | null>(null)
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!result) return
    setSubmitting(true)
    setError(null)
    try {
      const trimmed = comment.trim()
      onAnswered(await respondToAlarm(alarm.id, { result, ...(trimmed && { comment: trimmed }) }))
    } catch (err) {
      setSubmitting(false)
      if (err instanceof ApiError && err.status === 409) return onConflict(err.message)
      setError(err instanceof ApiError ? err.message : t('errors.network'))
    }
  }

  if (!result) {
    return (
      <div role="group" aria-label={t('alarms.answer.question')} className="grid grid-cols-2 gap-2 border-t pt-3">
        <Button variant="destructive" className={BIG} onClick={() => setResult('theft')}>
          <ShieldAlert />
          {t('alarms.answer.theft')}
        </Button>
        <Button variant="outline" className={BIG} onClick={() => setResult('false_alarm')}>
          <CircleCheck />
          {t('alarms.answer.falseAlarm')}
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 border-t pt-3">
      <p className="font-semibold">
        {t(result === 'theft' ? 'alarms.answer.confirmTheft' : 'alarms.answer.confirmFalseAlarm')}
      </p>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={commentId}>{t('alarms.answer.comment')}</Label>
        <textarea
          id={commentId}
          rows={2}
          maxLength={COMMENT_MAX}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder={t(result === 'theft' ? 'alarms.answer.theftHint' : 'alarms.answer.falseAlarmHint')}
          className="w-full rounded-lg border border-input bg-transparent px-3 py-2 text-base outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        />
      </div>
      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
      <div className="grid grid-cols-2 gap-2">
        <Button
          type="button"
          variant="outline"
          className={BIG}
          disabled={submitting}
          onClick={() => {
            setResult(null)
            setError(null)
          }}
        >
          {t('alarms.answer.cancel')}
        </Button>
        <Button type="submit" variant={result === 'theft' ? 'destructive' : 'default'} className={BIG} disabled={submitting}>
          {t(submitting ? 'alarms.answer.saving' : 'alarms.answer.save')}
        </Button>
      </div>
    </form>
  )
}
