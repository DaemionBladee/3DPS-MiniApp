import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth/context'
import { PricingPanel } from './PricingPanel'
import { OwnerPricingWorkspace } from './OwnerPricingWorkspace'

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../../lib/api/client', () => ({ apiRequest: api }))
let value: Record<string, unknown> | null
function mount(owner = false, design = false, workspace = false) {
  const auth: AuthContextValue = { status: 'authenticated', session: { user: { id: 'user-1', telegram_id: '123', display_name: 'Test', role: owner ? 'owner' : 'customer' }, csrf_token: 'test-csrf', environment: 'simulation', capabilities: [] }, error: null, isLoggingOut: false, logout: vi.fn(), refreshSession: vi.fn() }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><AuthContext.Provider value={auth}>{workspace ? <OwnerPricingWorkspace /> : <PricingPanel requestId="request-1" version={7} owner={owner} design={design} scopeId="scope-1" />}</AuthContext.Provider></QueryClientProvider>)
}
beforeEach(() => {
  value = { id: 'estimate-1', number: 1, currency_code: 'MMK', estimated_total: '123.00000000', priced: true, current: true, decision: 'review', policy_version: 1, request_revision: 3, stale_reasons: [], assumptions: ['simulation_only'], expires_at: '2099-01-01T00:00:00Z' }
  api.mockReset()
  api.mockImplementation(async (path: string, options?: RequestInit) => path === '/requests/request-1' ? { version: 9 } : options?.method === 'POST' ? { estimate_id: 'estimate-1' } : { estimate: value })
})
describe('M07 simulation pricing', () => {
  it('shows only the server total and no checkout or acceptance', async () => {
    mount()
    await screen.findByText('Estimated total: 123.00000000 MMK')
    expect(screen.getByText(/NON-BINDING TEST ESTIMATE/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /pay|accept|production/i })).not.toBeInTheDocument()
    expect(screen.queryByText('Owner cost breakdown and eligibility')).not.toBeInTheDocument()
  })
  it.each(['stale', 'expired', 'unknown'])('hides %s prices', async kind => {
    value = { ...value, ...(kind === 'stale' ? { current: false, stale_reasons: ['pricing_policy_changed'] } : kind === 'expired' ? { expires_at: '2000-01-01T00:00:00Z' } : { priced: false, estimated_total: null }) }
    mount()
    await screen.findByText('Current price unavailable — review or refresh required.')
    expect(screen.queryByText(/Estimated total:/)).not.toBeInTheDocument()
  })
  it('uses current version, CSRF and a stable idempotency key after an ambiguous failure', async () => {
    let failures = 0
    api.mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/requests/request-1') return { version: 9 }
      if (options?.method === 'POST' && failures++ === 0) throw new Error('Synthetic connection lost')
      return { estimate: value }
    })
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Calculate test estimate' }))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Retry exact estimate command' }))
    await waitFor(() => expect(api.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(2))
    const calls = api.mock.calls.filter(([, options]) => options?.method === 'POST')
    expect(calls[0]?.[1]).toEqual(calls[1]?.[1])
    expect(calls[0]?.[1]?.csrfToken).toBe('test-csrf')
    expect(JSON.parse(calls[0]?.[1]?.body as string)).toEqual({ expected_version: 9 })
  })
  it('keeps customer design estimates read-only and in a separate currency', async () => {
    value = { ...value, currency_code: 'XTR', estimated_total: '136.00000000' }
    mount(false, true)
    await screen.findByText('Estimated total: 136.00000000 XTR')
    expect(screen.queryByRole('button', { name: 'Calculate test estimate' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Estimated design hours')).not.toBeInTheDocument()
  })
  it('renders Owner costs, missing inputs and exact provenance', async () => {
    value = { ...value, historical_total: '123', unknown_costs: ['shipping'], policy_checksum: 'policy-hash', source_sha256: 'source-hash', lines: [{ position: 1, component_code: 'material', quantity: '2', rate: '1.5', amount: '3' }], eligibility_rules: [{ code: 'stock', result: 'unknown', detail: 'No fixture' }], policy_snapshot: {}, source_snapshot: {} }
    mount(true)
    await screen.findByText('Missing costs: shipping')
    expect(screen.getByText('Policy SHA-256: policy-hash')).toBeInTheDocument()
    expect(api.mock.calls[0]?.[0]).toBe('/owner/requests/request-1/estimates')
  })
  it('sends Owner effort as decimal strings tied to the exact scope', async () => {
    mount(true, true)
    const button = screen.getByRole('button', { name: 'Calculate test estimate' })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Estimated design hours'), { target: { value: '1.5' } })
    fireEvent.change(screen.getByLabelText('Hours per included revision'), { target: { value: '0.5' } })
    fireEvent.click(button)
    await waitFor(() => expect(api.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(true))
    const call = api.mock.calls.find(([, options]) => options?.method === 'POST')!
    expect(JSON.parse(call[1].body).design_basis).toEqual({ scope_id: 'scope-1', estimated_hours: '1.5', hours_per_revision: '0.5', complexity: 'standard', usage_rights: 'personal' })
  })
  it('does not open Owner configuration for customers', () => {
    mount(false, false, true)
    expect(screen.queryByText('Simulation pricing configuration')).not.toBeInTheDocument()
    expect(api).not.toHaveBeenCalled()
  })
  it('loads configuration only after explicit Owner action', async () => {
    api.mockResolvedValue({ policies: [], availability: null })
    mount(true, false, true)
    expect(api).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Load pricing workspace' }))
    await screen.findByText('Availability fixture: Unknown; manual review required')
    expect(screen.getByRole('button', { name: 'Publish simulation policy version' })).toBeDisabled()
  })
})
