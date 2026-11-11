import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth/context'
import { ApiError, apiPrivateBlob, apiRequest, apiUpload } from '../../lib/api/client'
import { DesignPage } from './DesignPage'
import { ProofViewer } from './ProofViewer'
import { DesignQueue } from './DesignQueue'
import { NewDesignRequest } from './NewDesignRequest'
import { DESIGN_ID, designData, proofData, SCOPE_ID, VERSION_ID } from './test-fixtures'
import type { DesignBrief, DesignDetail } from './types'
import { CUSTOMER_ID } from '../printing/test-fixtures'

vi.mock('../../lib/api/client', async importOriginal => ({ ...await importOriginal<typeof import('../../lib/api/client')>(), apiRequest: vi.fn(), apiUpload: vi.fn(), apiPrivateBlob: vi.fn() }))
const request = vi.mocked(apiRequest), upload = vi.mocked(apiUpload)
let stored: DesignDetail
function mount(owner = false, child?: React.ReactNode) {
  const auth: AuthContextValue = { status: 'authenticated', session: { user: { id: owner ? 'owner-id' : CUSTOMER_ID, display_name: 'Test user', telegram_id: '123', role: owner ? 'owner' : 'customer' }, capabilities: [], csrf_token: 'design-test-csrf', environment: 'simulation' }, error: null, isLoggingOut: false, logout: vi.fn(), refreshSession: vi.fn() }
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={cache}><AuthContext.Provider value={auth}><MemoryRouter initialEntries={[`/app/design-projects/${DESIGN_ID}`]}><Routes><Route path="/app/design-projects/:designId" element={child ?? <DesignPage owner={owner} />} /></Routes></MemoryRouter></AuthContext.Provider></QueryClientProvider>)
}
beforeEach(() => {
  stored = designData(); request.mockReset(); upload.mockReset(); vi.mocked(apiPrivateBlob).mockReset().mockResolvedValue(new Blob(['Preview text <script> is plain text.']))
  request.mockImplementation(async (path, options) => {
    if (path.startsWith('/design-projects?')) return { items: [structuredClone(stored)], next_offset: null }
    if (options?.method) {
      const body = JSON.parse(options.body as string) as { brief?: DesignBrief; expected_version: number }
      expect(body.expected_version).toBe(stored.request.version)
      if (body.brief) stored.brief = body.brief
      if (path.endsWith('/submit')) { stored.state = 'brief_received'; stored.request.status = 'submitted' }
      if (path.endsWith('/scope-agreements')) { stored.state = 'awaiting_payment'; stored.approved_scope_id = SCOPE_ID }
      if (path.endsWith('/simulation-fixture')) { stored.state = 'designing'; stored.simulation_fixture = true }
      if (path.endsWith('/reviews')) { stored.state = 'approved'; stored.approved_version_id = VERSION_ID }
      stored.request.version += 1
    }
    return structuredClone(stored)
  })
})

