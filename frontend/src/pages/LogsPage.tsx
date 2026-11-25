import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RefreshCw, Search } from 'lucide-react'
import { cn } from 'cn'

import { ApiError } from '@/api/client'
import { listLogs } from '@/api/logs'
import type { LogLevel, LogLine } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { SELECT_CLASS } from '@/lib/select'

const TAIL = 1000
const AUTO_REFRESH_MS = 5000

type LevelFilter = 'all' | 'WARNING' | 'ERROR'

const RANK: Record<LogLevel, number> = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 4 }
const MIN_RANK: Record<LevelFilter, number> = { all: 0, WARNING: 2, ERROR: 3 }

const LEVEL_STYLE: Record<LogLevel, string> = {
  DEBUG: 'bg-muted text-muted-foreground',
  INFO: 'bg-sky-500/15 text-sky-700 dark:text-sky-300',
  WARNING: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  ERROR: 'bg-red-500/15 text-red-700 dark:text-red-300',
  CRITICAL: 'bg-red-600 text-white',
}

// "Logs" section of the admin panel: backend log tail (api.md, GET /admin/logs), newest on top
export function LogsPage() {
  const { t, i18n } = useTranslation()
  const [lines, setLines] = useState<LogLine[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [auto, setAuto] = useState(false)
  const [level, setLevel] = useState<LevelFilter>('all')
  const [search, setSearch] = useState('')

  // state is set only after the response, so it is safe to call from effects
  const fetchLogs = useCallback(
    () =>
      listLogs(TAIL)
        .then((loaded) => {
          setLines(loaded)
          setError(null)
        })
        .catch((err) => {
          if (err instanceof ApiError && err.status === 404) setError(t('logs.disabled'))
          else setError(err instanceof ApiError ? err.message : t('errors.network'))
        })
        .finally(() => setLoading(false)),
    [t],
  )

  function refresh() {
    setLoading(true)
    void fetchLogs()
  }

  useEffect(() => {
    void fetchLogs()
  }, [fetchLogs])

  useEffect(() => {
    if (!auto) return
    const id = window.setInterval(() => void fetchLogs(), AUTO_REFRESH_MS)
    return () => window.clearInterval(id)
  }, [auto, fetchLogs])

  const shown = useMemo(() => {
    const query = search.trim().toLowerCase()
    return (lines ?? [])
      .filter((l) => (RANK[l.level] ?? 0) >= MIN_RANK[level])
      .filter((l) => !query || l.message.toLowerCase().includes(query) || l.logger.toLowerCase().includes(query))
      .reverse()
  }, [lines, level, search])

  const timeFormat = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    [i18n.language],
  )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">{t('logs.title')}</h1>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} className="size-4" />
            {t('logs.auto')}
          </label>
          <Button variant="outline" onClick={refresh} disabled={loading}>
            <RefreshCw className={cn(loading && 'animate-spin')} />
            {t('logs.refresh')}
          </Button>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{t('logs.note')}</p>

      <Card className="gap-0 py-0">
        <div className="flex flex-wrap items-center gap-2 border-b p-3">
          <div className="flex min-w-48 flex-1 items-center gap-2">
            <Search className="size-4 shrink-0 text-muted-foreground" />
            <Input
              type="search"
              aria-label={t('logs.search')}
              placeholder={t('logs.search')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
            />
          </div>
          <select
            aria-label={t('logs.level')}
            value={level}
            onChange={(e) => setLevel(e.target.value as LevelFilter)}
            className={cn(SELECT_CLASS, 'w-auto')}
          >
            {(['all', 'WARNING', 'ERROR'] as const).map((l) => (
              <option key={l} value={l}>
                {t(`logs.levels.${l}`)}
              </option>
            ))}
          </select>
        </div>

        {error ? (
          <p role="alert" className="p-4 text-sm text-destructive">
            {error}
          </p>
        ) : lines === null ? (
          <p role="status" className="p-4 text-muted-foreground">
            {t('app.loading')}
          </p>
        ) : shown.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">{t('logs.empty')}</p>
        ) : (
          <ol aria-label={t('logs.title')} className="max-h-[70svh] divide-y overflow-y-auto font-mono text-xs">
            {shown.map((line, i) => (
              <li key={`${line.time}-${i}`} className="flex gap-3 px-3 py-1.5 hover:bg-muted/40">
                <time
                  dateTime={line.time}
                  title={new Date(line.time).toLocaleString(i18n.language)}
                  className="shrink-0 text-muted-foreground tabular-nums"
                >
                  {timeFormat.format(new Date(line.time))}
                </time>
                <span className={cn('h-fit w-16 shrink-0 rounded px-1 text-center font-semibold', LEVEL_STYLE[line.level])}>
                  {line.level}
                </span>
                <div className="min-w-0 flex-1">
                  <span className="text-muted-foreground">{line.logger}</span>{' '}
                  <span className="break-words whitespace-pre-wrap">{line.message}</span>
                </div>
              </li>
            ))}
          </ol>
        )}
        {lines !== null && !error && (
          <p className="border-t px-3 py-2 text-xs text-muted-foreground">
            {t('logs.count', { shown: shown.length, total: lines.length })}
          </p>
        )}
      </Card>
    </div>
  )
}
