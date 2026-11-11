import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue, type AuthResponse } from '../auth/context'
import type { components } from '../../lib/api/schema'
import { RequestWorkspace } from './RequestWorkspace'

const session: AuthResponse = { user: { id: 'customer-id', telegram_id: '123', display_name: 'Test customer', role: 'customer' }, capabilities: [], csrf_token: 'session-csrf', environment: 'simulation' }
const row: components['schemas']['RequestResponse'] = { id: 'request-id', service_project_id: 'project-id', customer_id: 'customer-id', service_type: 'printing', stage_kind: 'printing', mode: 'simulation', status: 'draft', version: 1, revision: 1, canonical_spec_sha256: 'a'.repeat(64), customer_notes: 'Original notes', created_at: '2026-11-11T00:00:00Z', updated_at: '2026-11-11T00:00:00Z' }
function mount(owner = false, authenticated = true) {
  const auth: AuthContextValue = { status: authenticated ? 'authenticated' : 'unauthenticated', session: authenticated ? session : null, error: null, isLoggingOut: false, refreshSession: vi.fn(), logout: vi.fn() }
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><AuthContext.Provider value={auth}><MemoryRouter><RequestWorkspace owner={owner} /></MemoryRouter></AuthContext.Provider></QueryClientProvider>)
}
const page = (items = [row], next_offset: number | null = null) => Response.json({ items, next_offset })
beforeEach(() => { vi.restoreAllMocks() })

describe('M03 authenticated draft workspace', () => {
  it('keeps mock previews disconnected and waits for explicit authenticated loading', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([]))
    vi.stubGlobal('fetch', fetcher)
    const disconnected = mount(false, false)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(fetcher).not.toHaveBeenCalled()
    disconnected.unmount()
    mount()
    expect(fetcher).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Open project drafts' }))
    expect(await screen.findByText('No drafts here yet')).toBeInTheDocument()
    expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/requests?limit=20&offset=0')
  })

  it('creates typed simulation drafts with same-origin cookies, CSRF and an idempotency key', async () => {
    const fetcher = vi.fn().mockImplementation((_path: string, request: RequestInit) => Promise.resolve(request.method === 'POST' ? Response.json({ request: row }, { status: 201 }) : page([])))
    vi.stubGlobal('fetch', fetcher)
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Open project drafts' }))
    await screen.findByText('No drafts here yet')
    fireEvent.change(screen.getByLabelText('Service'), { target: { value: 'design_and_print' } })
    fireEvent.change(screen.getByLabelText('Project notes (optional)'), { target: { value: 'An idea' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save simulation draft' }))
    await waitFor(() => expect(fetcher.mock.calls.some(call => call[1]?.method === 'POST')).toBe(true))
    const call = fetcher.mock.calls.find(call => call[1]?.method === 'POST') as [string, RequestInit]
    expect(call[0]).toBe('/api/v1/requests')
    expect(call[1].credentials).toBe('same-origin')
    expect(new Headers(call[1].headers).get('X-CSRF-Token')).toBe('session-csrf')
    expect(new Headers(call[1].headers).get('Idempotency-Key')).toMatch(/^[a-f0-9-]{36}$/)
    expect(JSON.parse(call[1].body as string)).toEqual({ service_type: 'design_and_print', customer_notes: 'An idea' })
    await waitFor(() => expect(screen.getByLabelText('Project notes (optional)')).toHaveValue(''))
    expect(screen.queryByRole('button', { name: /submit|pay|quote/i })).not.toBeInTheDocument()
  })

  it.each(['network', 'server'])('reuses the command key after an ambiguous %s failure', async failure => {
    let attempts = 0
    const fetcher = vi.fn().mockImplementation((_path: string, request: RequestInit) => {
      if (request.method === 'POST') {
        if (++attempts === 1) return failure === 'network' ? Promise.reject(new TypeError('offline')) : Promise.resolve(Response.json({ code: 'unavailable' }, { status: 503 }))
        return Promise.resolve(Response.json({ request: row }, { status: 201 }))
      }
      return Promise.resolve(page([]))
    })
    vi.stubGlobal('fetch', fetcher)
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Open project drafts' }))
    await screen.findByText('No drafts here yet')
    fireEvent.click(screen.getByRole('button', { name: 'Save simulation draft' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(failure === 'network' ? 'Cannot reach the service' : 'The service is unavailable')
    expect(screen.getByRole('button', { name: 'Save simulation draft' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry change' }))
    await waitFor(() => expect(attempts).toBe(2))
    const commands = fetcher.mock.calls.filter(call => call[1]?.method === 'POST')
    expect(new Headers(commands[0]?.[1]?.headers).get('Idempotency-Key')).toBe(new Headers(commands[1]?.[1]?.headers).get('Idempotency-Key'))
  })

  it('updates notes and cancels with the current server version and a reason', async () => {
    const fetcher = vi.fn().mockImplementation((_path: string, request: RequestInit) => Promise.resolve(request.method === 'GET' ? page() : Response.json(row)))
    vi.stubGlobal('fetch', fetcher)
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Open project drafts' }))
    await screen.findByLabelText('Draft notes')
    fireEvent.change(screen.getByLabelText('Draft notes'), { target: { value: 'Revised notes' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(fetcher.mock.calls.some(call => call[1]?.method === 'PATCH')).toBe(true))
    const update = fetcher.mock.calls.find(call => call[1]?.method === 'PATCH') as [string, RequestInit]
    expect(JSON.parse(update[1].body as string)).toEqual({ expected_version: 1, customer_notes: 'Revised notes' })
    await waitFor(() => expect(screen.getByLabelText('Cancellation reason')).not.toBeDisabled())
    fireEvent.change(screen.getByLabelText('Cancellation reason'), { target: { value: 'No longer needed' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel draft' }))
    await waitFor(() => expect(fetcher.mock.calls.some(call => call[0]?.endsWith('/transitions'))).toBe(true))
    const cancel = fetcher.mock.calls.find(call => call[0]?.endsWith('/transitions')) as [string, RequestInit]
    expect(JSON.parse(cancel[1].body as string)).toEqual({ expected_version: 1, target: 'cancelled', reason: 'No longer needed' })
  })

  it('loads the owner endpoint without a customer creation form or impersonation editor', async () => {
    const fetcher = vi.fn().mockResolvedValue(page([{ ...row, customer_id: 'another-customer' }]))
    vi.stubGlobal('fetch', fetcher)
    mount(true)
    fireEvent.click(screen.getByRole('button', { name: 'Load customer drafts' }))
    expect(await screen.findByText('Original notes')).toBeInTheDocument()
    expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/owner/requests?limit=20&offset=0')
    expect(screen.queryByLabelText('Draft notes')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save simulation draft' })).not.toBeInTheDocument()
  })

  it('shows loading, recoverable errors and bounded pagination', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ code: 'unavailable' }, { status: 503 })).mockResolvedValueOnce(page([row], 20)).mockResolvedValueOnce(page([]))
    vi.stubGlobal('fetch', fetcher)
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Open project drafts' }))
    expect(await screen.findByRole('heading', { name: 'Requests unavailable' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByLabelText('Draft notes')
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    expect(await screen.findByText('No drafts here yet')).toBeInTheDocument()
    expect(fetcher.mock.calls[2]?.[0]).toBe('/api/v1/requests?limit=20&offset=20')
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Previous page' })).not.toBeDisabled()
  })
})
