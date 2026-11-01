import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

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

  it('shows the map without pins when there are no sensors', () => {
    const { container } = render(<SensorMap sensors={[]} />)

    expect(container.querySelector('.leaflet-container')).toBeInTheDocument()
    expect(container.querySelector('.sensor-pin')).not.toBeInTheDocument()
  })
})
