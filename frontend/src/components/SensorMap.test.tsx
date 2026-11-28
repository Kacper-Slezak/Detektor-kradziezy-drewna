import { StrictMode } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Sensor } from '@/api/types'
import { SensorMap } from './SensorMap'

const base: Sensor = {
  id: '70B3D57ED0051234',
  name: 'Skład przy drodze 5',
  lat: 50.0647,
  lon: 19.945,
  range_id: 1,
  active: true,
  state: 'alarm',
  battery_pct: 64,
  last_seen: '2026-10-16T09:58:12Z',
  muted_until: null,
  open_alarm_id: 41,
}

const sensors: Sensor[] = [
  base,
  { ...base, id: '70B3D57ED0055678', name: 'Skład przy szlabanie', lat: 50.07, lon: 19.95, state: 'ok', battery_pct: 9 },
  { ...base, id: '70B3D57ED0059ABC', name: null, lat: null, lon: null, state: 'inactive' },
]

// Leaflet takes two taps within 200 ms for a double tap and zooms in, which jsdom cannot
// lay out (Invalid LatLng). A person never taps the pin and the popup button that fast.
const afterTap = () => new Promise((resolve) => setTimeout(resolve, 250))

describe('SensorMap', () => {
  it('puts a pin for every mounted sensor, labelled with its name and state', () => {
    render(<SensorMap sensors={sensors} />)

    expect(screen.getByTitle('Skład przy drodze 5: Alarm')).toBeInTheDocument()
    expect(screen.getByTitle('Skład przy szlabanie: Działa')).toBeInTheDocument()
    // no location, no pin
    expect(screen.queryByTitle(/70B3D57ED0059ABC/)).not.toBeInTheDocument()
  })

  it('makes the alarm pin bigger and pulsing', () => {
    render(<SensorMap sensors={sensors} />)

    expect(screen.getByTitle('Skład przy drodze 5: Alarm')).toHaveClass('sensor-pin--alarm')
    expect(screen.getByTitle('Skład przy szlabanie: Działa')).not.toHaveClass('sensor-pin--alarm')
  })

  it('shows details of a sensor after clicking its pin', async () => {
    const user = userEvent.setup()
    render(<SensorMap sensors={sensors} />)

    await user.click(screen.getByTitle('Skład przy szlabanie: Działa'))

    expect(await screen.findByText('70B3D57ED0055678')).toBeInTheDocument()
    expect(screen.getByText('Bateria: 9%')).toHaveClass('text-red-600')
  })

  it('opens the popup of the sensor from the address at once, e.g. after a push', async () => {
    render(<SensorMap sensors={sensors} focusId="70B3D57ED0055678" />)

    // no click: the popup of this pin is already open, the other one is not
    expect(await screen.findByText('70B3D57ED0055678')).toBeInTheDocument()
    expect(screen.getByText('Bateria: 9%')).toBeInTheDocument()
    expect(screen.queryByText('70B3D57ED0051234')).not.toBeInTheDocument()
  })

  // the app runs in StrictMode, which mounts everything twice in development
  it('keeps that popup open in StrictMode too', async () => {
    render(
      <StrictMode>
        <SensorMap sensors={sensors} focusId="70B3D57ED0055678" />
      </StrictMode>,
    )

    expect(await screen.findByText('70B3D57ED0055678')).toBeInTheDocument()
  })

  it('opens nothing for a sensor that is not on the map', async () => {
    render(<SensorMap sensors={sensors} focusId="70B3D57ED0059ABC" />)

    await afterTap()
    expect(screen.queryByText('70B3D57ED0059ABC')).not.toBeInTheDocument()
    expect(screen.queryByText(/Bateria/)).not.toBeInTheDocument()
  })

  it('lets the page move a sensor from its pin', async () => {
    const user = userEvent.setup()
    const onMove = vi.fn()
    render(<SensorMap sensors={sensors} onMove={onMove} />)

    await user.click(screen.getByTitle('Skład przy szlabanie: Działa'))
    const move = await screen.findByRole('button', { name: 'Przenieś czujnik' })
    await afterTap()
    await user.click(move)

    expect(onMove).toHaveBeenCalledWith(sensors[1])
  })

  it('has no move button when the page does not allow it', async () => {
    const user = userEvent.setup()
    render(<SensorMap sensors={sensors} />)

    await user.click(screen.getByTitle('Skład przy szlabanie: Działa'))

    expect(await screen.findByText('70B3D57ED0055678')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Przenieś czujnik' })).not.toBeInTheDocument()
  })

  describe('muting for timber pickup', () => {
    const noop = () => {}
    // one pin of each kind: watching, muted, alarm while muted, switched off
    const pins: Sensor[] = [
      { ...base, id: 'A1', name: 'Czuwa', state: 'ok', open_alarm_id: null },
      { ...base, id: 'A2', name: 'Wyciszony', lat: 50.07, state: 'muted', muted_until: '2026-11-20T18:00:00Z', open_alarm_id: null },
      { ...base, id: 'A3', name: 'Alarm w trakcie wywozu', lat: 50.08, muted_until: '2026-11-20T18:00:00Z' },
      { ...base, id: 'A4', name: 'Wyłączony', lat: 50.09, active: false, state: 'inactive', open_alarm_id: null },
    ]

    async function openPin(title: string, props = { onRelease: vi.fn(), onEndRelease: vi.fn() }) {
      const user = userEvent.setup()
      render(<SensorMap sensors={pins} {...props} />)
      await user.click(screen.getByTitle(title))
      await screen.findByText(title.split(':')[0], { selector: 'strong' })
      await afterTap()
      return { user, ...props }
    }

    it('offers muting a watching sensor', async () => {
      const { user, onRelease } = await openPin('Czuwa: Działa')

      expect(screen.queryByRole('button', { name: 'Zakończ wyciszenie' })).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Wycisz na czas wywozu' }))
      expect(onRelease).toHaveBeenCalledWith(pins[0])
    })

    it('offers ending the muting of a muted sensor', async () => {
      const { user, onEndRelease } = await openPin('Wyciszony: Wyciszony')

      expect(screen.queryByRole('button', { name: 'Wycisz na czas wywozu' })).not.toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Zakończ wyciszenie' }))
      expect(onEndRelease).toHaveBeenCalledWith(pins[1])
    })

    it('knows a red pin is muted too when an alarm came before the release', async () => {
      await openPin('Alarm w trakcie wywozu: Alarm')
      expect(screen.getByRole('button', { name: 'Zakończ wyciszenie' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Wycisz na czas wywozu' })).not.toBeInTheDocument()
    })

    it('has nothing to mute on a switched-off sensor', async () => {
      await openPin('Wyłączony: Wyłączony')
      expect(screen.queryByRole('button', { name: 'Wycisz na czas wywozu' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Zakończ wyciszenie' })).not.toBeInTheDocument()
    })

    it('has no muting buttons when the page does not allow it', async () => {
      const user = userEvent.setup()
      render(<SensorMap sensors={pins} onMove={noop} />)
      await user.click(screen.getByTitle('Czuwa: Działa'))

      expect(await screen.findByRole('button', { name: 'Przenieś czujnik' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Wycisz na czas wywozu' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Zakończ wyciszenie' })).not.toBeInTheDocument()
    })
  })

  it('gives a pin a new title when its state changes', () => {
    const { rerender } = render(<SensorMap sensors={[{ ...base, state: 'ok', open_alarm_id: null }]} />)
    expect(screen.getByTitle('Skład przy drodze 5: Działa')).toBeInTheDocument()

    rerender(<SensorMap sensors={[{ ...base, state: 'muted', open_alarm_id: null }]} />)
    expect(screen.getByTitle('Skład przy drodze 5: Wyciszony')).toBeInTheDocument()
    expect(screen.queryByTitle('Skład przy drodze 5: Działa')).not.toBeInTheDocument()
  })

  it('shows the map without pins when there are no sensors', () => {
    const { container } = render(<SensorMap sensors={[]} />)

    expect(container.querySelector('.leaflet-container')).toBeInTheDocument()
    expect(container.querySelector('.sensor-pin')).not.toBeInTheDocument()
  })
})
