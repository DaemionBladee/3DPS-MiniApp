import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TelegramProvider } from '../integrations/telegram/TelegramProvider'
import { App } from './App'
import { createQueryClient } from './query-client'
import { AuthProvider } from '../features/auth/AuthProvider'

function renderApp(path = '/') {
  return render(<QueryClientProvider client={createQueryClient()}><TelegramProvider>
    <AuthProvider><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AuthProvider>
  </TelegramProvider></QueryClientProvider>)
}

beforeEach(() => {
  vi.stubEnv('VITE_TELEGRAM_MOCK', 'true')
  delete window.Telegram
})

describe('M01 workspaces', () => {
  it('renders the customer shell and inert services without automatic API calls', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    renderApp()
    expect(await screen.findByRole('heading', { name: 'Your next idea, made real.' })).toBeInTheDocument()
    for (const name of ['3D printing', 'Custom design', 'Design + print']) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'Start a project' })).toBeDisabled()
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content')
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('navigates between exactly two preview workspaces and changes appearance', async () => {
    renderApp('/app')
    fireEvent.click(await screen.findByRole('button', { name: 'Owner' }))
    expect(await screen.findByRole('heading', { name: 'Your workshop, at a glance.' })).toBeInTheDocument()
    for (const name of ['Reviews', 'Payments', 'Production', 'Inventory']) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument()
    }
    fireEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }))
    expect(document.documentElement.dataset.theme).toBe('dark')
    fireEvent.click(screen.getByRole('button', { name: 'Customer' }))
    expect(await screen.findByRole('heading', { name: 'Your next idea, made real.' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /operator/i })).not.toBeInTheDocument()
  })

  it('shows an honest missing-backend error and allows retry using Query', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(Response.json({ status: 'ok' }))
    vi.stubGlobal('fetch', fetcher)
    renderApp('/app')
    fireEvent.click(await screen.findByRole('button', { name: 'Check connection' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Service not connected')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Service reachable')
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/health')
  })

  it('announces loading while a connection check is still pending', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => { /* Await a server response. */ })))
    renderApp('/app')
    fireEvent.click(await screen.findByRole('button', { name: 'Check connection' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Checking service connection…')
    expect(screen.queryByRole('button', { name: 'Check connection' })).not.toBeInTheDocument()
  })

  it('shows browser guidance unless mock opt-in is explicit; URL hints grant nothing', async () => {
    vi.stubEnv('VITE_TELEGRAM_MOCK', 'false')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ code: 'unauthenticated' }, { status: 401 })))
    renderApp('/owner?role=owner&mock=true')
    expect(await screen.findByRole('heading', { name: 'Open in Telegram' })).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Preview workspace' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Your workshop, at a glance.' })).not.toBeInTheDocument()
  })

  it('does not grant a role to unverified Telegram launch data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(Response.json({ code: 'unauthenticated' }, { status: 401 }))))
    window.Telegram = { WebApp: {
      initData: 'unverified-presentation-only', colorScheme: 'light', themeParams: {},
      ready: vi.fn(), expand: vi.fn(), onEvent: vi.fn(), offEvent: vi.fn(),
    } }
    renderApp('/owner')
    expect(await screen.findByRole('heading', { name: 'Sign-in required' })).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Preview workspace' })).not.toBeInTheDocument()
  })

  it('does not enable a production role override even if the mock flag is set', async () => {
    vi.stubEnv('DEV', false)
    vi.stubEnv('PROD', true)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ code: 'unauthenticated' }, { status: 401 })))
    renderApp('/owner?role=owner')
    expect(await screen.findByRole('heading', { name: 'Open in Telegram' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Owner' })).not.toBeInTheDocument()
  })

  it('renders a recoverable unknown route rather than inventing future screens', async () => {
    renderApp('/app/requests/new')
    expect(await screen.findByRole('heading', { name: 'This idea hasn’t taken shape.' })).toBeInTheDocument()
  })
})
