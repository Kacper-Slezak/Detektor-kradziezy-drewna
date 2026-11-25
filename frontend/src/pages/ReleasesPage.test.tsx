import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { setToken } from '@/api/client'
import type { Sensor } from '@/api/types'

// Ending a release edits mock state, so every test loads a fresh page and mock
let ReleasesPage: typeof import('./ReleasesPage').ReleasesPage
let HIGHLIGHT_MS: number
let listSensors: typeof import('@/api/sensors').listSensors

beforeEach(async () => {
  vi.resetModules()
  ReleasesPage = (await import('./ReleasesPage')).ReleasesPage
  HIGHLIGHT_MS = (await import('@/components/ReleaseHistory')).HIGHLIGHT_MS
  listSensors = (await import('@/api/sensors')).listSensors
})

// every mock call waits 400 ms, and a tab or filter change makes one or two
const slow = { timeout: 3000 }

// mock tokens: mock-3 forester of Dąbrowa, mock-4 district manager, mock-5 forester of Olszyny
async function renderAs(token: string, canEnd = token !== 'mock-4', focusId: number | null = null) {
  setToken(token)
  // the page gets the sensors from the map
  const sensors: Sensor[] = await listSensors()
  const onEnded = vi.fn()
  render(<ReleasesPage sensors={sensors} canEnd={canEnd} onEnded={onEnded} focusId={focusId} />)
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
    // mock: muted for 2 h from when it loaded; after 22:00 that is tomorrow, so with the date
    expect(release).toHaveTextContent(/do (\d{2}\.\d{2}\.\d{4}, )?\d{1,2}:\d{2} · jeszcze (2 h|1 h 59 min)/)
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
  it('opens the history at once for a release from the address (a push about its end)', async () => {
    await renderAs('mock-3', true, 9)

    expect(tab('Historia')).toHaveAttribute('aria-pressed', 'true')
    const release = within(await screen.findByRole('list', { name: 'Zakończone wydania' }, slow)).getByRole('listitem', {
      current: true,
    })
    expect(release).toHaveTextContent('Skład przy paśniku')
    expect(release).toHaveAttribute('data-highlighted')
  })

  it('lets the light of that release fade after a moment', async () => {
    await renderAs('mock-3', true, 9)
    const release = within(await screen.findByRole('list', { name: 'Zakończone wydania' }, slow)).getByRole('listitem', {
      current: true,
    })

    await waitFor(() => expect(release).not.toHaveAttribute('data-highlighted'), { timeout: HIGHLIGHT_MS + 1000 })
    // still marked for a screen reader
    expect(release).toHaveAttribute('aria-current', 'true')
  })

  it('finds a release older than 30 days from an old link', async () => {
    await renderAs('mock-3', true, 7)

    const release = within(await screen.findByRole('list', { name: 'Zakończone wydania' }, slow)).getByRole('listitem', {
      current: true,
    })
    expect(release).toHaveTextContent('Skład przy drodze 5')
    expect(period('Wszystko')).toHaveAttribute('aria-pressed', 'true')
  })

  it('says so when the release from the address is not in the history', async () => {
    const { user } = await renderAs('mock-3', true, 999)

    expect(await screen.findByText('Wydania 999 nie ma w historii. Mogło zostać usunięte albo dotyczy innego leśnictwa.', {}, slow)).toBeInTheDocument()
    // other filters: the forester looks for something else now
    await user.click(period('7 dni'))
    expect(screen.queryByText(/Wydania 999/)).not.toBeInTheDocument()
  })

  it('does not light the release again after the forester changed the tab', async () => {
    const { user } = await renderAs('mock-3', true, 9)
    await screen.findByRole('list', { name: 'Zakończone wydania' }, slow)

    await user.click(tab('Trwające'))
    await cards('Trwające wydania')
    await user.click(tab('Historia'))

    const history = await cards('Zakończone wydania')
    expect(history.some((li) => li.hasAttribute('data-highlighted') || li.hasAttribute('aria-current'))).toBe(false)
  })

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
    // the end has its date too when the release went past midnight (mock: 3 h from this hour, a day ago)
    expect(history[0]).toHaveTextContent(/\d{1,2}:\d{2} – (\d{2}\.\d{2}\.\d{4}, )?\d{1,2}:\d{2}/)
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
