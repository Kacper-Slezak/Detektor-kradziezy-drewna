import { render, screen, within } from '@testing-library/react'
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
  render(<UsersPage />)
  // wait for the table and the ranges from the mock
  await screen.findByText('Błażej Kowalski')
  return userEvent.setup()
}

// Opens the "New account" side panel and returns it
async function openForm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Dodaj konto' }))
  return screen.findByRole('dialog', { name: 'Nowe konto' })
}

const row = (name: string) => screen.getByRole('row', { name: new RegExp(name) })

describe('UsersPage', () => {
  it('shows accounts in a table with role, range and status', async () => {
    await renderAsAdmin()

    expect(within(row('Błażej Kowalski')).getAllByRole('cell').map((c) => c.textContent)).toEqual([
      'Błażej Kowalski',
      'blazej',
      'Leśniczy',
      'Leśnictwo Dąbrowa',
      'Aktywne',
    ])
    expect(within(row('Bogdan Nowak')).getByText('—')).toBeInTheDocument()
    expect(within(row('Jan Nowy')).getByText('Hasło tymczasowe')).toBeInTheDocument()
  })

  it('shows totals in the tiles', async () => {
    await renderAsAdmin()
    const tile = (label: string) => screen.getByText(label, { selector: 'dt' }).parentElement!

    expect(tile('Wszystkie konta')).toHaveTextContent('4')
    expect(tile('Leśniczy')).toHaveTextContent('2')
    expect(tile('Z hasłem tymczasowym')).toHaveTextContent('1')
    expect(tile('Nieaktywne')).toHaveTextContent('0')
  })

  it('filters the table by name or login', async () => {
    const user = await renderAsAdmin()
    const search = screen.getByRole('searchbox', { name: /Szukaj/ })

    await user.type(search, 'bogd')
    expect(screen.getByText('Bogdan Nowak')).toBeInTheDocument()
    expect(screen.queryByText('Błażej Kowalski')).not.toBeInTheDocument()

    await user.clear(search)
    await user.type(search, 'nikogo')
    expect(screen.getByText('Brak kont')).toBeInTheDocument()
  })

  it('fills the login from the full name until it is edited', async () => {
    const user = await renderAsAdmin()
    const form = await openForm(user)
    const login = within(form).getByLabelText('Login')

    await user.type(within(form).getByLabelText('Imię i nazwisko'), 'Błażej Nowak')
    expect(login).toHaveValue('blazej.nowak')

    await user.clear(login)
    await user.type(login, 'bnowak')
    await user.type(within(form).getByLabelText('Imię i nazwisko'), 'owski')
    expect(login).toHaveValue('bnowak')
  })

  it('creates a forester, closes the panel and shows the login and password once', async () => {
    const user = await renderAsAdmin()
    const form = await openForm(user)

    await user.type(within(form).getByLabelText('Imię i nazwisko'), 'Anna Las')
    await user.selectOptions(within(form).getByLabelText('Leśnictwo'), 'Leśnictwo Olszyny')
    await user.click(within(form).getByRole('button', { name: 'Wylosuj' }))
    const password = (within(form).getByLabelText('Hasło tymczasowe') as HTMLInputElement).value
    expect(password).toMatch(/^\w{4}-\w{4}-\w{4}$/)
    await user.click(within(form).getByRole('button', { name: 'Utwórz konto' }))

    const created = await screen.findByRole('status')
    expect(created).toHaveTextContent('Konto utworzone')
    expect(created).toHaveTextContent('anna.las')
    expect(created).toHaveTextContent(password)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(within(row('Anna Las')).getByText('Leśnictwo Olszyny')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Kopiuj' }))
    expect(await navigator.clipboard.readText()).toBe(`Login: anna.las\nHasło: ${password}`)
    expect(screen.getByRole('button', { name: 'Skopiowano' })).toBeInTheDocument()
  })

  it('does not ask for a range for a district manager', async () => {
    const user = await renderAsAdmin()
    const form = await openForm(user)

    await user.selectOptions(within(form).getByLabelText('Rola'), 'Nadleśniczy')
    expect(within(form).queryByLabelText('Leśnictwo')).not.toBeInTheDocument()

    await user.type(within(form).getByLabelText('Imię i nazwisko'), 'Ewa Bór')
    await user.type(within(form).getByLabelText('Hasło tymczasowe'), 'Haslo1234')
    await user.click(within(form).getByRole('button', { name: 'Utwórz konto' }))

    expect(await screen.findByRole('row', { name: /ewa\.bor/ })).toHaveTextContent('Nadleśniczy')
  })

  it('requires a range for a forester', async () => {
    const user = await renderAsAdmin()
    const form = await openForm(user)

    await user.type(within(form).getByLabelText('Imię i nazwisko'), 'Anna Las')
    await user.type(within(form).getByLabelText('Hasło tymczasowe'), 'Haslo1234')
    await user.click(within(form).getByRole('button', { name: 'Utwórz konto' }))

    expect(within(form).getByRole('alert')).toHaveTextContent('Leśniczy musi mieć przypisane leśnictwo')
  })

  it('rejects a short password', async () => {
    const user = await renderAsAdmin()
    const form = await openForm(user)

    await user.type(within(form).getByLabelText('Imię i nazwisko'), 'Anna Las')
    await user.selectOptions(within(form).getByLabelText('Leśnictwo'), 'Leśnictwo Olszyny')
    await user.type(within(form).getByLabelText('Hasło tymczasowe'), 'krotkie')
    await user.click(within(form).getByRole('button', { name: 'Utwórz konto' }))

    expect(within(form).getByRole('alert')).toHaveTextContent('Hasło musi mieć co najmniej 8 znaków')
  })

  it('shows the backend error for a taken login', async () => {
    const user = await renderAsAdmin()
    const form = await openForm(user)

    await user.type(within(form).getByLabelText('Imię i nazwisko'), 'Błażej Kowalski')
    await user.clear(within(form).getByLabelText('Login'))
    await user.type(within(form).getByLabelText('Login'), 'blazej')
    await user.selectOptions(within(form).getByLabelText('Leśnictwo'), 'Leśnictwo Dąbrowa')
    await user.type(within(form).getByLabelText('Hasło tymczasowe'), 'Haslo1234')
    await user.click(within(form).getByRole('button', { name: 'Utwórz konto' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent('Login blazej jest już zajęty')
  })

  it('shows an error when the user is not an admin', async () => {
    setToken('mock-3')
    render(<UsersPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Brak uprawnień')
  })
})
