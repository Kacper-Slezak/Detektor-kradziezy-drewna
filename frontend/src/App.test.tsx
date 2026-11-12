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

// after signing in, the map code is loaded separately and the sensors come from the mock
const mapTimeout = { timeout: 3000 }

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

    expect(await screen.findByRole('heading', { name: 'Mapa czujników' }, mapTimeout)).toBeInTheDocument()
    expect(screen.getByText('Błażej Kowalski · Leśnictwo Dąbrowa')).toBeInTheDocument()
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
    expect(await screen.findByRole('heading', { name: 'Mapa czujników' }, mapTimeout)).toBeInTheDocument()
    expect(screen.getByText('Bogdan Nowak')).toBeInTheDocument()
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

    expect(await screen.findByRole('heading', { name: 'Mapa czujników' }, mapTimeout)).toBeInTheDocument()
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
    expect(within(menu).getByRole('button', { name: /Leśnictwa/ })).toBeDisabled()
    expect(screen.getByRole('heading', { name: 'Użytkownicy' })).toBeInTheDocument()
    expect(await screen.findByText('Błażej Kowalski')).toBeInTheDocument()
  })

  it('switches to the sensors section from the menu', async () => {
    render(<App />)
    const user = await logIn('admin', 'admin123')
    const menu = await screen.findByRole('navigation', { name: 'Menu panelu' })

    await user.click(within(menu).getByRole('button', { name: 'Czujniki' }))

    expect(within(menu).getByRole('button', { name: 'Czujniki' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('heading', { name: 'Czujniki' })).toBeInTheDocument()
    expect(await screen.findByText('Skład przy drodze 5')).toBeInTheDocument()
  })

  it('a new forester can sign in with the temporary password', async () => {
    render(<App />)
    const user = await logIn('admin', 'admin123')
    await screen.findByText('Błażej Kowalski')

    await user.click(screen.getByRole('button', { name: 'Dodaj konto' }))
    const form = await screen.findByRole('dialog', { name: 'Nowe konto' })
    await user.type(within(form).getByLabelText('Imię i nazwisko'), 'Anna Las')
    await user.selectOptions(within(form).getByLabelText('Leśnictwo'), 'Leśnictwo Olszyny')
    await user.type(within(form).getByLabelText('Hasło tymczasowe'), 'Tymczasowe1')
    await user.click(within(form).getByRole('button', { name: 'Utwórz konto' }))
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

    await screen.findByRole('heading', { name: 'Mapa czujników' }, mapTimeout)
    expect(screen.queryByRole('navigation', { name: 'Menu panelu' })).not.toBeInTheDocument()
  })
})

describe('sensor map', () => {
  it('a forester sees the pins of their range and a legend with counts', async () => {
    render(<App />)
    await logIn('blazej', 'tajne123')

    expect(await screen.findByTitle('Skład przy drodze 5: Alarm', {}, mapTimeout)).toBeInTheDocument()
    expect(screen.getByTitle('Skład przy szlabanie: Wyciszony')).toBeInTheDocument()
    expect(screen.getByTitle('Skład przy paśniku: Działa')).toBeInTheDocument()
    // another range
    expect(screen.queryByTitle(/Skład przy leśniczówce/)).not.toBeInTheDocument()

    const legend = screen.getByRole('region', { name: 'Legenda' })
    expect(within(legend).getByText('Alarm').parentElement).toHaveTextContent('1')
    expect(within(legend).getByText('Działa').parentElement).toHaveTextContent('1')
  })

  it('a district manager sees all ranges and the sensors waiting to be mounted', async () => {
    render(<App />)
    await logIn('bogdan', 'tajne123')

    expect(await screen.findByTitle('Skład przy leśniczówce: Bez kontaktu', {}, mapTimeout)).toBeInTheDocument()
    expect(screen.getByTitle('Skład przy drodze 5: Alarm')).toBeInTheDocument()
    expect(screen.getByText('1 czujnik czeka na montaż')).toBeInTheDocument()
  })

  it('has a menu with password change and log out', async () => {
    render(<App />)
    const user = await logIn('blazej', 'tajne123')

    await user.click(await screen.findByRole('button', { name: 'Menu' }, mapTimeout))
    const menu = await screen.findByRole('dialog', { name: 'Błażej Kowalski' })
    expect(within(menu).getByRole('button', { name: 'Zmień hasło' })).toBeInTheDocument()

    await user.click(within(menu).getByRole('button', { name: 'Wyloguj' }))
    expect(screen.getByRole('button', { name: 'Zaloguj się' })).toBeInTheDocument()
    expect(getToken()).toBeNull()
  })

  it('switches between the map and the alarm list', async () => {
    render(<App />)
    const user = await logIn('blazej', 'tajne123')
    await screen.findByTitle('Skład przy drodze 5: Alarm', {}, mapTimeout)
    const views = screen.getByRole('navigation', { name: 'Widok' })

    // the number of open alarms is in the name of the button
    await user.click(within(views).getByRole('button', { name: 'Alarmy, 1 otwarty' }))
    expect(screen.getByRole('heading', { name: 'Alarmy' })).toBeInTheDocument()
    expect(await screen.findByRole('list', { name: 'Alarmy' })).toHaveTextContent('Skład przy drodze 5')

    await user.click(within(views).getByRole('button', { name: 'Mapa' }))
    expect(screen.getByRole('heading', { name: 'Mapa czujników' })).toBeInTheDocument()
    expect(within(views).getByRole('button', { name: 'Mapa' })).toHaveAttribute('aria-current', 'page')
  })

  it('clears the open alarm count after the forester answers', async () => {
    render(<App />)
    const user = await logIn('blazej', 'tajne123')
    await screen.findByTitle('Skład przy drodze 5: Alarm', {}, mapTimeout)
    const views = screen.getByRole('navigation', { name: 'Widok' })

    await user.click(within(views).getByRole('button', { name: 'Alarmy, 1 otwarty' }))
    const list = await screen.findByRole('list', { name: 'Alarmy' })
    await user.click(within(list).getByRole('button', { name: 'Fałszywy alarm' }))
    await user.click(within(list).getByRole('button', { name: 'Zapisz' }))

    // the sensors are loaded again, so the count goes away
    expect(await within(views).findByRole('button', { name: 'Alarmy' })).toBeInTheDocument()
  })
})
