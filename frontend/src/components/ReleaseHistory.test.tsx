import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { listReleases } from '@/api/releases'
import type { Release, Sensor } from '@/api/types'

import { HISTORY_PAGE, ReleaseHistory } from './ReleaseHistory'

// what goes to the backend and the paging are checked here; the filtering itself is the backend's
// (and the mock's, see mock.test.ts)
vi.mock('@/api/releases', () => ({ listReleases: vi.fn() }))

const DAY = 24 * 60 * 60 * 1000

const sensors = [
  { id: '70B3D57ED0052345', name: 'Skład przy paśniku' },
  { id: '70B3D57ED0051234', name: 'Skład przy drodze 5' },
] as Sensor[]

// `count` finished releases, numbered from `from`
function releases(count: number, from = 1): Release[] {
  return Array.from({ length: count }, (_, i) => ({
    id: from + i,
    sensor_id: '70B3D57ED0052345',
    sensor_name: 'Skład przy paśniku',
    starts_at: '2026-11-20T08:00:00Z',
    ends_at: '2026-11-20T10:00:00Z',
    active: false,
    carrier: null,
    log_count: null,
    comment: null,
    created_by: 'blazej',
  }))
}

function renderHistory() {
  render(<ReleaseHistory sensors={sensors} />)
  return userEvent.setup()
}

const cards = async () => within(await screen.findByRole('list', { name: 'Zakończone wydania' })).getAllByRole('listitem')
const lastQuery = () => vi.mocked(listReleases).mock.lastCall![0]!

beforeEach(() => {
  vi.mocked(listReleases).mockReset().mockResolvedValue(releases(3))
})

describe('ReleaseHistory', () => {
  it('asks for one page of finished releases of the last 30 days', async () => {
    renderHistory()
    await cards()

    const query = lastQuery()
    expect(query).toMatchObject({ active: false, limit: HISTORY_PAGE + 1 })
    expect(query).not.toHaveProperty('sensor_id')
    const days = (Date.now() - Date.parse(query.from!)) / DAY
    expect(days).toBeGreaterThanOrEqual(30)
    expect(days).toBeLessThan(30.01)
  })

  it('shows older releases a page at a time', async () => {
    // one more than a page: there is something older
    vi.mocked(listReleases).mockResolvedValueOnce(releases(HISTORY_PAGE + 1)).mockResolvedValueOnce(releases(3, 51))
    const user = renderHistory()

    expect(await cards()).toHaveLength(HISTORY_PAGE)
    await user.click(screen.getByRole('button', { name: 'Pokaż starsze' }))

    await vi.waitFor(async () => expect(await cards()).toHaveLength(HISTORY_PAGE + 3))
    expect(lastQuery()).toMatchObject({ active: false, offset: HISTORY_PAGE })
    expect(lastQuery().from).toBeDefined()
    // nothing older now
    expect(screen.queryByRole('button', { name: 'Pokaż starsze' })).not.toBeInTheDocument()
  })

  it('has no "show older" when everything fits on one page', async () => {
    renderHistory()

    expect(await cards()).toHaveLength(3)
    expect(screen.queryByRole('button', { name: 'Pokaż starsze' })).not.toBeInTheDocument()
  })

  it('asks again for the chosen sensor, and for all time without a start', async () => {
    const user = renderHistory()
    await cards()

    await user.selectOptions(screen.getByLabelText('Czujnik'), 'Skład przy drodze 5')
    await vi.waitFor(() => expect(lastQuery()).toMatchObject({ sensor_id: '70B3D57ED0051234' }))

    await user.click(within(screen.getByRole('group', { name: 'Okres' })).getByRole('button', { name: 'Wszystko' }))
    await vi.waitFor(() => expect(lastQuery()).not.toHaveProperty('from'))
    expect(lastQuery()).toMatchObject({ sensor_id: '70B3D57ED0051234' })
  })

  it('lists the sensors alphabetically after "all sensors"', () => {
    renderHistory()

    const options = within(screen.getByLabelText('Czujnik')).getAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual([
      'Wszystkie czujniki',
      'Skład przy drodze 5',
      'Skład przy paśniku',
    ])
  })

  it('says so when nothing was released yet', async () => {
    vi.mocked(listReleases).mockResolvedValue([])
    const user = renderHistory()

    expect(await screen.findByText('Brak zakończonych wydań w tym okresie.')).toBeInTheDocument()
    await user.click(within(screen.getByRole('group', { name: 'Okres' })).getByRole('button', { name: 'Wszystko' }))
    expect(await screen.findByText('Brak zakończonych wydań.')).toBeInTheDocument()
  })

  it('shows the backend error', async () => {
    vi.mocked(listReleases).mockRejectedValue(new ApiError(500, 'Błąd serwera'))
    renderHistory()

    expect(await screen.findByRole('alert')).toHaveTextContent('Błąd serwera')
  })
})
