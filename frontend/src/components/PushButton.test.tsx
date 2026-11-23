import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { enablePush, getPushState } from '@/lib/push'

import { PushButton } from './PushButton'

// the browser part is tested in lib/push.test.ts; here only what the forester sees
vi.mock('@/lib/push', () => ({ getPushState: vi.fn(), enablePush: vi.fn() }))

beforeEach(() => {
  vi.mocked(getPushState).mockReset()
  vi.mocked(enablePush).mockReset()
})

describe('PushButton', () => {
  it('turns notifications on after a click', async () => {
    vi.mocked(getPushState).mockResolvedValue('disabled')
    vi.mocked(enablePush).mockResolvedValue('enabled')
    render(<PushButton />)

    const button = await screen.findByRole('button', { name: 'Włącz powiadomienia o alarmach' })
    // nothing is asked before the click
    expect(enablePush).not.toHaveBeenCalled()
    await userEvent.setup().click(button)

    expect(await screen.findByRole('status')).toHaveTextContent('Powiadomienia o alarmach włączone')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('stays off when the forester says no in the question', async () => {
    vi.mocked(getPushState).mockResolvedValue('disabled')
    vi.mocked(enablePush).mockResolvedValue('disabled')
    render(<PushButton />)

    await userEvent.setup().click(await screen.findByRole('button', { name: 'Włącz powiadomienia o alarmach' }))

    expect(await screen.findByRole('button', { name: 'Włącz powiadomienia o alarmach' })).toBeEnabled()
  })

  it('says where to unblock notifications', async () => {
    vi.mocked(getPushState).mockResolvedValue('denied')
    render(<PushButton />)

    expect(await screen.findByText(/Powiadomienia są zablokowane/)).toHaveTextContent('kłódka przy adresie')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('says when the device has no notifications', async () => {
    vi.mocked(getPushState).mockResolvedValue('unsupported')
    render(<PushButton />)

    expect(await screen.findByText('To urządzenie nie obsługuje powiadomień.')).toBeInTheDocument()
  })

  it('sends the subscription again quietly when notifications are already on', async () => {
    vi.mocked(getPushState).mockResolvedValue('enabled')
    vi.mocked(enablePush).mockResolvedValue('enabled')
    render(<PushButton />)

    expect(await screen.findByRole('status')).toHaveTextContent('Powiadomienia o alarmach włączone')
    // another forester may have signed in on this phone: the backend learns the new owner
    expect(enablePush).toHaveBeenCalledOnce()
  })

  it.each([
    [new ApiError(403, 'Powiadomienia push są tylko dla leśniczych'), 'Powiadomienia push są tylko dla leśniczych'],
    [new DOMException('Registration failed', 'AbortError'), 'Nie udało się włączyć powiadomień. Spróbuj ponownie.'],
  ])('shows the error and lets the forester try again (%s)', async (error, message) => {
    vi.mocked(getPushState).mockResolvedValue('disabled')
    vi.mocked(enablePush).mockRejectedValue(error)
    render(<PushButton />)

    await userEvent.setup().click(await screen.findByRole('button', { name: 'Włącz powiadomienia o alarmach' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByRole('button', { name: 'Włącz powiadomienia o alarmach' })).toBeEnabled()
  })
})
