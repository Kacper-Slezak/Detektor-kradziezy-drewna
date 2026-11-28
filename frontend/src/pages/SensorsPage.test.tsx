import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { setToken } from '@/api/client'

// Adding a sensor edits mock state, so every test loads a fresh page and mock
let SensorsPage: typeof import('./SensorsPage').SensorsPage

beforeEach(async () => {
  vi.resetModules()
  SensorsPage = (await import('./SensorsPage')).SensorsPage
})

async function renderAsAdmin() {
  setToken('mock-1')
  render(<SensorsPage />)
  // wait for the table and the ranges from the mock
  await screen.findByText('Skład przy drodze 5')
  return userEvent.setup()
}

// Opens the "New sensor" side panel and returns it
async function openForm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Dodaj czujnik' }))
  return screen.findByRole('dialog', { name: 'Nowy czujnik' })
}

const row = (text: string) => screen.getByRole('row', { name: new RegExp(text) })

describe('SensorsPage', () => {
  it('shows sensors in a table with range, state and battery', async () => {
    await renderAsAdmin()

    const cells = within(row('Skład przy drodze 5')).getAllByRole('cell').map((c) => c.textContent)
    expect(cells.slice(0, 6)).toEqual([
      'Skład przy drodze 5',
      '70B3D57ED0051234',
      'Leśnictwo Dąbrowa',
      'Błażej Kowalski',
      'Alarm',
      '64%',
    ])
    expect(within(row('Skład przy szlabanie')).getByText('Wyciszony')).toBeInTheDocument()
    expect(within(row('Skład przy leśniczówce')).getByText('8%')).toHaveClass('text-destructive')
  })

  it('shows a registered sensor without a location as not mounted', async () => {
    await renderAsAdmin()

    const unmounted = row('70B3D57ED0059ABC')
    expect(within(unmounted).getByText('bez nazwy')).toBeInTheDocument()
    expect(within(unmounted).getByText('Niezamontowany')).toBeInTheDocument()
  })

  it('shows totals in the tiles', async () => {
    await renderAsAdmin()
    const tile = (label: string) => screen.getByText(label, { selector: 'dt' }).parentElement!

    expect(tile('Wszystkie czujniki')).toHaveTextContent('6')
    expect(tile('Z alarmem')).toHaveTextContent('1')
    expect(tile('Bez kontaktu')).toHaveTextContent('1')
    expect(tile('Do zamontowania')).toHaveTextContent('2')
  })

  it('filters the table by name or ID', async () => {
    const user = await renderAsAdmin()
    const search = screen.getByRole('searchbox', { name: /Szukaj/ })

    await user.type(search, 'szlab')
    expect(screen.getByText('Skład przy szlabanie')).toBeInTheDocument()
    expect(screen.queryByText('Skład przy drodze 5')).not.toBeInTheDocument()

    await user.clear(search)
    await user.type(search, '9abc')
    expect(screen.getByText('70B3D57ED0059ABC')).toBeInTheDocument()
    expect(screen.queryByText('Skład przy szlabanie')).not.toBeInTheDocument()

    await user.clear(search)
    await user.type(search, 'xyz')
    expect(screen.getByText('Brak czujników')).toBeInTheDocument()
  })

  it('adds a sensor: cleans up the ID, closes the panel and shows it as not mounted', async () => {
    const user = await renderAsAdmin()
    const form = await openForm(user)

    await user.type(within(form).getByLabelText('ID czujnika (DevEUI)'), '70-b3-d5-7e-d0-06-00-01')
    await user.selectOptions(within(form).getByLabelText('Leśnictwo'), 'Leśnictwo Olszyny · Jan Nowy')
    await user.click(within(form).getByRole('button', { name: 'Dodaj czujnik' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Dodano czujnik 70B3D57ED0060001')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const added = row('70B3D57ED0060001')
    expect(within(added).getByText('Leśnictwo Olszyny')).toBeInTheDocument()
    expect(within(added).getByText('Niezamontowany')).toBeInTheDocument()
  })

  it('rejects an ID that is not 16 hex characters', async () => {
    const user = await renderAsAdmin()
    const form = await openForm(user)

    await user.type(within(form).getByLabelText('ID czujnika (DevEUI)'), '70B3D57ED00')
    await user.selectOptions(within(form).getByLabelText('Leśnictwo'), 'Leśnictwo Olszyny · Jan Nowy')
    await user.click(within(form).getByRole('button', { name: 'Dodaj czujnik' }))

    expect(within(form).getByRole('alert')).toHaveTextContent('ID czujnika musi mieć 16 znaków')
  })

  it('requires a range', async () => {
    const user = await renderAsAdmin()
    const form = await openForm(user)

    await user.type(within(form).getByLabelText('ID czujnika (DevEUI)'), '70B3D57ED0060001')
    await user.click(within(form).getByRole('button', { name: 'Dodaj czujnik' }))

    expect(within(form).getByRole('alert')).toHaveTextContent('Wybierz leśnictwo')
  })

  it('shows the backend error for a sensor that is already added', async () => {
    const user = await renderAsAdmin()
    const form = await openForm(user)

    await user.type(within(form).getByLabelText('ID czujnika (DevEUI)'), '70B3D57ED0051234')
    await user.selectOptions(within(form).getByLabelText('Leśnictwo'), 'Leśnictwo Dąbrowa · Błażej Kowalski')
    await user.click(within(form).getByRole('button', { name: 'Dodaj czujnik' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent('Czujnik 70B3D57ED0051234 jest już dodany')
  })

  it('moves a sensor to another range and renames it', async () => {
    const user = await renderAsAdmin()

    await user.click(screen.getByRole('button', { name: 'Edytuj czujnik 70B3D57ED0051234' }))
    const form = await screen.findByRole('dialog', { name: 'Edycja czujnika' })
    // the ID is shown as text, there is no field to change it
    expect(within(form).getByText('70B3D57ED0051234')).toBeInTheDocument()
    expect(within(form).queryByLabelText('ID czujnika (DevEUI)')).not.toBeInTheDocument()
    expect(within(form).getByLabelText('Leśnictwo')).toHaveDisplayValue('Leśnictwo Dąbrowa · Błażej Kowalski')

    await user.selectOptions(within(form).getByLabelText('Leśnictwo'), 'Leśnictwo Olszyny · Jan Nowy')
    await user.clear(within(form).getByLabelText('Nazwa (opcjonalnie)'))
    await user.type(within(form).getByLabelText('Nazwa (opcjonalnie)'), 'Skład przy moście')
    await user.click(within(form).getByRole('button', { name: 'Zapisz' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Zapisano zmiany czujnika 70B3D57ED0051234')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const edited = row('70B3D57ED0051234')
    expect(within(edited).getByText('Skład przy moście')).toBeInTheDocument()
    expect(within(edited).getByText('Leśnictwo Olszyny')).toBeInTheDocument()
    // the forester follows the range
    expect(within(edited).getByText('Jan Nowy')).toBeInTheDocument()
  })

  it('switches a sensor off and on again', async () => {
    const user = await renderAsAdmin()

    await user.click(screen.getByRole('button', { name: 'Edytuj czujnik 70B3D57ED0052345' }))
    let form = await screen.findByRole('dialog', { name: 'Edycja czujnika' })
    expect(within(form).getByLabelText('Czujnik włączony')).toBeChecked()
    await user.click(within(form).getByLabelText('Czujnik włączony'))
    await user.click(within(form).getByRole('button', { name: 'Zapisz' }))

    await screen.findByRole('status')
    expect(within(row('70B3D57ED0052345')).getByText('Wyłączony')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Edytuj czujnik 70B3D57ED0052345' }))
    form = await screen.findByRole('dialog', { name: 'Edycja czujnika' })
    expect(within(form).getByLabelText('Czujnik włączony')).not.toBeChecked()
    await user.click(within(form).getByLabelText('Czujnik włączony'))
    await user.click(within(form).getByRole('button', { name: 'Zapisz' }))

    // back to what it was before
    await vi.waitFor(() => expect(within(row('70B3D57ED0052345')).getByText('Działa')).toBeInTheDocument())
  })

  it('cannot switch on a sensor that is not mounted yet', async () => {
    const user = await renderAsAdmin()

    await user.click(screen.getByRole('button', { name: 'Edytuj czujnik 70B3D57ED0059ABC' }))
    const form = await screen.findByRole('dialog', { name: 'Edycja czujnika' })

    expect(within(form).getByLabelText('Czujnik włączony')).toBeDisabled()
    expect(within(form).getByText('Czujnik włączy się sam, gdy leśniczy go zamontuje.')).toBeInTheDocument()
  })

  it('deletes a sensor with no history after a second question', async () => {
    const user = await renderAsAdmin()

    await user.click(screen.getByRole('button', { name: 'Edytuj czujnik 70B3D57ED0059ABC' }))
    const form = await screen.findByRole('dialog', { name: 'Edycja czujnika' })
    await user.click(within(form).getByRole('button', { name: 'Usuń czujnik' }))
    expect(within(form).getByText('Usunąć czujnik 70B3D57ED0059ABC na stałe?')).toBeInTheDocument()
    await user.click(within(form).getByRole('button', { name: 'Usuń' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Usunięto czujnik 70B3D57ED0059ABC.')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('row', { name: /70B3D57ED0059ABC/ })).not.toBeInTheDocument()
  })

  it('deletes nothing when the admin cancels', async () => {
    const user = await renderAsAdmin()

    await user.click(screen.getByRole('button', { name: 'Edytuj czujnik 70B3D57ED0059ABC' }))
    const form = await screen.findByRole('dialog', { name: 'Edycja czujnika' })
    await user.click(within(form).getByRole('button', { name: 'Usuń czujnik' }))
    await user.click(within(form).getByRole('button', { name: 'Anuluj' }))

    // back to the first button, the sensor stays
    expect(within(form).getByRole('button', { name: 'Usuń czujnik' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(row('70B3D57ED0059ABC')).toBeInTheDocument()
  })

  it('offers to switch off a sensor that has history instead of deleting it', async () => {
    const user = await renderAsAdmin()

    // Skład przy paśniku has an answered alarm
    await user.click(screen.getByRole('button', { name: 'Edytuj czujnik 70B3D57ED0052345' }))
    const form = await screen.findByRole('dialog', { name: 'Edycja czujnika' })
    await user.click(within(form).getByRole('button', { name: 'Usuń czujnik' }))
    await user.click(within(form).getByRole('button', { name: 'Usuń' }))

    const why = await within(form).findByRole('status')
    expect(why).toHaveTextContent('Tego czujnika nie można usunąć, bo ma alarmy lub wydania.')
    // our own words, not the backend's text for API users, and not as an error
    expect(why).not.toHaveTextContent('PATCH')
    expect(within(form).queryByRole('alert')).not.toBeInTheDocument()

    await user.click(within(form).getByRole('button', { name: 'Wyłącz czujnik' }))

    expect(await screen.findByText('Wyłączono czujnik 70B3D57ED0052345.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(within(row('70B3D57ED0052345')).getByText('Wyłączony')).toBeInTheDocument()
  })

  it('only explains it when the sensor with history is off already', async () => {
    const user = await renderAsAdmin()

    // switch it off first
    await user.click(screen.getByRole('button', { name: 'Edytuj czujnik 70B3D57ED0052345' }))
    let form = await screen.findByRole('dialog', { name: 'Edycja czujnika' })
    await user.click(within(form).getByLabelText('Czujnik włączony'))
    await user.click(within(form).getByRole('button', { name: 'Zapisz' }))
    await screen.findByRole('status')

    await user.click(screen.getByRole('button', { name: 'Edytuj czujnik 70B3D57ED0052345' }))
    form = await screen.findByRole('dialog', { name: 'Edycja czujnika' })
    await user.click(within(form).getByRole('button', { name: 'Usuń czujnik' }))
    await user.click(within(form).getByRole('button', { name: 'Usuń' }))

    expect(await within(form).findByText('Zostaje w systemie jako wyłączony, razem z historią.')).toBeInTheDocument()
    expect(within(form).queryByRole('button', { name: 'Wyłącz czujnik' })).not.toBeInTheDocument()
    await user.click(within(form).getByRole('button', { name: 'OK' }))
    expect(within(form).getByRole('button', { name: 'Usuń czujnik' })).toBeInTheDocument()
  })

  it('shows an error when the user is not an admin', async () => {
    setToken('mock-3')
    render(<SensorsPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Brak uprawnień')
  })
})
