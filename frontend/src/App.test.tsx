import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getToken, setToken } from './api/client'

// The app runs on the mock backend here (VITE_USE_MOCK=true in vite.config.ts).
// Changing a password edits mock state, so every test loads a fresh App.
let App: typeof import('./App').default

beforeEach(async () => {
  vi.resetModules()
  App = (await import('./App')).default
})

async function logIn(login: string, password: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Login'), login)
  await user.type(screen.getByLabelText('Hasło'), password)
  await user.click(screen.getByRole('button', { name: 'Zaloguj się' }))
  return user
}

describe('login', () => {
  it('logs in, saves the token and shows the home page', async () => {
    render(<App />)
    await logIn('blazej', 'tajne123')

    expect(await screen.findByRole('heading', { name: 'Witaj, Błażej Kowalski' })).toBeInTheDocument()
    expect(screen.getByText(/Leśniczy · Leśnictwo Dąbrowa/)).toBeInTheDocument()
    expect(getToken()).toBe('mock-3')
  })

  it('shows an error for a wrong password', async () => {
    render(<App />)
    await logIn('blazej', 'zle')

    expect(await screen.findByRole('alert')).toHaveTextContent('Nieprawidłowy login lub hasło')
    expect(getToken()).toBeNull()
  })

  it('logs out and removes the token', async () => {
    render(<App />)
    const user = await logIn('admin', 'admin123')
    await user.click(await screen.findByRole('button', { name: 'Wyloguj' }))

    expect(screen.getByRole('button', { name: 'Zaloguj się' })).toBeInTheDocument()
    expect(getToken()).toBeNull()
  })
})

describe('session restore', () => {
  it('restores the user from a saved token', async () => {
    setToken('mock-4')
    render(<App />)

    expect(screen.getByRole('status')).toHaveTextContent('Ładowanie…')
    expect(await screen.findByRole('heading', { name: 'Witaj, Bogdan Nowak' })).toBeInTheDocument()
  })

  it('drops an invalid token and shows the login page', async () => {
    setToken('mock-999')
    render(<App />)

    expect(await screen.findByRole('button', { name: 'Zaloguj się' })).toBeInTheDocument()
    expect(getToken()).toBeNull()
  })

  it('shows the login page right away without a token', () => {
    render(<App />)
    expect(screen.getByRole('button', { name: 'Zaloguj się' })).toBeInTheDocument()
  })
})

describe('forced password change', () => {
  it('blocks the home page until the temporary password is changed', async () => {
    render(<App />)
    const user = await logIn('nowy.lesniczy', 'Tymczasowe123!')

    await user.type(await screen.findByLabelText('Hasło tymczasowe'), 'Tymczasowe123!')
    await user.type(screen.getByLabelText('Nowe hasło'), 'NoweHaslo1')
    await user.type(screen.getByLabelText('Powtórz nowe hasło'), 'NoweHaslo1')
    await user.click(screen.getByRole('button', { name: 'Zmień hasło' }))

    expect(await screen.findByRole('heading', { name: 'Witaj, Jan Nowy' })).toBeInTheDocument()
    expect(screen.getByText('Hasło zostało zmienione.')).toBeInTheDocument()
  })

  it('can only log out from the forced change', async () => {
    render(<App />)
    const user = await logIn('nowy.lesniczy', 'Tymczasowe123!')
    await user.click(await screen.findByRole('button', { name: 'Wyloguj' }))

    expect(screen.getByRole('button', { name: 'Zaloguj się' })).toBeInTheDocument()
    expect(getToken()).toBeNull()
  })
})

describe('admin panel', () => {
  it('opens right after the admin signs in, on the users section', async () => {
    render(<App />)
    await logIn('admin', 'admin123')

    const menu = await screen.findByRole('navigation', { name: 'Menu panelu' })
    expect(within(menu).getByRole('button', { name: 'Użytkownicy' })).toHaveAttribute('aria-current', 'page')
    expect(within(menu).getByRole('button', { name: /Czujniki/ })).toBeDisabled()
    expect(screen.getByRole('heading', { name: 'Użytkownicy' })).toBeInTheDocument()
    expect(await screen.findByText('Błażej Kowalski')).toBeInTheDocument()
  })

  it('a new forester can sign in with the temporary password', async () => {
    render(<App />)
    const user = await logIn('admin', 'admin123')
    await screen.findByText('Błażej Kowalski')

    await user.type(screen.getByLabelText('Imię i nazwisko'), 'Anna Las')
    await user.selectOptions(screen.getByLabelText('Leśnictwo'), 'Leśnictwo Olszyny')
    await user.type(screen.getByLabelText('Hasło tymczasowe'), 'Tymczasowe1')
    await user.click(screen.getByRole('button', { name: 'Utwórz konto' }))
    await screen.findByText('Konto utworzone')

    await user.click(screen.getByRole('button', { name: 'Wyloguj' }))
    await logIn('anna.las', 'Tymczasowe1')

    expect(await screen.findByLabelText('Hasło tymczasowe')).toBeInTheDocument()
  })

  it('changes the password from the menu and comes back to the panel', async () => {
    render(<App />)
    const user = await logIn('admin', 'admin123')
    await user.click(await screen.findByRole('button', { name: 'Zmień hasło' }))

    await user.type(screen.getByLabelText('Obecne hasło'), 'admin123')
    await user.type(screen.getByLabelText('Nowe hasło'), 'NoweHaslo1')
    await user.type(screen.getByLabelText('Powtórz nowe hasło'), 'NoweHaslo1')
    await user.click(screen.getByRole('button', { name: 'Zmień hasło' }))

    expect(await screen.findByRole('navigation', { name: 'Menu panelu' })).toBeInTheDocument()
    expect(screen.getByText('Hasło zostało zmienione.')).toBeInTheDocument()
  })

  it('is not shown to a forester', async () => {
    render(<App />)
    await logIn('blazej', 'tajne123')

    await screen.findByRole('heading', { name: 'Witaj, Błażej Kowalski' })
    expect(screen.queryByRole('navigation', { name: 'Menu panelu' })).not.toBeInTheDocument()
  })
})
