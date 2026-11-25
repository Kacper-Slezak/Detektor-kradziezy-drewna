import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { endRelease, listReleases } from '@/api/releases'
import type { Release, Sensor } from '@/api/types'

import { EndReleaseConfirm } from './EndReleaseConfirm'

vi.mock('@/api/releases', () => ({ listReleases: vi.fn(), endRelease: vi.fn() }))

const sensor: Sensor = {
  id: '70B3D57ED0055678',
  name: 'Skład przy szlabanie',
  lat: 50.0712,
  lon: 19.9533,
  range_id: 1,
  active: true,
  state: 'muted',
  battery_pct: 91,
  last_seen: '2026-10-16T10:01:00Z',
  muted_until: '2026-11-20T18:00:00Z',
  open_alarm_id: null,
}

function renderConfirm() {
  const onEnded = vi.fn()
  const onCancel = vi.fn()
  render(<EndReleaseConfirm sensor={sensor} onEnded={onEnded} onCancel={onCancel} />)
  return { user: userEvent.setup(), onEnded, onCancel }
}

beforeEach(() => {
  vi.mocked(listReleases).mockReset().mockResolvedValue([{ id: 8 } as Release])
  vi.mocked(endRelease).mockReset().mockResolvedValue({ id: 8, active: false } as Release)
})

describe('EndReleaseConfirm', () => {
  it('finds the ongoing release of the sensor and ends it', async () => {
    const { user, onEnded } = renderConfirm()

    expect(screen.getByText('Czujnik „Skład przy szlabanie” znów będzie zgłaszał alarmy.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Zakończ' }))

    await vi.waitFor(() => expect(onEnded).toHaveBeenCalledOnce())
    expect(listReleases).toHaveBeenCalledWith({ sensor_id: '70B3D57ED0055678', active: true })
    expect(endRelease).toHaveBeenCalledWith(8)
  })

  it('ends the given release without looking it up (the release list knows it)', async () => {
    const onEnded = vi.fn()
    render(
      <EndReleaseConfirm
        sensor={{ id: sensor.id, name: sensor.name }}
        releaseId={8}
        onEnded={onEnded}
        onCancel={vi.fn()}
      />,
    )

    await userEvent.setup().click(screen.getByRole('button', { name: 'Zakończ' }))

    await vi.waitFor(() => expect(onEnded).toHaveBeenCalledOnce())
    expect(endRelease).toHaveBeenCalledWith(8)
    expect(listReleases).not.toHaveBeenCalled()
  })

  it('sends nothing when the forester cancels', async () => {
    const { user, onEnded, onCancel } = renderConfirm()

    await user.click(screen.getByRole('button', { name: 'Anuluj' }))

    expect(onCancel).toHaveBeenCalledOnce()
    expect(listReleases).not.toHaveBeenCalled()
    expect(onEnded).not.toHaveBeenCalled()
  })

  it('is done when the release has just run out', async () => {
    vi.mocked(listReleases).mockResolvedValue([])
    const { user, onEnded } = renderConfirm()

    await user.click(screen.getByRole('button', { name: 'Zakończ' }))

    await vi.waitFor(() => expect(onEnded).toHaveBeenCalledOnce())
    expect(endRelease).not.toHaveBeenCalled()
  })

  it('is done when someone else ended it a moment earlier (409)', async () => {
    vi.mocked(endRelease).mockRejectedValue(new ApiError(409, 'Wydanie już się zakończyło'))
    const { user, onEnded } = renderConfirm()

    await user.click(screen.getByRole('button', { name: 'Zakończ' }))

    await vi.waitFor(() => expect(onEnded).toHaveBeenCalledOnce())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows other errors and lets the forester try again', async () => {
    vi.mocked(endRelease).mockRejectedValue(new ApiError(403, 'Czujnik należy do innego leśnictwa'))
    const { user, onEnded } = renderConfirm()

    await user.click(screen.getByRole('button', { name: 'Zakończ' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Czujnik należy do innego leśnictwa')
    expect(screen.getByRole('button', { name: 'Zakończ' })).toBeEnabled()
    expect(onEnded).not.toHaveBeenCalled()
  })
})
