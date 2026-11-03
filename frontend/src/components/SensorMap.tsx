// Map of sensors (Leaflet + OpenStreetMap). Only mounted sensors have a location, so only they get a pin.

import 'leaflet/dist/leaflet.css'

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { divIcon, latLngBounds } from 'leaflet'
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet'
import { cn } from 'cn'

import type { Sensor } from '@/api/types'
import { formatDateTime, LOW_BATTERY_PCT, STATUS_DOT, statusOf, type Status } from '@/lib/sensor-status'

// whole Poland, when there is nothing to show yet
const POLAND_CENTER: [number, number] = [52.1, 19.4]
const POLAND_ZOOM = 6

// one icon per state, built once; the alarm pin is bigger and pulses
const icons = new Map<Status, ReturnType<typeof divIcon>>()
function iconFor(status: Status) {
  let icon = icons.get(status)
  if (!icon) {
    const size = status === 'alarm' ? 22 : 16
    icon = divIcon({
      className: cn('sensor-pin', status === 'alarm' && 'sensor-pin--alarm'),
      html: `<span class="block size-full rounded-full ring-2 ring-white shadow ${STATUS_DOT[status]}"></span>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
      popupAnchor: [0, -size / 2],
    })
    icons.set(status, icon)
  }
  return icon
}

interface SensorMapProps {
  sensors: Sensor[]
  className?: string
}

export function SensorMap({ sensors, className }: SensorMapProps) {
  const { t, i18n } = useTranslation()
  const mounted = useMemo(() => sensors.filter((s) => s.lat !== null && s.lon !== null), [sensors])
  // zoom to fit all pins
  const bounds = useMemo(
    () => (mounted.length ? latLngBounds(mounted.map((s) => [s.lat!, s.lon!])) : undefined),
    [mounted],
  )

  return (
    <MapContainer
      className={cn('z-0 h-full w-full', className)}
      center={bounds ? undefined : POLAND_CENTER}
      zoom={bounds ? undefined : POLAND_ZOOM}
      bounds={bounds}
      boundsOptions={{ padding: [40, 40], maxZoom: 15 }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {mounted.map((sensor) => {
        const status = statusOf(sensor)
        const label = sensor.name ?? sensor.id
        return (
          <Marker
            key={sensor.id}
            position={[sensor.lat!, sensor.lon!]}
            icon={iconFor(status)}
            title={`${label}: ${t(`sensors.status.${status}`)}`}
            // alarms on top of other pins
            zIndexOffset={status === 'alarm' ? 1000 : 0}
          >
            <Popup>
              <div className="flex flex-col gap-1 text-sm">
                <strong>{sensor.name ?? t('sensors.noName')}</strong>
                <span className="font-mono text-xs">{sensor.id}</span>
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden className={cn('size-2 rounded-full', STATUS_DOT[status])} />
                  {t(`sensors.status.${status}`)}
                  {status === 'muted' &&
                    sensor.muted_until &&
                    ` ${t('map.mutedUntil', { time: formatDateTime(sensor.muted_until, i18n.language) })}`}
                </span>
                {sensor.battery_pct !== null && (
                  <span className={cn(sensor.battery_pct < LOW_BATTERY_PCT && 'font-medium text-red-600')}>
                    {t('sensors.table.battery')}: {sensor.battery_pct}%
                  </span>
                )}
                {sensor.last_seen && (
                  <span>
                    {t('sensors.table.lastSeen')}: {formatDateTime(sensor.last_seen, i18n.language)}
                  </span>
                )}
              </div>
            </Popup>
          </Marker>
        )
      })}
    </MapContainer>
  )
}
