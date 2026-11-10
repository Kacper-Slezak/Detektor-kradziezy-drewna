import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { setToken } from '@/api/client'
import { AlarmsPage } from './AlarmsPage'

// mock tokens: mock-3 forester of Dąbrowa, mock-4 district manager, mock-5 forester of Olszyny
function renderAs(token: string) {
  setToken(token)
  render(<AlarmsPage />)
  return userEvent.setup()
}

const items = async () => within(await screen.findByRole('list', { name: 'Alarmy' })).getAllByRole('listitem')
const filter = (name: string) => within(screen.getByRole('group', { name: 'Pokaż alarmy' })).getByRole('button', { name })

describe('AlarmsPage', () => {
  it('shows only new alarms of the forester range by default', async () => {
    renderAs('mock-3')

    const [alarm, ...rest] = await items()
    expect(rest).toHaveLength(0)
    expect(alarm).toHaveTextContent('Skład przy drodze 5')
    expect(alarm).toHaveTextContent('Nowy')
    expect(alarm).toHaveTextContent('pewność 87%')
    expect(alarm).toHaveTextContent('dźwięk + wibracje')
    expect(filter('Nowe')).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows all alarms newest first, with the response and the tampering note', async () => {
    const user = renderAs('mock-3')
    await items()

    await user.click(filter('Wszystkie'))
    const all = await items()
    expect(all.map((li) => within(li).getByText(/^Skład/).textContent)).toEqual([
      'Skład przy drodze 5',
      'Skład przy paśniku',
      'Skład przy drodze 5',
    ])
    expect(all[1]).toHaveTextContent('Kradzież')
    expect(all[1]).toHaveTextContent('Sprawdził(a) blazej')
    expect(all[1]).toHaveTextContent('„przewoźnik ładował 5 dodatkowych kłód”')
    expect(all[2]).toHaveTextContent('Fałszywy alarm')
    expect(all[2]).toHaveTextContent('Możliwa manipulacja przy czujniku')
    expect(all[0]).not.toHaveTextContent('Możliwa manipulacja')
  })

  it('filters by status', async () => {
    const user = renderAs('mock-3')
    await items()

    await user.click(filter('Fałszywe'))
    const shown = await items()
    expect(shown).toHaveLength(1)
    expect(shown[0]).toHaveTextContent('zwierzę przy stosie')
    expect(filter('Fałszywe')).toHaveAttribute('aria-pressed', 'true')
    expect(filter('Nowe')).toHaveAttribute('aria-pressed', 'false')
  })

  it('gives the district manager the alarms of every range', async () => {
    renderAs('mock-4')

    const shown = await items()
    expect(shown).toHaveLength(2)
    expect(shown[1]).toHaveTextContent('Skład przy leśniczówce')
  })

  it('says when there are no alarms', async () => {
    const user = renderAs('mock-5')
    await items()

    await user.click(filter('Kradzież'))
    expect(await screen.findByText('Brak alarmów')).toBeInTheDocument()
  })

  it('shows the backend error', async () => {
    renderAs('wrong-token')
    expect(await screen.findByRole('alert')).toHaveTextContent('Sesja wygasła')
  })
})
