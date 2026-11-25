import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { createRelease } from '@/api/releases'
import type { Release, Sensor } from '@/api/types'

import { ReleaseForm } from './ReleaseForm'

// what goes to the backend is checked here; the backend rules are tested in mock.test.ts
vi.mock('@/api/releases', () => ({ createRelease: vi.fn() }))

const sensor: Sensor = {
  id: '70B3D57ED0052345',
  name: 'Skład przy paśniku',
  lat: 50.0598,
  lon: 19.9605,
  range_id: 1,
  active: true,
  state: 'ok',
  battery_pct: 77,
  last_seen: '2026-10-16T10:05:30Z',
  muted_until: null,
  open_alarm_id: null,
}

const HOUR = 60 * 60 * 1000

function renderForm() {
  const onReleased = vi.fn()
  render(<ReleaseForm sensor={sensor} onReleased={onReleased} />)
  return { user: userEvent.setup(), onReleased }
}

// the body of the first createRelease call
const sent = () => vi.mocked(createRelease).mock.calls[0]

beforeEach(() => {
  vi.mocked(createRelease).mockReset()
  vi.mocked(createRelease).mockImplementation(
    async (sensorId, release) => ({ id: 9, sensor_id: sensorId, ends_at: release?.ends_at }) as Release,
  )
})

describe('ReleaseForm', () => {
  it('mutes for 4 h unless the forester picks otherwise', async () => {
    const { user, onReleased } = renderForm()

    expect(screen.getByText('Skład przy paśniku')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '4 h' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/Czujnik zacznie znów czuwać o \d/)).toBeInTheDocument()

    const before = Date.now()
    await user.click(screen.getByRole('button', { name: 'Wycisz' }))

    await vi.waitFor(() => expect(onReleased).toHaveBeenCalledOnce())
    const [sensorId, release] = sent()
    expect(sensorId).toBe('70B3D57ED0052345')
    // nothing optional was typed, so only the end goes
    expect(Object.keys(release!)).toEqual(['ends_at'])
    const hours = (Date.parse(release!.ends_at!) - before) / HOUR
    expect(hours).toBeGreaterThanOrEqual(4)
    expect(hours).toBeLessThan(4.01)
  })

  it('counts the end from the chosen time', async () => {
    const { user } = renderForm()

    await user.click(screen.getByRole('button', { name: '1 h' }))
    expect(screen.getByRole('button', { name: '1 h' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '4 h' })).toHaveAttribute('aria-pressed', 'false')

    const before = Date.now()
    await user.click(screen.getByRole('button', { name: 'Wycisz' }))

    await vi.waitFor(() => expect(createRelease).toHaveBeenCalledOnce())
    const hours = (Date.parse(sent()[1]!.ends_at!) - before) / HOUR
    expect(hours).toBeGreaterThanOrEqual(1)
    expect(hours).toBeLessThan(1.01)
  })

  it('sends the carrier, the logs and the comment, trimmed', async () => {
    const { user } = renderForm()

    await user.type(screen.getByLabelText('Przewoźnik (opcjonalnie)'), '  Trans-Las  ')
    await user.type(screen.getByLabelText('Liczba kłód (opcjonalnie)'), '30')
    await user.type(screen.getByLabelText('Komentarz (opcjonalnie)'), ' zielony MAN ')
    await user.click(screen.getByRole('button', { name: 'Wycisz' }))

    await vi.waitFor(() => expect(createRelease).toHaveBeenCalledOnce())
    expect(sent()[1]).toMatchObject({ carrier: 'Trans-Las', log_count: 30, comment: 'zielony MAN' })
  })

  it('leaves out fields with only spaces in them', async () => {
    const { user } = renderForm()

    await user.type(screen.getByLabelText('Przewoźnik (opcjonalnie)'), '   ')
    await user.click(screen.getByRole('button', { name: 'Wycisz' }))

    await vi.waitFor(() => expect(createRelease).toHaveBeenCalledOnce())
    expect(sent()[1]).not.toHaveProperty('carrier')
  })

  it('shows the backend error and lets the forester try again', async () => {
    vi.mocked(createRelease).mockRejectedValue(
      new ApiError(409, 'Wydanie dla tego czujnika już trwa (id 8); zakończ je albo poczekaj'),
    )
    const { user, onReleased } = renderForm()

    await user.click(screen.getByRole('button', { name: 'Wycisz' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Wydanie dla tego czujnika już trwa')
    expect(screen.getByRole('button', { name: 'Wycisz' })).toBeEnabled()
    expect(onReleased).not.toHaveBeenCalled()
  })
})