describe('M05 private design workflow', () => {
  it('autosaves a model-free brief and recovers it after remount', async () => {
    const first = mount()
    await screen.findByRole('heading', { name: 'Your design draft' })
    fireEvent.change(screen.getByLabelText('Project description'), { target: { value: 'Updated private design brief' } })
    expect(screen.getByRole('button', { name: 'Continue design intake' })).toBeDisabled()
    await waitFor(() => expect(stored.brief.description).toBe('Updated private design brief'), { timeout: 2500 })
    await screen.findByText('Design brief saved')
    const call = request.mock.calls.find(([,options]) => options?.method === 'PATCH')
    expect(call?.[1]?.csrfToken).toBe('design-test-csrf'); expect(call?.[1]?.idempotencyKey).toBeTruthy()
    first.unmount(); mount()
    await screen.findByDisplayValue('Updated private design brief')
    expect(screen.queryByLabelText('Choose model files')).not.toBeInTheDocument()
  })
  it('submits a complete design brief with no print items or attachments', async () => {
    mount(); await screen.findByRole('heading', { name: 'Your design draft' })
    fireEvent.click(screen.getByRole('button', { name: '3. Review' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit design brief' }))
    await screen.findByRole('heading', { name: 'Design request details' })
    expect(stored.state).toBe('brief_received')
    expect(upload).not.toHaveBeenCalled()
  })
  it('agrees only to a named simulation scope without exposing fixture controls to customers', async () => {
    stored = proofData(); stored.state = 'scoping'; stored.versions = []; stored.scopes[0]!.agreed = false
    mount(); await screen.findByRole('heading', { name: 'Design request details' })
    fireEvent.click(screen.getByRole('button', { name: 'Agree to simulation scope 1' }))
    await waitFor(() => expect(request.mock.calls.some(([path, options]) => path.endsWith('/scope-agreements') && JSON.parse(options?.body as string).scope_id === SCOPE_ID)).toBe(true))
    expect(screen.queryByRole('button', { name: 'Start simulation-paid fixture' })).not.toBeInTheDocument()
  })
  it('reviews the exact latest proof and never offers approval of historical versions', async () => {
    stored = proofData(); stored.versions.unshift({ ...stored.versions[0]!, id: 'old-version', number: 1, release_notes: 'Old historical proof' })
    mount(); await screen.findByRole('heading', { name: 'Review exact proof version 2' })
    expect(screen.queryByRole('button', { name: 'Approve proof version 1' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Request revision of version 2' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Customer feedback'), { target: { value: 'Looks correct' } })
    fireEvent.click(screen.getByRole('button', { name: 'Approve proof version 2' }))
    await waitFor(() => expect(request.mock.calls.some(([path, options]) => path.endsWith('/reviews') && JSON.parse(options?.body as string).design_version_id === VERSION_ID)).toBe(true))
  })
  it('requires explicit Owner confirmation before activating a simulation fixture', async () => {
    stored = proofData(); stored.state = 'awaiting_payment'; stored.simulation_fixture = false
    mount(true); await screen.findByRole('heading', { name: 'Explicit simulation fixture' })
    expect(screen.getByRole('button', { name: 'Start simulation-paid fixture' })).toBeDisabled()
    fireEvent.click(screen.getByLabelText('I confirm this is a simulation with no real funds'))
    fireEvent.click(screen.getByRole('button', { name: 'Start simulation-paid fixture' }))
    await waitFor(() => expect(request.mock.calls.some(([path, options]) => path.startsWith('/owner/') && path.endsWith('/simulation-fixture') && JSON.parse(options?.body as string).confirm_simulation === true)).toBe(true))
  })
  it('keeps the same mutation key for an exact retry after a stale response', async () => {
    request.mockRejectedValueOnce(new ApiError('Stale design.', 409, 'stale_version'))
    mount(); await screen.findByRole('heading', { name: 'Design unavailable' })
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByRole('heading', { name: 'Your design draft' })
    request.mockRejectedValueOnce(new ApiError('Stale design.', 409, 'stale_version'))
    fireEvent.change(screen.getByLabelText('Project description'), { target: { value: 'A queued design change' } })
    await screen.findByRole('heading', { name: 'Design change needs attention' })
    const failed = request.mock.calls.find(([,options]) => options?.method === 'PATCH')
    fireEvent.click(screen.getByRole('button', { name: 'Retry exact change' }))
    await waitFor(() => expect(stored.brief.description).toBe('A queued design change'))
    const calls = request.mock.calls.filter(([,options]) => options?.method === 'PATCH')
    expect(calls[1]?.[1]?.idempotencyKey).toBe(failed?.[1]?.idempotencyKey)
  })
  it('loads an authorized design queue and links to its correct workspace', async () => {
    stored = proofData(); mount(true, <DesignQueue owner />)
    fireEvent.click(screen.getByRole('button', { name: 'Load design reviews' }))
    expect(await screen.findByRole('link', { name: `Open design ${DESIGN_ID.slice(0,8)}` })).toHaveAttribute('href', `/owner/designs/${DESIGN_ID}`)
  })
  it('renders private text proofs as text without executing markup', async () => {
    vi.mocked(apiPrivateBlob).mockResolvedValue(Object.assign(new Blob(), { text: async () => 'Preview <script>unsafe()</script> stays plain text.' }))
    render(<ProofViewer file={proofData().versions[0]!.preview} />)
    fireEvent.click(screen.getByRole('button', { name: 'View proof proof.txt' }))
    expect(await screen.findByText('Preview <script>unsafe()</script> stays plain text.')).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
  })
  it('creates combined service drafts through the existing request API', async () => {
    request.mockImplementation(async (path, options) => { if (path === '/requests') { expect(JSON.parse(options?.body as string).service_type).toBe('design_and_print'); return { request: stored.request } } return stored })
    mount(false, <NewDesignRequest />)
    fireEvent.change(screen.getByLabelText('Design service'), { target: { value: 'design_and_print' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create design draft' }))
    await waitFor(() => expect(request.mock.calls.some(([path]) => path === '/requests')).toBe(true))
    expect(request.mock.calls.find(([path]) => path === '/requests')?.[1]?.idempotencyKey).toBeTruthy()
  })
})
