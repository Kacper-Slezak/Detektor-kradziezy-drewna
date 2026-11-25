import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getToken, setToken } from './api/client'

// The app runs on the mock backend here (VITE_USE_MOCK=true in vite.config.ts).
// Changing a password edits mock state, so every test loads a fresh App.
let App: typeof import('./App').default

beforeEach(async () => {
  // the address says which view is open, and jsdom keeps it between tests
  window.history.replaceState(null, '', '/')
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

// Leaflet takes two taps within 200 ms for a double tap and zooms in, which jsdom cannot
// lay out (Invalid LatLng). A person never taps the pin and the popup button that fast.
const afterTap = () => new Promise((resolve) => setTimeout(resolve, 250))

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
    // the same module instance App uses (beforeEach loaded both fresh)
    const disablePush = vi.spyOn(await import('@/lib/push'), 'disablePush')
    setToken('mock-999')
    render(<App />)

    expect(await screen.findByRole('button', { name: 'Zaloguj się' })).toBeInTheDocument()
    expect(getToken()).toBeNull()
    // this phone stops getting that user's alarms too
    expect(disablePush).toHaveBeenCalledWith(null)
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

  it('deletes a test sensor and switches off one with history instead', async () => {
    render(<App />)
    const user = await logIn('admin', 'admin123')
    await user.click(within(await screen.findByRole('navigation', { name: 'Menu panelu' })).getByRole('button', { name: 'Czujniki' }))
    await screen.findByText('Skład przy drodze 5')

    // not mounted, no alarms or releases: it can go
    await user.click(screen.getByRole('button', { name: 'Edytuj czujnik 70B3D57ED005A1B2' }))
    let form = await screen.findByRole('dialog', { name: 'Edycja czujnika' })
    await user.click(within(form).getByRole('button', { name: 'Usuń czujnik' }))
    await user.click(within(form).getByRole('button', { name: 'Usuń' }))
    expect(await screen.findByText('Usunięto czujnik 70B3D57ED005A1B2.')).toBeInTheDocument()
    expect(screen.queryByText('70B3D57ED005A1B2')).not.toBeInTheDocument()

    // an alarm and a release: it stays, switched off
    await user.click(screen.getByRole('button', { name: 'Edytuj czujnik 70B3D57ED005DEF0' }))
    form = await screen.findByRole('dialog', { name: 'Edycja czujnika' })
    await user.click(within(form).getByRole('button', { name: 'Usuń czujnik' }))
    await user.click(within(form).getByRole('button', { name: 'Usuń' }))
    await user.click(await within(form).findByRole('button', { name: 'Wyłącz czujnik' }))
    expect(await screen.findByText('Wyłączono czujnik 70B3D57ED005DEF0.')).toBeInTheDocument()
    expect(within(screen.getByRole('row', { name: /70B3D57ED005DEF0/ })).getByText('Wyłączony')).toBeInTheDocument()
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
    expect(screen.getByText('2 czujniki czekają na montaż')).toBeInTheDocument()
  })

  it('has a menu with password change and log out', async () => {
    render(<App />)
    const user = await logIn('blazej', 'tajne123')

    await user.click(await screen.findByRole('button', { name: 'Menu' }, mapTimeout))
    const menu = await screen.findByRole('dialog', { name: 'Błażej Kowalski' })
    expect(within(menu).getByRole('button', { name: 'Zmień hasło' })).toBeInTheDocument()
    // notifications are for foresters; jsdom has no push, so it says so
    expect(await within(menu).findByText('To urządzenie nie obsługuje powiadomień.')).toBeInTheDocument()

    const disablePush = vi.spyOn(await import('@/lib/push'), 'disablePush')
    await user.click(within(menu).getByRole('button', { name: 'Wyloguj' }))
    expect(screen.getByRole('button', { name: 'Zaloguj się' })).toBeInTheDocument()
    expect(getToken()).toBeNull()
    // the push subscription is removed with the token from before logout
    expect(disablePush).toHaveBeenCalledWith('mock-3')
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
    expect(window.location.pathname).toBe('/alarms')

    await user.click(within(views).getByRole('button', { name: 'Mapa' }))
    expect(screen.getByRole('heading', { name: 'Mapa czujników' })).toBeInTheDocument()
    expect(within(views).getByRole('button', { name: 'Mapa' })).toHaveAttribute('aria-current', 'page')
    expect(window.location.pathname).toBe('/')
  })

  it('opens the releases, ends one there, and the map follows', async () => {
    render(<App />)
    const user = await logIn('blazej', 'tajne123')
    await screen.findByTitle('Skład przy szlabanie: Wyciszony', {}, mapTimeout)
    const views = screen.getByRole('navigation', { name: 'Widok' })

    // the number of ongoing releases is in the name of the button
    await user.click(within(views).getByRole('button', { name: 'Wydania, 1 trwa' }))
    expect(screen.getByRole('heading', { name: 'Wydania drewna' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/releases')

    const list = await screen.findByRole('list', { name: 'Trwające wydania' }, mapTimeout)
    await user.click(within(list).getByRole('button', { name: 'Zakończ wyciszenie' }))
    const panel = await screen.findByRole('dialog', { name: 'Zakończyć wyciszenie?' })
    await user.click(within(panel).getByRole('button', { name: 'Zakończ' }))
    expect(await screen.findByText('Skład przy szlabanie znów czuwa')).toBeInTheDocument()

    // no ongoing release left, so the badge is gone
    expect(await within(views).findByRole('button', { name: 'Wydania' }, mapTimeout)).toBeInTheDocument()
    await user.click(within(views).getByRole('button', { name: 'Mapa' }))
    expect(await screen.findByTitle('Skład przy szlabanie: Działa', {}, mapTimeout)).toBeInTheDocument()
  })

  it('opens the releases from the address', async () => {
    window.history.replaceState(null, '', '/releases')
    setToken('mock-3')
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Wydania drewna' }, mapTimeout)).toBeInTheDocument()
    expect(await screen.findByRole('list', { name: 'Trwające wydania' }, mapTimeout)).toHaveTextContent('Skład przy szlabanie')
  })

  it('opens the alarm from the address, e.g. after tapping a push', async () => {
    window.history.replaceState(null, '', '/alarms/41')
    setToken('mock-3')
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Alarmy' }, mapTimeout)).toBeInTheDocument()
    const list = await screen.findByRole('list', { name: 'Alarmy' })
    expect(within(list).getByRole('listitem', { current: true })).toHaveTextContent('Skład przy drodze 5')
  })

  it('opens the ended release in the history from the address, e.g. after a push about its end', async () => {
    window.history.replaceState(null, '', '/releases/9')
    setToken('mock-3')
    render(<App />)

    const list = await screen.findByRole('list', { name: 'Zakończone wydania' }, mapTimeout)
    expect(within(list).getByRole('listitem', { current: true })).toHaveTextContent('Skład przy paśniku')
  })

  it('opens the pin of a sensor from the address, e.g. after a push about its battery', async () => {
    window.history.replaceState(null, '', '/sensors/70B3D57ED0055678')
    setToken('mock-3')
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Mapa czujników' }, mapTimeout)).toBeInTheDocument()
    // its popup is open without a tap
    expect(await screen.findByText('70B3D57ED0055678', {}, mapTimeout)).toBeInTheDocument()
  })

  it('says so when the sensor from the address is not on the map', async () => {
    window.history.replaceState(null, '', '/sensors/70B3D57ED0059ABC')
    setToken('mock-3')
    render(<App />)

    expect(await screen.findByText('Czujnika 70B3D57ED0059ABC nie ma na mapie.', {}, mapTimeout)).toBeInTheDocument()
  })

  it('goes back to the map with the back button', async () => {
    render(<App />)
    const user = await logIn('blazej', 'tajne123')
    await screen.findByTitle('Skład przy drodze 5: Alarm', {}, mapTimeout)
    await user.click(within(screen.getByRole('navigation', { name: 'Widok' })).getByRole('button', { name: /^Alarmy/ }))

    window.history.back()

    expect(await screen.findByRole('heading', { name: 'Mapa czujników' })).toBeInTheDocument()
  })

  it('starts the next person on the map after logging out', async () => {
    window.history.replaceState(null, '', '/alarms')
    setToken('mock-3')
    render(<App />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Menu' }, mapTimeout))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Wyloguj' }))

    expect(window.location.pathname).toBe('/')
  })

  // jsdom has no GPS and is not https: the phone is faked for the mounting tests
  function fakePhoneGps() {
    vi.stubGlobal('isSecureContext', true)
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition: (ok: PositionCallback) =>
          ok({ coords: { latitude: 50.061, longitude: 19.95, accuracy: 6 } } as GeolocationPosition),
      },
    })
  }

  function removePhoneGps() {
    vi.unstubAllGlobals()
    Reflect.deleteProperty(navigator, 'geolocation')
  }

  it('a forester mounts a sensor and its pin shows up on the map', async () => {
    fakePhoneGps()
    try {
      render(<App />)
      const user = await logIn('blazej', 'tajne123')
      await user.click(await screen.findByRole('button', { name: 'Zamontuj' }, mapTimeout))

      const panel = await screen.findByRole('dialog', { name: 'Montaż czujnika' })
      await user.type(within(panel).getByLabelText('Nazwa'), 'Skład przy brzozach')
      await user.click(within(panel).getByRole('button', { name: 'Pobierz pozycję' }))
      await user.click(await within(panel).findByRole('button', { name: 'Zapisz' }))

      expect(await screen.findByText('Zamontowano: Skład przy brzozach')).toBeInTheDocument()
      expect(screen.queryByRole('dialog', { name: 'Montaż czujnika' })).not.toBeInTheDocument()
      // it has not sent anything yet, so it is silent; nothing waits to be mounted any more
      expect(await screen.findByTitle('Skład przy brzozach: Bez kontaktu')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Zamontuj' })).not.toBeInTheDocument()
    } finally {
      removePhoneGps()
    }
  })

  it('a forester moves a mounted sensor from its pin', async () => {
    fakePhoneGps()
    try {
      render(<App />)
      const user = await logIn('blazej', 'tajne123')
      await user.click(await screen.findByTitle('Skład przy paśniku: Działa', {}, mapTimeout))
      const move = await screen.findByRole('button', { name: 'Przenieś czujnik' })
      await afterTap()
      await user.click(move)

      const panel = await screen.findByRole('dialog', { name: 'Przeniesienie czujnika' })
      expect(within(panel).getByText('Obecna pozycja: 50.05980, 19.96050')).toBeInTheDocument()
      await user.click(within(panel).getByRole('button', { name: 'Pobierz pozycję' }))
      await user.click(await within(panel).findByRole('button', { name: 'Zapisz nową pozycję' }))

      expect(await screen.findByText('Przeniesiono: Skład przy paśniku')).toBeInTheDocument()
      expect(screen.queryByRole('dialog', { name: 'Przeniesienie czujnika' })).not.toBeInTheDocument()
      // still one pin, now in the new place
      expect(await screen.findByTitle('Skład przy paśniku: Działa')).toBeInTheDocument()
    } finally {
      removePhoneGps()
    }
  })

  it('a district manager cannot move or mute sensors', async () => {
    render(<App />)
    const user = await logIn('bogdan', 'tajne123')
    await user.click(await screen.findByTitle('Skład przy paśniku: Działa', {}, mapTimeout))

    expect(await screen.findByText('70B3D57ED0052345')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Przenieś czujnik' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Wycisz na czas wywozu' })).not.toBeInTheDocument()
  })

  it('a forester mutes a sensor for timber pickup and its pin turns blue', async () => {
    render(<App />)
    const user = await logIn('blazej', 'tajne123')
    await user.click(await screen.findByTitle('Skład przy paśniku: Działa', {}, mapTimeout))
    const mute = await screen.findByRole('button', { name: 'Wycisz na czas wywozu' })
    await afterTap()
    await user.click(mute)

    const panel = await screen.findByRole('dialog', { name: 'Wyciszenie na czas wywozu' })
    await user.click(within(panel).getByRole('button', { name: '2 h' }))
    await user.type(within(panel).getByLabelText('Przewoźnik (opcjonalnie)'), 'Trans-Las')
    await user.click(within(panel).getByRole('button', { name: 'Wycisz' }))

    expect(await screen.findByText(/^Wyciszono: Skład przy paśniku do /)).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Wyciszenie na czas wywozu' })).not.toBeInTheDocument()
    expect(await screen.findByTitle('Skład przy paśniku: Wyciszony')).toBeInTheDocument()
  })

  it('a forester ends the muting when the carrier has left', async () => {
    render(<App />)
    const user = await logIn('blazej', 'tajne123')
    await user.click(await screen.findByTitle('Skład przy szlabanie: Wyciszony', {}, mapTimeout))
    const end = await screen.findByRole('button', { name: 'Zakończ wyciszenie' })
    await afterTap()
    await user.click(end)

    const panel = await screen.findByRole('dialog', { name: 'Zakończyć wyciszenie?' })
    await user.click(within(panel).getByRole('button', { name: 'Zakończ' }))

    expect(await screen.findByText('Skład przy szlabanie znów czuwa')).toBeInTheDocument()
    expect(await screen.findByTitle('Skład przy szlabanie: Działa')).toBeInTheDocument()
  })

  it('a district manager sees the sensors waiting to be mounted but cannot mount them', async () => {
    render(<App />)
    await logIn('bogdan', 'tajne123')

    expect(await screen.findByText('2 czujniki czekają na montaż', {}, mapTimeout)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zamontuj' })).not.toBeInTheDocument()
  })

  it('has no alarm notifications for a district manager', async () => {
    render(<App />)
    const user = await logIn('bogdan', 'tajne123')

    await user.click(await screen.findByRole('button', { name: 'Menu' }, mapTimeout))
    const menu = await screen.findByRole('dialog', { name: 'Bogdan Nowak' })
    expect(within(menu).getByRole('button', { name: 'Wyloguj' })).toBeInTheDocument()
    expect(within(menu).queryByText(/powiadomie/i)).not.toBeInTheDocument()
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
