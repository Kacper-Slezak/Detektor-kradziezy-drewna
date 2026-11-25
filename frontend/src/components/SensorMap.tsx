// Map of sensors (Leaflet + OpenStreetMap). Only mounted sensors have a location, so only they get a pin.

import 'leaflet/dist/leaflet.css'

import { useEffect, useMemo, useRef, type RefObject } from 'react'
import { useTranslation } from 'react-i18next'
import { divIcon, latLngBounds, type Marker as LeafletMarker } from 'leaflet'
import { MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import { Bell, BellOff, MoveRight } from 'lucide-react'
import { cn } from 'cn'

import type { Sensor } from '@/api/types'
import { Button } from '@/components/ui/button'
import { formatDateTime, LOW_BATTERY_PCT, STATUS_DOT, statusOf, type Status } from '@/lib/sensor-status'

// whole Poland, when there is nothing to show yet
const POLAND_CENTER: [number, number] = [52.1, 19.4]
const POLAND_ZOOM = 6
// close enough to see the stack the sensor is on
const FOCUS_ZOOM = 16

// big enough to hit with a thumb (about 44 px)
const POPUP_BUTTON = 'h-11 text-base [&_svg]:size-5!'

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

// Zooms to one pin and opens its popup. Depends on plain values, not the sensor object, so a
// refresh of the sensors does not make the map jump back while the forester looks around.
// No "done" flag: StrictMode mounts the pins twice, and the second time the popup must open again.
function FocusPin({ sensor, markers }: { sensor: Sensor | undefined; markers: RefObject<Map<string, LeafletMarker>> }) {
  const map = useMap()
  const id = sensor?.id
  const lat = sensor?.lat
  const lon = sensor?.lon
  useEffect(() => {
    if (!id || lat == null || lon == null) return
    map.setView([lat, lon], Math.max(map.getZoom(), FOCUS_ZOOM), { animate: false })
    markers.current.get(id)?.openPopup()
  }, [map, id, lat, lon, markers])
  return null
}

interface SensorMapProps {
  sensors: Sensor[]
  className?: string
  // the sensor to show at once, e.g. from a push about its battery (address /sensors/<id>)
  focusId?: string | null
  // given only to those who may move a sensor (the page decides by role)
  onMove?: (sensor: Sensor) => void
  // the same for muting a sensor while the timber is taken away, and for ending it early
  onRelease?: (sensor: Sensor) => void
  onEndRelease?: (sensor: Sensor) => void
}

export function SensorMap({ sensors, className, focusId, onMove, onRelease, onEndRelease }: SensorMapProps) {
  const { t, i18n } = useTranslation()
  const mounted = useMemo(() => sensors.filter((s) => s.lat !== null && s.lon !== null), [sensors])
  // the Leaflet pins by sensor id, so the focused one can open its popup
  const markers = useRef(new Map<string, LeafletMarker>())
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
            // react-leaflet sets the title only when the pin is created, so a new state makes a new pin
            key={`${sensor.id}-${status}`}
            ref={(marker) => {
              if (marker) markers.current.set(sensor.id, marker)
            }}
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
                {/* muted_until, not the state: a sensor with an open alarm stays red while muted */}
                {sensor.muted_until
                  ? onEndRelease && (
                      <Button variant="outline" className={cn(POPUP_BUTTON, 'mt-1')} onClick={() => onEndRelease(sensor)}>
                        <Bell />
                        {t('release.end')}
                      </Button>
                    )
                  : // a switched-off sensor sends no alarms, so there is nothing to mute
                    sensor.active &&
                    onRelease && (
                      <Button className={cn(POPUP_BUTTON, 'mt-1')} onClick={() => onRelease(sensor)}>
                        <BellOff />
                        {t('release.open')}
                      </Button>
                    )}
                {onMove && (
                  <Button variant="outline" className={cn(POPUP_BUTTON, 'mt-1')} onClick={() => onMove(sensor)}>
                    <MoveRight />
                    {t('mount.move')}
                  </Button>
                )}
              </div>
            </Popup>
          </Marker>
        )
      })}
      <FocusPin sensor={focusId ? mounted.find((s) => s.id === focusId) : undefined} markers={markers} />
    </MapContainer>
  )
}
