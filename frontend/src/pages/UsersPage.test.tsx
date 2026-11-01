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
  render(<UsersPage currentUserId={1} />)
  // wait for the table and the ranges from the mock
  await screen.findByText('Błażej Kowalski')
  return userEvent.setup()
}

// Opens the "New account" side panel and returns it
async function openForm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Dodaj konto' }))
  return screen.findByRole('dialog', { name: 'Nowe konto' })
}

// Opens the "Edit account" side panel for a login and returns it
async function openEdit(user: ReturnType<typeof userEvent.setup>, login: string) {
  await user.click(screen.getByRole('button', { name: `Edytuj konto ${login}` }))
  return screen.findByRole('dialog', { name: 'Edycja konta' })
}

const row = (name: string) => screen.getByRole('row', { name: new RegExp(name) })

describe('UsersPage', () => {
  it('shows accounts in a table with role, range and status', async () => {
    await renderAsAdmin()

    expect(within(row('Błażej Kowalski')).getAllByRole('cell').slice(0, 5).map((c) => c.textContent)).toEqual([
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

  it('changes the name and moves a forester to another range', async () => {
    const user = await renderAsAdmin()
    const form = await openEdit(user, 'blazej')

    expect(within(form).getByText('blazej')).toBeInTheDocument()
    await user.clear(within(form).getByLabelText('Imię i nazwisko'))
    await user.type(within(form).getByLabelText('Imię i nazwisko'), 'Błażej Kowalski-Nowak')
    await user.selectOptions(within(form).getByLabelText('Leśnictwo'), 'Leśnictwo Olszyny')
    await user.click(within(form).getByRole('button', { name: 'Zapisz' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Zapisano zmiany konta blazej')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const edited = row('Błażej Kowalski-Nowak')
    expect(within(edited).getByText('Leśnictwo Olszyny')).toBeInTheDocument()
  })

  it('deactivates an account', async () => {
    const user = await renderAsAdmin()
    const form = await openEdit(user, 'bogdan')

    await user.click(within(form).getByLabelText('Konto aktywne'))
    await user.click(within(form).getByRole('button', { name: 'Zapisz' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Zapisano zmiany konta bogdan')
    expect(within(row('Bogdan Nowak')).getByText('Nieaktywne')).toBeInTheDocument()
    const tile = screen.getByText('Nieaktywne', { selector: 'dt' }).parentElement!
    expect(tile).toHaveTextContent('1')
  })

  it('does not let the admin deactivate or demote their own account', async () => {
    const user = await renderAsAdmin()
    const form = await openEdit(user, 'admin')

    expect(within(form).getByLabelText('Rola')).toBeDisabled()
    expect(within(form).getByLabelText('Konto aktywne')).toBeDisabled()
  })

  it('resets the password after confirming and shows the new one once', async () => {
    const user = await renderAsAdmin()
    const form = await openEdit(user, 'blazej')

    await user.click(within(form).getByRole('button', { name: 'Resetuj hasło' }))
    await user.click(within(form).getByRole('button', { name: 'Tak, resetuj hasło' }))

    const card = await screen.findByRole('status')
    expect(card).toHaveTextContent('Hasło zresetowane')
    expect(card).toHaveTextContent('blazej')
    expect(card.textContent).toMatch(/\w{4}-\w{4}-\w{4}/)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(within(row('Błażej Kowalski')).getByText('Hasło tymczasowe')).toBeInTheDocument()
  })

  it('cancels the password reset', async () => {
    const user = await renderAsAdmin()
    const form = await openEdit(user, 'blazej')

    await user.click(within(form).getByRole('button', { name: 'Resetuj hasło' }))
    await user.click(within(form).getByRole('button', { name: 'Anuluj' }))

    expect(within(form).getByRole('button', { name: 'Resetuj hasło' })).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows an error when the user is not an admin', async () => {
    setToken('mock-3')
    render(<UsersPage currentUserId={1} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Brak uprawnień')
  })
})
