import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { changePassword } from '@/api/auth'
import { ApiError } from '@/api/client'

import { ChangePasswordPage } from './ChangePasswordPage'

// Only the page is tested here, so the API call is replaced with a spy
vi.mock('@/api/auth', () => ({ changePassword: vi.fn() }))

const changePasswordMock = vi.mocked(changePassword)

function renderPage(forced = false) {
  const onChanged = vi.fn()
  const onCancel = vi.fn()
  render(<ChangePasswordPage forced={forced} onChanged={onChanged} onCancel={onCancel} />)
  return { onChanged, onCancel }
}

async function fillAndSubmit(oldPassword: string, newPassword: string, repeatPassword: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Obecne hasło'), oldPassword)
  await user.type(screen.getByLabelText('Nowe hasło'), newPassword)
  await user.type(screen.getByLabelText('Powtórz nowe hasło'), repeatPassword)
  await user.click(screen.getByRole('button', { name: 'Zmień hasło' }))
}

beforeEach(() => {
  changePasswordMock.mockReset()
})

describe('ChangePasswordPage validation', () => {
  it('rejects a password shorter than 8 characters', async () => {
    renderPage()
    await fillAndSubmit('stare123', 'krotkie', 'krotkie')
    expect(screen.getByRole('alert')).toHaveTextContent('co najmniej 8 znaków')
    expect(changePasswordMock).not.toHaveBeenCalled()
  })

  it('rejects passwords that do not match', async () => {
    renderPage()
    await fillAndSubmit('stare123', 'NoweHaslo1', 'NoweHaslo2')
    expect(screen.getByRole('alert')).toHaveTextContent('nie są takie same')
    expect(changePasswordMock).not.toHaveBeenCalled()
  })

  it('rejects a new password equal to the old one', async () => {
    renderPage()
    await fillAndSubmit('tajne123', 'tajne123', 'tajne123')
    expect(screen.getByRole('alert')).toHaveTextContent('inne niż obecne')
    expect(changePasswordMock).not.toHaveBeenCalled()
  })
})

describe('ChangePasswordPage submit', () => {
  it('sends the passwords and calls onChanged', async () => {
    changePasswordMock.mockResolvedValue(undefined)
    const { onChanged } = renderPage()

    await fillAndSubmit('tajne123', 'NoweHaslo1', 'NoweHaslo1')

    expect(changePasswordMock).toHaveBeenCalledWith('tajne123', 'NoweHaslo1')
    expect(onChanged).toHaveBeenCalledOnce()
  })

  it('shows the backend error and stays on the page', async () => {
    changePasswordMock.mockRejectedValue(new ApiError(400, 'Stare hasło jest nieprawidłowe'))
    const { onChanged } = renderPage()

    await fillAndSubmit('zle', 'NoweHaslo1', 'NoweHaslo1')

    expect(await screen.findByRole('alert')).toHaveTextContent('Stare hasło jest nieprawidłowe')
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('shows a network error for non-API failures', async () => {
    changePasswordMock.mockRejectedValue(new TypeError('Failed to fetch'))
    renderPage()

    await fillAndSubmit('tajne123', 'NoweHaslo1', 'NoweHaslo1')

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia z serwerem')
  })
})

describe('ChangePasswordPage forced mode', () => {
  it('asks for the temporary password and offers logout instead of cancel', async () => {
    const { onCancel } = renderPage(true)

    expect(screen.getByLabelText('Hasło tymczasowe')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Anuluj' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Wyloguj' }))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
