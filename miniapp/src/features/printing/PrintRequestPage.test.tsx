import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth/context'
import { ApiError, apiDownload, apiRequest, apiUpload } from '../../lib/api/client'
import { PrintRequestPage } from './PrintRequestPage'
import { NewPrintRequest } from './NewPrintRequest'
import { OwnerPrintingQueue } from './OwnerPrintingQueue'
import { catalog, CUSTOMER_ID, FILE_ID, intakeData, REQUEST_ID } from './test-fixtures'
import type { IntakeDetail, ItemSpecification } from './types'

vi.mock('../../lib/api/client', async importOriginal => ({ ...await importOriginal<typeof import('../../lib/api/client')>(), apiRequest: vi.fn(), apiUpload: vi.fn(), apiDownload: vi.fn() }))
let stored: IntakeDetail
const request = vi.mocked(apiRequest)
const upload = vi.mocked(apiUpload)

function mount(owner = false, authenticated = true, child?: React.ReactNode) {
  const auth: AuthContextValue = { status: authenticated ? 'authenticated' : 'unauthenticated', session: authenticated ? { user: { id: owner ? 'owner-id' : CUSTOMER_ID, display_name: 'Test Customer', telegram_id: '123', role: owner ? 'owner' : 'customer' }, capabilities: [], csrf_token: 'test-session-csrf', environment: 'simulation' } : null, error: null, isLoggingOut: false, logout: vi.fn(), refreshSession: vi.fn() }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><AuthContext.Provider value={auth}><MemoryRouter initialEntries={[`/app/requests/${REQUEST_ID}`]}><Routes><Route path="*" element={child ?? <PrintRequestPage owner={owner} />} /><Route path="/app/requests/:requestId" element={child ?? <PrintRequestPage owner={owner} />} /></Routes></MemoryRouter></AuthContext.Provider></QueryClientProvider>)
}

beforeEach(() => {
  stored = intakeData()
  request.mockReset(); upload.mockReset(); vi.mocked(apiDownload).mockReset().mockResolvedValue(undefined)
  request.mockImplementation(async (path, options) => {
    if (path.endsWith('/analysis/results')) return { items: [] }
    if (path.endsWith('/analysis')) return { state: 'pending', tasks: stored.tasks, processing_available: false }
    if (path === '/catalog/printing-options') return structuredClone(catalog)
    if (options?.method === 'PATCH') {
      const body = JSON.parse(options.body as string) as { expected_version: number; specification?: ItemSpecification; customer_notes?: string; fulfillment_method?: 'pickup' | 'delivery'; fulfillment_notes?: string }
      expect(body.expected_version).toBe(stored.request.version)
      if (body.specification && stored.items[0]) stored.items[0].specification = body.specification
      if (body.customer_notes !== undefined) stored.request.customer_notes = body.customer_notes
      if (body.fulfillment_method) stored.request.fulfillment_method = body.fulfillment_method
      if (body.fulfillment_notes !== undefined) stored.request.fulfillment_notes = body.fulfillment_notes
      stored.request.version += 1; stored.request.revision += 1
    }
    if (path.endsWith('/submit')) {
      stored.request.status = 'submitted'; stored.request.submitted_revision = stored.request.revision
      stored.request.submitted_at = '2026-11-11T01:00:00Z'; stored.request.submitted_spec = {}
      stored.tasks = [{ id: 'task-id', uploaded_file_id: FILE_ID, request_revision: stored.request.revision, spec_sha256: stored.request.canonical_spec_sha256, kind: 'model_analysis', state: 'pending', attempts: 0, retryable: false }]
    }
    if (path.endsWith('/items') && options?.method === 'POST') stored = intakeData(false)
    return structuredClone(stored)
  })
})

