import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { setToken } from '@/api/client'
import type { Sensor } from '@/api/types'
import { getPosition, PositionFailure } from '@/lib/geolocation'

import { MountSensorForm } from './MountSensorForm'

// the phone's GPS is faked; the rest of geolocation.ts stays real
vi.mock('@/lib/geolocation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/geolocation')>()),
  getPosition: vi.fn(),
}))

const unmounted: Sensor = {
  id: '70B3D57ED005A1B2',
  name: null,
  lat: null,
  lon: null,
  range_id: 1,
  active: false,
  state: 'inactive',
  battery_pct: null,
  last_seen: null,
  muted_until: null,
  open_alarm_id: null,
}

function renderForm(sensors: Sensor[] = [unmounted]) {
  const onMounted = vi.fn()
  render(<MountSensorForm sensors={sensors} onMounted={onMounted} />)
  return { user: userEvent.setup(), onMounted }
}

beforeEach(() => {
  // the forester of Dąbrowa
  setToken('mock-3')
  vi.mocked(getPosition).mockResolvedValue({ lat: 50.061234, lon: 19.951234, accuracy: 8.4 })
})

describe('MountSensorForm', () => {
  it('mounts the only sensor with a name and the phone location', async () => {
    const { user, onMounted } = renderForm()
    const save = screen.getByRole('button', { name: 'Zapisz' })

    // a single sensor is chosen already; saving waits for the name and the location
    expect(screen.getByLabelText('Czujnik')).toHaveValue('70B3D57ED005A1B2')
    expect(save).toBeDisabled()

    await user.type(screen.getByLabelText('Nazwa'), 'Skład przy brzozach')
    await user.click(screen.getByRole('button', { name: 'Pobierz pozycję' }))
    expect(await screen.findByText('50.06123, 19.95123 · ±8 m')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pobierz ponownie' })).toBeInTheDocument()
    expect(screen.queryByText(/Słaba dokładność/)).not.toBeInTheDocument()

    await user.click(save)
    await vi.waitFor(() => expect(onMounted).toHaveBeenCalledOnce())
    expect(onMounted.mock.calls[0][0]).toMatchObject({
      id: '70B3D57ED005A1B2',
      name: 'Skład przy brzozach',
      lat: 50.061234,
      lon: 19.951234,
      active: true,
    })
  })

  it('warns about poor accuracy but still lets the forester save', async () => {
    vi.mocked(getPosition).mockResolvedValue({ lat: 50.06, lon: 19.95, accuracy: 120 })
    const { user } = renderForm()

    await user.type(screen.getByLabelText('Nazwa'), 'Skład')
    await user.click(screen.getByRole('button', { name: 'Pobierz pozycję' }))

    expect(await screen.findByText('Słaba dokładność, spróbuj ponownie na otwartym terenie')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Zapisz' })).toBeEnabled()
  })

  it('says why there is no location', async () => {
    vi.mocked(getPosition).mockRejectedValue(new PositionFailure('denied'))
    const { user } = renderForm()

    await user.click(screen.getByRole('button', { name: 'Pobierz pozycję' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak zgody na lokalizację')
    expect(screen.getByRole('button', { name: 'Zapisz' })).toBeDisabled()
  })

  it('takes the name the admin gave when choosing from several sensors', async () => {
    const { user } = renderForm([unmounted, { ...unmounted, id: '70B3D57ED0059ABC', name: 'Skład przy stawie' }])

    expect(screen.getByLabelText('Czujnik')).toHaveValue('')
    await user.selectOptions(screen.getByLabelText('Czujnik'), '70B3D57ED0059ABC')

    expect(screen.getByLabelText('Nazwa')).toHaveValue('Skład przy stawie')
  })

  it('shows the backend error', async () => {
    // a forester of another range
    setToken('mock-5')
    const { user, onMounted } = renderForm()

    await user.type(screen.getByLabelText('Nazwa'), 'Skład')
    await user.click(screen.getByRole('button', { name: 'Pobierz pozycję' }))
    await user.click(await screen.findByRole('button', { name: 'Zapisz' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Czujnik jest w innym leśnictwie')
    expect(onMounted).not.toHaveBeenCalled()
  })
})
