import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { setToken } from '@/api/client'

// Answering an alarm edits mock state, so every test loads a fresh page and mock
let AlarmsPage: typeof import('./AlarmsPage').AlarmsPage

beforeEach(async () => {
  vi.resetModules()
  AlarmsPage = (await import('./AlarmsPage')).AlarmsPage
})

// mock tokens: mock-3 forester of Dąbrowa, mock-4 district manager, mock-5 forester of Olszyny
async function renderAs(token: string, canRespond = token !== 'mock-4') {
  setToken(token)
  const onAnswered = vi.fn()
  render(<AlarmsPage canRespond={canRespond} onAnswered={onAnswered} />)
  return { user: userEvent.setup(), onAnswered }
}

const items = async () => within(await screen.findByRole('list', { name: 'Alarmy' })).getAllByRole('listitem')
const filter = (name: string) => within(screen.getByRole('group', { name: 'Pokaż alarmy' })).getByRole('button', { name })

describe('AlarmsPage', () => {
  it('shows only new alarms of the forester range by default', async () => {
    await renderAs('mock-3')

    const [alarm, ...rest] = await items()
    expect(rest).toHaveLength(0)
    expect(alarm).toHaveTextContent('Skład przy drodze 5')
    expect(alarm).toHaveTextContent('Nowy')
    expect(alarm).toHaveTextContent('pewność 87%')
    expect(alarm).toHaveTextContent('dźwięk + wibracje')
    expect(filter('Nowe')).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows all alarms newest first, with the response and the tampering note', async () => {
    const { user } = await renderAs('mock-3')
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
    // only the new alarm can be answered
    expect(within(all[0]).getByRole('group', { name: 'Co się stało?' })).toBeInTheDocument()
    expect(within(all[1]).queryByRole('group', { name: 'Co się stało?' })).not.toBeInTheDocument()
  })

  it('filters by status', async () => {
    const { user } = await renderAs('mock-3')
    await items()

    await user.click(filter('Fałszywe'))
    const shown = await items()
    expect(shown).toHaveLength(1)
    expect(shown[0]).toHaveTextContent('zwierzę przy stosie')
    expect(filter('Fałszywe')).toHaveAttribute('aria-pressed', 'true')
    expect(filter('Nowe')).toHaveAttribute('aria-pressed', 'false')
  })

  it('gives the district manager the alarms of every range, without answer buttons', async () => {
    await renderAs('mock-4')

    const shown = await items()
    expect(shown).toHaveLength(2)
    expect(shown[1]).toHaveTextContent('Skład przy leśniczówce')
    expect(screen.queryByRole('group', { name: 'Co się stało?' })).not.toBeInTheDocument()
  })

  it('marks a new alarm as theft with a comment', async () => {
    const { user, onAnswered } = await renderAs('mock-3')
    const [alarm] = await items()

    await user.click(within(alarm).getByRole('button', { name: 'Kradzież' }))
    expect(within(alarm).getByText('Potwierdzasz kradzież?')).toBeInTheDocument()
    await user.type(within(alarm).getByLabelText('Komentarz (opcjonalnie)'), 'ślady opon przy stosie')
    await user.click(within(alarm).getByRole('button', { name: 'Zapisz' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Zapisano: Kradzież – Skład przy drodze 5')
    // it is not new any more, so it leaves the default list
    expect(screen.getByText('Brak nowych alarmów')).toBeInTheDocument()
    expect(onAnswered).toHaveBeenCalledOnce()

    await user.click(filter('Kradzież'))
    const thefts = await items()
    expect(thefts[0]).toHaveTextContent('Skład przy drodze 5')
    expect(thefts[0]).toHaveTextContent('Sprawdził(a) blazej')
    expect(thefts[0]).toHaveTextContent('„ślady opon przy stosie”')
  })

  it('marks a false alarm without a comment', async () => {
    const { user } = await renderAs('mock-5')
    const [alarm] = await items()

    await user.click(within(alarm).getByRole('button', { name: 'Fałszywy alarm' }))
    await user.click(within(alarm).getByRole('button', { name: 'Zapisz' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Zapisano: Fałszywy alarm – Skład przy leśniczówce')
  })

  it('goes back without saving', async () => {
    const { user, onAnswered } = await renderAs('mock-3')
    const [alarm] = await items()

    await user.click(within(alarm).getByRole('button', { name: 'Kradzież' }))
    await user.click(within(alarm).getByRole('button', { name: 'Wróć' }))

    expect(within(alarm).getByRole('group', { name: 'Co się stało?' })).toBeInTheDocument()
    expect(within(alarm).getByText('Nowy')).toBeInTheDocument()
    expect(onAnswered).not.toHaveBeenCalled()
  })

  it('says when someone else answered first', async () => {
    const { user } = await renderAs('mock-3')
    const [alarm] = await items()
    // another forester answers in the meantime
    const { respondToAlarm } = await import('@/api/alarms')
    await respondToAlarm(41, { result: 'false_alarm' })

    await user.click(within(alarm).getByRole('button', { name: 'Kradzież' }))
    await user.click(within(alarm).getByRole('button', { name: 'Zapisz' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Alarm ma już odpowiedź')
    // the list is loaded again, and the alarm is no longer new
    expect(await screen.findByText('Brak nowych alarmów')).toBeInTheDocument()
  })

  it('says when there are no alarms', async () => {
    const { user } = await renderAs('mock-5')
    await items()

    await user.click(filter('Kradzież'))
    expect(await screen.findByText('Brak alarmów')).toBeInTheDocument()
  })

  it('shows the backend error', async () => {
    await renderAs('wrong-token')
    expect(await screen.findByRole('alert')).toHaveTextContent('Sesja wygasła')
  })
})
