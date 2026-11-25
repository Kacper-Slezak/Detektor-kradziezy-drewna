import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Clock, MessageSquare, Truck, UserRound } from 'lucide-react'
import { cn } from 'cn'

import type { Release } from '@/api/types'
import { STATUS_DOT } from '@/lib/sensor-status'

interface ReleaseCardProps {
  release: Release
  // "until 18:05 · 1 h 20 min left" for an ongoing one, "14.10.2026, 08:00 – 11:20" for history
  when: string
  // who released the timber, and for an ongoing one since when
  who: string
  // the "End muting" button of an ongoing one
  children?: ReactNode
}

// One timber release on the release list: the sensor, when, the carrier and the logs, who
export function ReleaseCard({ release, when, who, children }: ReleaseCardProps) {
  const { t } = useTranslation()

  return (
    <li className="flex flex-col gap-2 rounded-xl bg-card p-4 text-base ring-1 ring-foreground/10">
      <p className="flex items-center gap-2 text-lg leading-snug font-semibold">
        {/* blue like a muted pin on the map, while it lasts */}
        {release.active && <span aria-hidden className={cn('size-3 shrink-0 rounded-full', STATUS_DOT.muted)} />}
        {release.sensor_name ?? release.sensor_id}
      </p>
      <p className="flex items-center gap-2">
        <Clock className="size-5 shrink-0 text-muted-foreground" />
        <span className="tabular-nums">{when}</span>
      </p>
      {(release.carrier || release.log_count !== null) && (
        <p className="flex items-center gap-2 text-muted-foreground">
          <Truck className="size-5 shrink-0" />
          {[release.carrier, release.log_count !== null && t('releases.logs', { count: release.log_count })]
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}
      {release.comment && (
        <p className="flex items-start gap-2 text-muted-foreground">
          <MessageSquare className="mt-0.5 size-5 shrink-0" />
          {t('releases.comment', { comment: release.comment })}
        </p>
      )}
      {who && (
        <p className="flex items-center gap-2 text-muted-foreground">
          <UserRound className="size-5 shrink-0" />
          {who}
        </p>
      )}
      {children}
    </li>
  )
}
