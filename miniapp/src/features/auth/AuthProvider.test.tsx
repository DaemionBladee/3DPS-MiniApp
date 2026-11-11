import { StrictMode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../../app/App'
import { createQueryClient } from '../../app/query-client'
import { TelegramProvider } from '../../integrations/telegram/TelegramProvider'
import { apiRequest } from '../../lib/api/client'
import { AuthProvider } from './AuthProvider'
import { useAuth } from './context'

const testSession = (role: 'customer' | 'owner' = 'customer') => ({
  user: { id: '00000000-0000-4000-8000-000000000001', telegram_id: '12345', display_name: 'Test person', role },
  capabilities: role === 'owner' ? ['auth.read_self', 'auth.logout', 'owner.auth_check'] : ['auth.read_self', 'auth.logout'],
  csrf_token: 'test-csrf-token', environment: 'simulation',
})
const unauthorized = () => Response.json({ code: 'unauthenticated' }, { status: 401 })

function telegramLaunch(raw = 'raw=exact%2Blaunch&user=%7B%22id%22%3A12345%7D') {
  const unsafeRead = vi.fn(() => { throw new Error('Unsafe identity must not be read') })
  const app = {
    initData: raw, colorScheme: 'light' as const, themeParams: {},
    ready: vi.fn(), expand: vi.fn(), onEvent: vi.fn(), offEvent: vi.fn(),
  }
  Object.defineProperty(app, 'initDataUnsafe', { get: unsafeRead })
  window.Telegram = { WebApp: app }
  return { raw, unsafeRead }
}

function SessionTestControls() {
  const auth = useAuth()
  return <button onClick={auth.refreshSession}>Recheck test session</button>
}

function mount(path = '/app', strict = false) {
  const client = createQueryClient()
  client.setQueryData(['private', 'test-records'], ['private data'])
  const children = <QueryClientProvider client={client}><TelegramProvider><AuthProvider>
    <MemoryRouter initialEntries={[path]}><App /><SessionTestControls /></MemoryRouter>
  </AuthProvider></TelegramProvider></QueryClientProvider>
  return { client, ...render(strict ? <StrictMode>{children}</StrictMode> : children) }
}

beforeEach(() => {
  vi.stubEnv('VITE_TELEGRAM_MOCK', 'false')
  delete window.Telegram
})

describe('real cookie authentication and role boundaries', () => {
  it('restores a server cookie session without resending a Telegram proof', async () => {
    telegramLaunch()
    const fetcher = vi.fn().mockResolvedValue(Response.json(testSession()))
    vi.stubGlobal('fetch', fetcher)
    mount()
    expect(await screen.findByRole('heading', { name: 'Your next idea, made real.' })).toBeInTheDocument()
    expect(screen.getByText('Test person')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/auth/me')
    expect(screen.queryByRole('group', { name: 'Preview workspace' })).not.toBeInTheDocument()
  })

  it('sends exact raw initData once after a 401 even under StrictMode; role comes from the API', async () => {
    const { raw, unsafeRead } = telegramLaunch()
    const fetcher = vi.fn().mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(Response.json(testSession()))
    vi.stubGlobal('fetch', fetcher)
    mount('/owner?role=owner', true)
    expect(await screen.findByRole('heading', { name: 'Owner access required' })).toBeInTheDocument()
    expect(fetcher).toHaveBeenCalledTimes(2)
    const [path, request] = fetcher.mock.calls[1] as [string, RequestInit]
    expect(path).toBe('/api/v1/auth/telegram')
    expect(request.method).toBe('POST')
    expect(JSON.parse(request.body as string)).toEqual({ init_data: raw })
    expect(request.credentials).toBe('same-origin')
    const headers = new Headers(request.headers)
    expect(headers.has('Authorization')).toBe(false)
    expect(headers.has('X-Role')).toBe(false)
    expect(unsafeRead).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('link', { name: 'Back to your workspace' }))
    expect(await screen.findByRole('heading', { name: 'Your next idea, made real.' })).toBeInTheDocument()
  })

  it('shows the Owner workspace only for the server-provisioned owner role and provides customer navigation', async () => {
    telegramLaunch()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(testSession('owner'))))
    mount('/owner')
    expect(await screen.findByRole('heading', { name: 'Your workshop, at a glance.' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'Customer workspace' }))
    expect(await screen.findByRole('heading', { name: 'Your next idea, made real.' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Owner workspace' })).toBeInTheDocument()
  })

  it('revokes logout through the CSRF-protected API and clears private cache without auto-login', async () => {
    telegramLaunch()
    const fetcher = vi.fn().mockResolvedValueOnce(Response.json(testSession()))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetcher)
    const { client } = mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('heading', { name: 'Sign-in required' })).toBeInTheDocument()
    expect(screen.getByText(/Your session ended/)).toBeInTheDocument()
    expect(client.getQueryData(['private', 'test-records'])).toBeUndefined()
    expect(fetcher).toHaveBeenCalledTimes(2)
    const [path, request] = fetcher.mock.calls[1] as [string, RequestInit]
    expect(path).toBe('/api/v1/auth/logout')
    expect(new Headers(request.headers).get('X-CSRF-Token')).toBe('test-csrf-token')
    expect(fetcher.mock.calls.some(([url]) => url === '/api/v1/auth/telegram')).toBe(false)
  })

  it('retains the session and exposes a safe retryable sign-out failure when revocation was not confirmed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(testSession()))
      .mockRejectedValueOnce(new TypeError('internal network detail')))
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the service')
    expect(screen.getByRole('button', { name: 'Sign out' })).not.toBeDisabled()
    expect(screen.getByRole('heading', { name: 'Your next idea, made real.' })).toBeInTheDocument()
  })

  it('invalidates UI identity and private cache on an authenticated API 401 without replaying initData', async () => {
    telegramLaunch()
    const fetcher = vi.fn().mockResolvedValueOnce(Response.json(testSession()))
      .mockResolvedValueOnce(unauthorized())
    vi.stubGlobal('fetch', fetcher)
    const { client } = mount()
    await screen.findByRole('button', { name: 'Sign out' })
    await act(async () => { await expect(apiRequest('/owner/auth-check')).rejects.toMatchObject({ status: 401 }) })
    expect(await screen.findByRole('heading', { name: 'Sign-in required' })).toBeInTheDocument()
    expect(client.getQueryData(['private', 'test-records'])).toBeUndefined()
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('reports connection errors and retries cookie restoration without resubmitting a launch proof', async () => {
    telegramLaunch()
    const fetcher = vi.fn().mockResolvedValueOnce(unauthorized())
      .mockRejectedValueOnce(new TypeError('internal'))
      .mockResolvedValueOnce(unauthorized())
    vi.stubGlobal('fetch', fetcher)
    mount()
    expect(await screen.findByRole('heading', { name: 'Unable to sign in' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Check connection again' }))
    expect(await screen.findByRole('heading', { name: 'Sign-in required' })).toBeInTheDocument()
    expect(fetcher.mock.calls.filter(([url]) => url === '/api/v1/auth/telegram')).toHaveLength(1)
  })

  it('checks the cookie again when returning to the app and detects expired sessions', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(Response.json(testSession())).mockResolvedValueOnce(unauthorized())
    vi.stubGlobal('fetch', fetcher)
    mount()
    await screen.findByRole('button', { name: 'Sign out' })
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
    fireEvent(document, new Event('visibilitychange'))
    expect(await screen.findByRole('heading', { name: 'Open in Telegram' })).toBeInTheDocument()
    expect(fetcher.mock.calls.filter(([url]) => url === '/api/v1/auth/telegram')).toHaveLength(0)
  })

  it('recovers after an initial cookie-read outage using a launch proof that was never submitted', async () => {
    const { raw } = telegramLaunch()
    const fetcher = vi.fn().mockRejectedValueOnce(new TypeError('offline before login'))
      .mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(Response.json(testSession()))
    vi.stubGlobal('fetch', fetcher)
    mount()
    expect(await screen.findByRole('heading', { name: 'Unable to sign in' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Check connection again' }))
    expect(await screen.findByRole('heading', { name: 'Your next idea, made real.' })).toBeInTheDocument()
    const submissions = fetcher.mock.calls.filter(([url]) => url === '/api/v1/auth/telegram')
    expect(submissions).toHaveLength(1)
    expect(JSON.parse((submissions[0]?.[1] as RequestInit).body as string)).toEqual({ init_data: raw })
  })

  it('allows a genuinely new proof after logout in a reused provider but never replays the logout proof', async () => {
    telegramLaunch('launch=before-logout')
    const fetcher = vi.fn().mockResolvedValueOnce(Response.json(testSession()))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(Response.json(testSession()))
    vi.stubGlobal('fetch', fetcher)
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))
    await screen.findByRole('heading', { name: 'Sign-in required' })
    fireEvent.click(screen.getByRole('button', { name: 'Check sign-in again' }))
    await screen.findByText(/Your session ended/)
    expect(fetcher.mock.calls.filter(([url]) => url === '/api/v1/auth/telegram')).toHaveLength(0)
    window.Telegram!.WebApp!.initData = 'launch=fresh-after-logout'
    fireEvent.click(screen.getByRole('button', { name: 'Check sign-in again' }))
    expect(await screen.findByRole('heading', { name: 'Your next idea, made real.' })).toBeInTheDocument()
    const submissions = fetcher.mock.calls.filter(([url]) => url === '/api/v1/auth/telegram')
    expect(submissions).toHaveLength(1)
    expect(JSON.parse((submissions[0]?.[1] as RequestInit).body as string)).toEqual({ init_data: 'launch=fresh-after-logout' })
  })

  it('recovers from a rejected launch only when a different proof is supplied', async () => {
    telegramLaunch('launch=rejected')
    const fetcher = vi.fn().mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(Response.json(testSession()))
    vi.stubGlobal('fetch', fetcher)
    mount()
    await screen.findByRole('heading', { name: 'Sign-in required' })
    fireEvent.click(screen.getByRole('button', { name: 'Check sign-in again' }))
    await screen.findByText(/Your session ended/)
    expect(fetcher.mock.calls.filter(([url]) => url === '/api/v1/auth/telegram')).toHaveLength(1)
    window.Telegram!.WebApp!.initData = 'launch=new-after-rejection'
    fireEvent.click(screen.getByRole('button', { name: 'Check sign-in again' }))
    expect(await screen.findByRole('heading', { name: 'Your next idea, made real.' })).toBeInTheDocument()
    expect(fetcher.mock.calls.filter(([url]) => url === '/api/v1/auth/telegram')).toHaveLength(2)
  })

  it('accepts a fresh Telegram proof after session expiry without replaying the expired launch', async () => {
    const subscriptions = vi.spyOn(document, 'addEventListener')
    telegramLaunch('launch=expired-session')
    const fetcher = vi.fn().mockResolvedValueOnce(Response.json(testSession()))
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(Response.json(testSession()))
    vi.stubGlobal('fetch', fetcher)
    mount()
    await screen.findByRole('button', { name: 'Sign out' })
    await waitFor(() => expect(subscriptions).toHaveBeenCalledWith('visibilitychange', expect.any(Function)))
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
    fireEvent(document, new Event('visibilitychange'))
    await screen.findByRole('heading', { name: 'Sign-in required' })
    expect(fetcher.mock.calls.filter(([url]) => url === '/api/v1/auth/telegram')).toHaveLength(0)
    window.Telegram!.WebApp!.initData = 'launch=fresh-after-expiry'
    fireEvent.click(screen.getByRole('button', { name: 'Check sign-in again' }))
    await screen.findByRole('heading', { name: 'Your next idea, made real.' })
    const submissions = fetcher.mock.calls.filter(([url]) => url === '/api/v1/auth/telegram')
    expect(submissions).toHaveLength(1)
    expect(JSON.parse((submissions[0]?.[1] as RequestInit).body as string)).toEqual({ init_data: 'launch=fresh-after-expiry' })
  })

  it('coalesces recovery checks with an in-flight login instead of submitting the proof twice', async () => {
    telegramLaunch('launch=concurrent-recovery')
    let finishLogin: ((response: Response) => void) | undefined
    const pendingLogin = new Promise<Response>(resolve => { finishLogin = resolve })
    const fetcher = vi.fn().mockResolvedValueOnce(unauthorized())
      .mockReturnValueOnce(pendingLogin).mockResolvedValueOnce(unauthorized())
    vi.stubGlobal('fetch', fetcher)
    mount('/app', true)
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
    fireEvent.click(screen.getByRole('button', { name: 'Recheck test session' }))
    fireEvent.click(screen.getByRole('button', { name: 'Recheck test session' }))
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3))
    await act(async () => { finishLogin?.(Response.json(testSession())) })
    expect(await screen.findByRole('heading', { name: 'Your next idea, made real.' })).toBeInTheDocument()
    expect(fetcher.mock.calls.filter(([url]) => url === '/api/v1/auth/telegram')).toHaveLength(1)
  })

  it('does not let a stale cookie-read failure overwrite a newer restored session', async () => {
    let rejectStaleRead: ((reason: unknown) => void) | undefined
    const staleRead = new Promise<Response>((_resolve, reject) => { rejectStaleRead = reject })
    const fetcher = vi.fn().mockReturnValueOnce(staleRead).mockResolvedValueOnce(Response.json(testSession()))
    vi.stubGlobal('fetch', fetcher)
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Recheck test session' }))
    await screen.findByRole('heading', { name: 'Your next idea, made real.' })
    await act(async () => { rejectStaleRead?.(new TypeError('late stale failure')) })
    expect(screen.getByRole('heading', { name: 'Your next idea, made real.' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Unable to sign in' })).not.toBeInTheDocument()
  })

  it('keeps explicit local mocks isolated from API sessions and production cannot enable them', async () => {
    vi.stubEnv('VITE_TELEGRAM_MOCK', 'true')
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    const view = mount('/owner')
    expect(await screen.findByRole('heading', { name: 'Your workshop, at a glance.' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument()
    expect(fetcher).not.toHaveBeenCalled()
    view.unmount()
    vi.stubEnv('DEV', false)
    vi.stubEnv('PROD', true)
    fetcher.mockResolvedValue(unauthorized())
    mount('/owner?mock=true&role=owner')
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Open in Telegram' })).toBeInTheDocument())
    expect(screen.queryByRole('group', { name: 'Preview workspace' })).not.toBeInTheDocument()
  })
})