describe('M04 saved private printing workflow', () => {
  it('loads persisted models, shows development options and autosaves/reloads item specifications', async () => {
    const first = mount()
    await screen.findByRole('heading', { name: 'Your printing draft' })
    expect(screen.getByText(catalog.notice)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '2. Specifications' }))
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '7' } })
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    await waitFor(() => expect(stored.items[0]?.specification.quantity).toBe(7), { timeout: 2500 })
    await screen.findByText('Settings saved')
    const patch = request.mock.calls.find(call => call[1]?.method === 'PATCH')
    expect(patch?.[1]?.csrfToken).toBe('test-session-csrf')
    expect(patch?.[1]?.idempotencyKey).toBeTruthy()
    first.unmount()
    mount()
    await screen.findByRole('heading', { name: 'Your printing draft' })
    fireEvent.click(screen.getByRole('button', { name: '2. Specifications' }))
    expect(screen.getByLabelText('Quantity')).toHaveValue(7)
  })

  it('autosaves fulfillment preferences before review', async () => {
    mount()
    await screen.findByRole('heading', { name: 'Your printing draft' })
    fireEvent.click(screen.getByRole('button', { name: '3. Fulfillment' }))
    fireEvent.change(screen.getByLabelText('Preferred handoff'), { target: { value: 'delivery' } })
    fireEvent.change(screen.getByLabelText('Fulfillment notes (optional)'), { target: { value: 'Township preference' } })
    await waitFor(() => expect(stored.request.fulfillment_notes).toBe('Township preference'), { timeout: 2500 })
    expect(stored.request.fulfillment_method).toBe('delivery')
    await screen.findByText('Preferences saved')
  })

  it('pauses stale changes and reloads the saved draft without overwriting another client', async () => {
    // Keep initial reads successful; fail the first mutation instead.
    const normal = request.getMockImplementation()!
    let failed = false
    request.mockReset().mockImplementation(async (path, options) => {
      if (options?.method === 'PATCH' && !failed) {
        failed = true; stored.request.version = 4; stored.items[0]!.specification.quantity = 8
        throw new ApiError('Changed elsewhere', 409, 'stale_version')
      }
      return normal(path, options)
    })
    mount()
    await screen.findByRole('heading', { name: 'Your printing draft' })
    fireEvent.click(screen.getByRole('button', { name: '2. Specifications' }))
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '3' } })
    await screen.findByRole('heading', { name: 'Draft changed or upload conflicted' })
    expect(screen.getByLabelText('Quantity')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Reload saved draft' }))
    await waitFor(() => expect(screen.getByLabelText('Quantity')).toHaveValue(8))
    expect(screen.getByLabelText('Quantity')).not.toBeDisabled()
  })

  it('reports progress, cancels and retries an upload with the same command key', async () => {
    stored = intakeData(false); stored.items = []
    upload.mockImplementationOnce(async (_path, _file, options) => {
      options.onProgress(50)
      return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('cancelled', 'AbortError'))))
    }).mockImplementationOnce(async () => { stored = intakeData(); return structuredClone(stored) })
    mount()
    await screen.findByRole('heading', { name: 'Your printing draft' })
    fireEvent.change(screen.getByLabelText('Choose model files'), { target: { files: [new File(['triangle'], 'triangle.stl')] } })
    await screen.findByRole('progressbar', { name: 'Model upload progress' })
    expect(screen.getByText(/50% transferred/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel upload' }))
    await screen.findByText(/triangle.stl: Upload cancelled/)
    fireEvent.click(screen.getByRole('button', { name: 'Retry upload' }))
    await screen.findByRole('heading', { name: 'triangle.stl' })
    expect(upload.mock.calls).toHaveLength(2)
    expect(upload.mock.calls[0]?.[2].idempotencyKey).toBe(upload.mock.calls[1]?.[2].idempotencyKey)
  })

  it('blocks incomplete submission and shows a persisted pending-analysis confirmation', async () => {
    stored.items[0]!.specification.unit_confirmed = false
    const incomplete = mount()
    await screen.findByRole('heading', { name: 'Your printing draft' })
    fireEvent.click(screen.getByRole('button', { name: '4. Review' }))
    expect(screen.getByRole('button', { name: 'Submit printing request' })).toBeDisabled()
    incomplete.unmount(); stored = intakeData(); mount()
    await screen.findByRole('heading', { name: 'Your printing draft' })
    fireEvent.click(screen.getByRole('button', { name: '4. Review' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit printing request' }))
    await screen.findByRole('heading', { name: 'Printing request submitted' })
    expect(await screen.findByRole('heading', { name: 'Pending analysis' })).toBeInTheDocument()
    expect(screen.getByText(/Analysis is not running yet/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /pay|quote|printer/i })).not.toBeInTheDocument()
  })

  it('gives the Owner read-only specifications, special requirements and authorized download', async () => {
    stored.items[0]!.specification.special_requirements = 'Keep labels legible'
    stored.request.status = 'submitted'; stored.request.submitted_revision = 3; stored.request.submitted_spec = {}
    mount(true)
    await screen.findByRole('heading', { name: 'Printing request submitted' })
    expect(screen.getByText('Keep labels legible')).toBeInTheDocument()
    expect(screen.getByText('Special requirements')).toBeInTheDocument()
    expect(screen.queryByLabelText('Quantity')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Download private model' }))
    expect(apiDownload).toHaveBeenCalledWith(`/files/${FILE_ID}/download`, 'triangle.stl')
  })

  it('never starts business queries or mutations from the isolated preview', () => {
    mount(false, false)
    expect(screen.getByRole('heading', { name: 'Sign in to manage printing requests' })).toBeInTheDocument()
    expect(request).not.toHaveBeenCalled(); expect(upload).not.toHaveBeenCalled()
  })

  it('loads only submitted printing resources for the Owner queue', async () => {
    request.mockResolvedValue({ items: [], next_offset: null })
    mount(true, true, <OwnerPrintingQueue />)
    fireEvent.click(screen.getByRole('button', { name: 'Load submitted printing requests' }))
    await screen.findByText('No submitted print requests')
    expect(request).toHaveBeenCalledWith('/owner/requests?stage_kind=printing&limit=20&offset=0', expect.anything())
  })

  it('creates a server-owned printing draft and follows its opaque ID', async () => {
    request.mockImplementation(async path => path === '/catalog/printing-options' ? catalog : path === '/requests' ? { request: stored.request } : structuredClone(stored))
    mount(false, true, <NewPrintRequest />)
    fireEvent.click(screen.getByRole('button', { name: 'Create printing draft' }))
    await waitFor(() => expect(request.mock.calls.some(call => call[0] === '/requests')).toBe(true))
    const command = request.mock.calls.find(call => call[0] === '/requests')?.[1]
    expect(JSON.parse(command?.body as string)).toEqual({ service_type: 'printing', customer_notes: '' })
    expect(command?.csrfToken).toBe('test-session-csrf')
    expect(command?.idempotencyKey).toBeTruthy()
  })
})
