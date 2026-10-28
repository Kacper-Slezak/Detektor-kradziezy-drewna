import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { setToken } from '@/api/client'

// Creating an account edits mock state, so every test loads a fresh page and mock
let UsersPage: typeof import('./UsersPage').UsersPage

beforeEach(async () => {
  vi.resetModules()
  UsersPage = (await import('./UsersPage')).UsersPage
})

async function renderAsAdmin() {
  setToken('mock-1')
  render(<UsersPage onBack={() => {}} />)
  // wait for the list and the ranges from the mock
  await screen.findByText('Błażej Kowalski')
  return userEvent.setup()
}

describe('UsersPage', () => {
  it('lists accounts with role and range', async () => {
    await renderAsAdmin()
    expect(screen.getByText('blazej · Leśniczy · Leśnictwo Dąbrowa')).toBeInTheDocument()
    expect(screen.getByText('bogdan · Nadleśniczy')).toBeInTheDocument()
    expect(screen.getByText('Hasło tymczasowe nie zostało jeszcze zmienione')).toBeInTheDocument()
  })

  it('fills the login from the full name until it is edited', async () => {
    const user = await renderAsAdmin()
    const login = screen.getByLabelText('Login')

    await user.type(screen.getByLabelText('Imię i nazwisko'), 'Błażej Nowak')
    expect(login).toHaveValue('blazej.nowak')

    await user.clear(login)
    await user.type(login, 'bnowak')
    await user.type(screen.getByLabelText('Imię i nazwisko'), 'owski')
    expect(login).toHaveValue('bnowak')
  })

  it('creates a forester and shows the login and password once', async () => {
    const user = await renderAsAdmin()

    await user.type(screen.getByLabelText('Imię i nazwisko'), 'Anna Las')
    await user.selectOptions(screen.getByLabelText('Leśnictwo'), 'Leśnictwo Olszyny')
    await user.click(screen.getByRole('button', { name: 'Wylosuj' }))
    const password = (screen.getByLabelText('Hasło tymczasowe') as HTMLInputElement).value
    expect(password).toMatch(/^\w{4}-\w{4}-\w{4}$/)
    await user.click(screen.getByRole('button', { name: 'Utwórz konto' }))

    const created = await screen.findByRole('status')
    expect(created).toHaveTextContent('Konto utworzone')
    expect(created).toHaveTextContent('anna.las')
    expect(created).toHaveTextContent(password)
    expect(screen.getByText('anna.las · Leśniczy · Leśnictwo Olszyny')).toBeInTheDocument()
    // the form is cleared for the next account
    expect(screen.getByLabelText('Imię i nazwisko')).toHaveValue('')

    await user.click(screen.getByRole('button', { name: 'Kopiuj' }))
    expect(await navigator.clipboard.readText()).toBe(`Login: anna.las\nHasło: ${password}`)
    expect(screen.getByRole('button', { name: 'Skopiowano' })).toBeInTheDocument()
  })

  it('does not ask for a range for a district manager', async () => {
    const user = await renderAsAdmin()

    await user.selectOptions(screen.getByLabelText('Rola'), 'Nadleśniczy')
    expect(screen.queryByLabelText('Leśnictwo')).not.toBeInTheDocument()

    await user.type(screen.getByLabelText('Imię i nazwisko'), 'Ewa Bór')
    await user.type(screen.getByLabelText('Hasło tymczasowe'), 'Haslo1234')
    await user.click(screen.getByRole('button', { name: 'Utwórz konto' }))

    expect(await screen.findByText('ewa.bor · Nadleśniczy')).toBeInTheDocument()
  })

  it('requires a range for a forester', async () => {
    const user = await renderAsAdmin()

    await user.type(screen.getByLabelText('Imię i nazwisko'), 'Anna Las')
    await user.type(screen.getByLabelText('Hasło tymczasowe'), 'Haslo1234')
    await user.click(screen.getByRole('button', { name: 'Utwórz konto' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Leśniczy musi mieć przypisane leśnictwo')
  })

  it('rejects a short password', async () => {
    const user = await renderAsAdmin()

    await user.type(screen.getByLabelText('Imię i nazwisko'), 'Anna Las')
    await user.selectOptions(screen.getByLabelText('Leśnictwo'), 'Leśnictwo Olszyny')
    await user.type(screen.getByLabelText('Hasło tymczasowe'), 'krotkie')
    await user.click(screen.getByRole('button', { name: 'Utwórz konto' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Hasło musi mieć co najmniej 8 znaków')
  })

  it('shows the backend error for a taken login', async () => {
    const user = await renderAsAdmin()

    await user.type(screen.getByLabelText('Imię i nazwisko'), 'Błażej Kowalski')
    await user.clear(screen.getByLabelText('Login'))
    await user.type(screen.getByLabelText('Login'), 'blazej')
    await user.selectOptions(screen.getByLabelText('Leśnictwo'), 'Leśnictwo Dąbrowa')
    await user.type(screen.getByLabelText('Hasło tymczasowe'), 'Haslo1234')
    await user.click(screen.getByRole('button', { name: 'Utwórz konto' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Login blazej jest już zajęty')
  })

  it('shows an error when the user is not an admin', async () => {
    setToken('mock-3')
    render(<UsersPage onBack={() => {}} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Brak uprawnień')
  })
})
