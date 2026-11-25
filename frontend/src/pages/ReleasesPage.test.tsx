import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setToken } from '@/api/client'
import type { Sensor } from '@/api/types'

// Ending a release edits mock state, so every test loads a fresh page and mock
let ReleasesPage: typeof import('./ReleasesPage').ReleasesPage
let listSensors: typeof import('@/api/sensors').listSensors

beforeEach(async () => {
  // midday: mock releases are "now ± a few hours", which near midnight crosses the date
  // and the page then shows the day too. Only Date is faked, the mock's delays stay real.
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 5, 15, 12, 0))
  vi.resetModules()
  ReleasesPage = (await import('./ReleasesPage')).ReleasesPage
  listSensors = (await import('@/api/sensors')).listSensors
})

afterEach(() => {
  vi.useRealTimers()
})

// every mock call waits 400 ms, and a tab or filter change makes one or two
const slow = { timeout: 3000 }

// mock tokens: mock-3 forester of Dąbrowa, mock-4 district manager, mock-5 forester of Olszyny
async function renderAs(token: string, canEnd = token !== 'mock-4') {
  setToken(token)
  // the page gets the sensors from the map
  const sensors: Sensor[] = await listSensors()
  const onEnded = vi.fn()
  render(<ReleasesPage sensors={sensors} canEnd={canEnd} onEnded={onEnded} />)
  return { user: userEvent.setup(), onEnded }
}

const cards = async (list: string) => within(await screen.findByRole('list', { name: list }, slow)).getAllByRole('listitem')
const names = (items: HTMLElement[]) => items.map((li) => within(li).getByText(/^Skład/).textContent)
const tab = (name: string) => within(screen.getByRole('group', { name: 'Pokaż wydania' })).getByRole('button', { name })
const period = (name: string) => within(screen.getByRole('group', { name: 'Okres' })).getByRole('button', { name })

describe('ReleasesPage, ongoing', () => {
  it('shows the ongoing releases of the forester range, until when and for whom', async () => {
    await renderAs('mock-3')

    const [release, ...rest] = await cards('Trwające wydania')
    expect(rest).toHaveLength(0)
    expect(release).toHaveTextContent('Skład przy szlabanie')
    // mock: muted for 2 h from when it loaded
    expect(release).toHaveTextContent(/do \d{1,2}:\d{2} · jeszcze (2 h|1 h 59 min)/)
    expect(release).toHaveTextContent('Transdrew Sp. z o.o. · 24 kłody')
    expect(release).toHaveTextContent(/blazej · od /)
    expect(tab('Trwające')).toHaveAttribute('aria-pressed', 'true')
  })

  it('ends a release from its card after the forester confirms', async () => {
    const { user, onEnded } = await renderAs('mock-3')
    const [release] = await cards('Trwające wydania')

    await user.click(within(release).getByRole('button', { name: 'Zakończ wyciszenie' }))
    const panel = await screen.findByRole('dialog', { name: 'Zakończyć wyciszenie?' })
    expect(panel).toHaveTextContent('Czujnik „Skład przy szlabanie” znów będzie zgłaszał alarmy.')
    await user.click(within(panel).getByRole('button', { name: 'Zakończ' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Skład przy szlabanie znów czuwa')
    expect(screen.getByText('Żaden czujnik nie jest teraz wyciszony.')).toBeInTheDocument()
    // the map refreshes, so the pin and the badge follow at once
    expect(onEnded).toHaveBeenCalledOnce()
  })

  it('changes nothing when the forester cancels', async () => {
    const { user, onEnded } = await renderAs('mock-3')
    const [release] = await cards('Trwające wydania')

    await user.click(within(release).getByRole('button', { name: 'Zakończ wyciszenie' }))
    const panel = await screen.findByRole('dialog', { name: 'Zakończyć wyciszenie?' })
    await user.click(within(panel).getByRole('button', { name: 'Anuluj' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(await cards('Trwające wydania')).toHaveLength(1)
    expect(onEnded).not.toHaveBeenCalled()
  })

  it('lets a district manager only look', async () => {
    await renderAs('mock-4')

    const [release] = await cards('Trwające wydania')
    expect(release).toHaveTextContent('Skład przy szlabanie')
    expect(within(release).queryByRole('button')).not.toBeInTheDocument()
  })

  it('says so when no sensor of the range is muted', async () => {
    await renderAs('mock-5')

    expect(await screen.findByText('Żaden czujnik nie jest teraz wyciszony.', {}, slow)).toBeInTheDocument()
  })
})

describe('ReleasesPage, history', () => {
  it('shows the finished releases of the last 30 days, newest first', async () => {
    const { user } = await renderAs('mock-3')
    await cards('Trwające wydania')

    await user.click(tab('Historia'))

    const history = await cards('Zakończone wydania')
    // mock: 1, 3, 10 and 18 days ago in Dąbrowa; the Olszyny ones are not there
    expect(names(history)).toEqual([
      'Skład przy paśniku',
      'Skład przy drodze 5',
      'Skład przy szlabanie',
      'Skład przy paśniku',
    ])
    expect(history[0]).toHaveTextContent('Trans-Las · 18 kłód')
    expect(history[0]).toHaveTextContent(/\d{1,2}:\d{2} – \d{1,2}:\d{2}/)
    expect(history[1]).toHaveTextContent('„dwa kursy”')
    // no end button in the history
    expect(within(history[0]).queryByRole('button')).not.toBeInTheDocument()
    expect(period('30 dni')).toHaveAttribute('aria-pressed', 'true')
  })

  it('filters by sensor and period', async () => {
    const { user } = await renderAs('mock-3')
    await cards('Trwające wydania')
    await user.click(tab('Historia'))
    await cards('Zakończone wydania')

    await user.selectOptions(screen.getByLabelText('Czujnik'), 'Skład przy drodze 5')
    await user.click(period('Wszystko'))
    // 3, 41 and 200 days ago
    expect(await cards('Zakończone wydania')).toHaveLength(3)

    await user.click(period('7 dni'))
    await vi.waitFor(async () => expect(await cards('Zakończone wydania')).toHaveLength(1), slow)

    await user.selectOptions(screen.getByLabelText('Czujnik'), 'Skład przy szlabanie')
    expect(await screen.findByText('Brak zakończonych wydań w tym okresie.', {}, slow)).toBeInTheDocument()
  })

  it('offers only the sensors of the forester range', async () => {
    const { user } = await renderAs('mock-5')
    await screen.findByText('Żaden czujnik nie jest teraz wyciszony.', {}, slow)
    await user.click(tab('Historia'))

    const options = within(screen.getByLabelText('Czujnik')).getAllByRole('option')
    expect(options.map((o) => o.textContent)).not.toContain('Skład przy paśniku')
    expect(options.map((o) => o.textContent)).toContain('Skład przy leśniczówce')
  })
})
