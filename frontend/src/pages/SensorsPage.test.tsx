import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { setToken } from '@/api/client'
import { SensorsPage } from './SensorsPage'

async function renderAsAdmin() {
  setToken('mock-1')
  render(<SensorsPage />)
  // wait for the table and the ranges from the mock
  await screen.findByText('Skład przy drodze 5')
  return userEvent.setup()
}

const row = (text: string) => screen.getByRole('row', { name: new RegExp(text) })

describe('SensorsPage', () => {
  it('shows sensors in a table with range, state and battery', async () => {
    await renderAsAdmin()

    const cells = within(row('Skład przy drodze 5')).getAllByRole('cell').map((c) => c.textContent)
    expect(cells.slice(0, 5)).toEqual(['Skład przy drodze 5', '70B3D57ED0051234', 'Leśnictwo Dąbrowa', 'Alarm', '64%'])
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

    expect(tile('Wszystkie czujniki')).toHaveTextContent('4')
    expect(tile('Z alarmem')).toHaveTextContent('1')
    expect(tile('Bez kontaktu')).toHaveTextContent('1')
    expect(tile('Do zamontowania')).toHaveTextContent('1')
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

  it('shows an error when the user is not an admin', async () => {
    setToken('mock-3')
    render(<SensorsPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Brak uprawnień')
  })
})
