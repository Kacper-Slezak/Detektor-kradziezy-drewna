import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { InstallButton } from './InstallButton'

// What Chrome sends when the app can be installed
function fireInstallPrompt() {
  const event = Object.assign(new Event('beforeinstallprompt', { cancelable: true }), {
    prompt: vi.fn().mockResolvedValue(undefined),
    userChoice: Promise.resolve({ outcome: 'accepted' }),
  })
  act(() => {
    window.dispatchEvent(event)
  })
  return event
}

describe('InstallButton', () => {
  it('is hidden until the browser allows installing', () => {
    render(<InstallButton />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows the install dialog on click and then hides', async () => {
    render(<InstallButton />)
    const event = fireInstallPrompt()

    expect(event.defaultPrevented).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'Zainstaluj aplikację' }))

    expect(event.prompt).toHaveBeenCalledOnce()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('hides after the app is installed', () => {
    render(<InstallButton />)
    fireInstallPrompt()
    expect(screen.getByRole('button')).toBeInTheDocument()

    act(() => {
      window.dispatchEvent(new Event('appinstalled'))
    })
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
