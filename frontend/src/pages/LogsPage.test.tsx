import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { setToken } from '@/api/client'

let LogsPage: typeof import('./LogsPage').LogsPage
let mock: typeof import('@/api/mock')

beforeEach(async () => {
  vi.resetModules()
  LogsPage = (await import('./LogsPage')).LogsPage
  mock = await import('@/api/mock')
})

async function renderAsAdmin() {
  setToken('mock-1')
  render(<LogsPage />)
  return screen.findByRole('list', { name: 'Logi backendu' })
}

describe('LogsPage', () => {
  it('shows log lines newest first with level and logger', async () => {
    const list = await renderAsAdmin()
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(6)
    expect(items[0]).toHaveTextContent('GET /api/v1/users')
    expect(items[1]).toHaveTextContent('ERROR')
    expect(items[1]).toHaveTextContent('app.services.push')
    expect(items[1]).toHaveTextContent('410 Gone')
  })

  it('filters by level and text', async () => {
    const list = await renderAsAdmin()
    const user = userEvent.setup()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Poziom' }), 'WARNING')
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
    await user.type(screen.getByRole('searchbox', { name: 'Szukaj w logach' }), 'unknown sensor')
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(1)
    expect(items[0]).toHaveTextContent('WARNING')
  })

  it('says the view is off when the backend has it disabled', async () => {
    mock.mockSetLogsEnabled(false)
    setToken('mock-1')
    render(<LogsPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('ADMIN_LOGS_ENABLED=false')
  })
})
