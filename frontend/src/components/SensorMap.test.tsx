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

  it('shows the map without pins when there are no sensors', () => {
    const { container } = render(<SensorMap sensors={[]} />)

    expect(container.querySelector('.leaflet-container')).toBeInTheDocument()
    expect(container.querySelector('.sensor-pin')).not.toBeInTheDocument()
  })
})
