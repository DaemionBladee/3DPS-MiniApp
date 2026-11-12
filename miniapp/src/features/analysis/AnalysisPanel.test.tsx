import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthContextValue } from '../auth/context'
import { apiRequest } from '../../lib/api/client'
import type { components } from '../../lib/api/schema'
import { AnalysisPanel } from './AnalysisPanel'
import { ProcessingQueue } from './ProcessingQueue'
import { specification } from '../printing/test-fixtures'

vi.mock('../../lib/api/client', async original => ({ ...await original<typeof import('../../lib/api/client')>(), apiRequest: vi.fn() }))
const api = vi.mocked(apiRequest)
const refresh = vi.fn().mockResolvedValue(undefined)
let state: components['schemas']['AnalysisStatus']['state']
let failure: boolean
const profile: components['schemas']['SimulationProfile'] = {
  id: 'profile-1', key: 'virtual-pla', version: 1, virtual_printer_model_id: 'virtual-1', material_key: 'dev-pla', quality_key: 'dev-standard', configuration: {}, config_sha256: 'c'.repeat(64), engine_version: '2.5.0+UNKNOWN', approval_status: 'approved', active: true, calibrated: false, simulation_only: true,
}
const result: components['schemas']['AnalysisResult'] = {
  id: 'run-1', task_id: 'task-1', request_item_id: 'item-1', uploaded_file_id: 'file-1', request_revision: 4, spec_sha256: 's'.repeat(64), input_sha256: 'a'.repeat(64), outcome: 'estimated',
  geometry: { format: 'stl', unit_key: 'mm', declared_unit: null, dimensions_mm: { x: 20, y: 20, z: 20 }, volume_mm3: 8000, object_count: 1, component_count: 1, triangle_count: 12, watertight: true, boundary_edges: 0, nonmanifold_edges: 0, degenerate_faces: 0, duplicate_faces: 0, winding_errors: 0, build_volume_compatible: true, warnings: ['simulation_only', 'uncalibrated_virtual_profile'], review_reasons: [] },
  estimate: { filament_g: 3.69, print_seconds: 1150, support_g: null, support_estimate_available: false, gcode_sha256: 'b'.repeat(64), canonical_gcode_sha256: 'c'.repeat(64), gcode_bytes: 146026 }, profile, profile_snapshot: {}, engine_version: '2.5.0+UNKNOWN', executable_sha256: 'd'.repeat(64), worker_image: 'sha256:' + 'e'.repeat(64), quantity: 2, submitted_specification: specification, special_requirements: true, simulation_only: true, notice: 'Simulation estimate — not a final quotation.',
}
function mount(owner = false, queue = false) {
  const auth: AuthContextValue = { status: 'authenticated', session: { user: { id: 'user-1', telegram_id: '123', display_name: 'Test', role: owner ? 'owner' : 'customer' }, csrf_token: 'csrf-for-test', environment: 'simulation', capabilities: [] }, error: null, isLoggingOut: false, logout: vi.fn(), refreshSession: vi.fn() }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><AuthContext.Provider value={auth}><MemoryRouter>{queue ? <ProcessingQueue /> : <AnalysisPanel requestId="request-1" version={7} owner={owner} refresh={refresh} />}</MemoryRouter></AuthContext.Provider></QueryClientProvider>)
}
beforeEach(() => {
  state = 'completed'; failure = false; api.mockReset(); refresh.mockClear()
  api.mockImplementation(async (path, options) => {
    if (failure) throw new Error('Test unavailable')
    if (path.endsWith('/retry')) return { request_id: 'request-1', task_id: 'task-1', version: 8, state: 'pending' }
    if (path === '/requests/request-1') return { version: 7 }
    if (path === '/catalog/simulation-profiles') return [profile]
    if (path.endsWith('/analysis/results')) return { items: state === 'completed' ? [result] : [] }
    if (options?.method === 'POST') throw new Error('Unexpected mutation')
    const task = { id: 'task-1', uploaded_file_id: 'file-1', request_revision: 4, spec_sha256: 'a'.repeat(64), kind: 'model_analysis', state: 'failed', attempts: 3, retryable: true, error_code: 'worker_timeout', started_at: null, request_id: 'request-1', customer_id: 'user-1', selected_profile_id: 'profile-1', max_attempts: 3, next_available_at: '2026-11-12T00:00:00Z', completed_at: null, special_requirements: true }
    if (path.startsWith('/owner/processing-tasks')) return { items: [task], next_offset: null }
    return { state, processing_available: state === 'processing', tasks: [task] }
  })
})
describe('M06 private simulation analysis', () => {
  it.each([
    ['pending', 'Pending analysis'], ['processing', 'Processing'], ['completed', 'Analysis completed'],
    ['manual_review', 'Manual review required'], ['needs_clarification', 'Needs clarification'], ['failed', 'Analysis failed'],
  ] as const)('renders %s without commercial actions', async (status, label) => {
    state = status; mount()
    await screen.findByRole('heading', { name: label })
    expect(screen.getByText('Simulation estimate — not a final quotation.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /pay|accept quote|retry/ })).not.toBeInTheDocument()
  })
  it('shows exact model dimensions and per-model estimates with uncertainty and provenance', async () => {
    mount()
    await screen.findByText('Per model: 3.69 g · 20 min (1150 seconds).')
    expect(screen.getByText('20.00 × 20.00 × 20.00')).toBeInTheDocument()
    expect(screen.getByText(/Batch packing and total production time/)).toBeInTheDocument()
    expect(screen.getByText(/Support material estimate unavailable/)).toBeInTheDocument()
    expect(screen.getByText(/Special requirements need Owner review/)).toBeInTheDocument()
    expect(screen.getByText(/uncalibrated virtual profile/)).toBeInTheDocument()
  })
  it('fails explicitly when results cannot be retrieved', async () => {
    failure = true; mount()
    await screen.findByRole('heading', { name: 'Analysis unavailable' })
    expect(screen.queryByText(/Per model:/)).not.toBeInTheDocument()
  })
  it('lets only Owners inspect and reason about bounded retries with CSRF and idempotency', async () => {
    mount(true, true)
    fireEvent.click(screen.getByRole('button', { name: 'Load processing queue' }))
    await screen.findByText('Failure: worker timeout')
    fireEvent.click(screen.getByRole('button', { name: 'Review simulation retry' }))
    const schedule = screen.getByRole('button', { name: 'Schedule simulation retry' })
    expect(schedule).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Review reason'), { target: { value: 'Inspect failed simulation' } })
    fireEvent.click(schedule)
    await waitFor(() => expect(api.mock.calls.some(([path]) => path.endsWith('/retry'))).toBe(true))
    const call = api.mock.calls.find(([path]) => path.endsWith('/retry'))!
    expect(call[1]?.csrfToken).toBe('csrf-for-test')
    expect(call[1]?.idempotencyKey).toBeTruthy()
    expect(JSON.parse(call[1]?.body as string)).toEqual({ expected_version: 7, reason: 'Inspect failed simulation', profile_id: null })
  })
  it('retries an ambiguous Owner command with the original body and idempotency key', async () => {
    const normal = api.getMockImplementation()!
    let attempts = 0
    api.mockImplementation(async (path, options) => {
      if (path.endsWith('/retry') && attempts++ === 0) throw new Error('Synthetic connection lost after commit')
      return normal(path, options)
    })
    mount(true, true)
    fireEvent.click(screen.getByRole('button', { name: 'Load processing queue' }))
    await screen.findByText('Failure: worker timeout')
    fireEvent.click(screen.getByRole('button', { name: 'Review simulation retry' }))
    fireEvent.change(screen.getByLabelText('Review reason'), { target: { value: 'Inspect failed simulation' } })
    fireEvent.click(screen.getByRole('button', { name: 'Schedule simulation retry' }))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Schedule simulation retry' }))
    await waitFor(() => expect(api.mock.calls.filter(([path]) => path.endsWith('/retry'))).toHaveLength(2))
    const calls = api.mock.calls.filter(([path]) => path.endsWith('/retry'))
    expect(calls[0]?.[1]?.idempotencyKey).toBe(calls[1]?.[1]?.idempotencyKey)
    expect(calls[0]?.[1]?.body).toBe(calls[1]?.[1]?.body)
    expect(api.mock.calls.filter(([path]) => path === '/requests/request-1')).toHaveLength(1)
  })
  it('does not request or display Owner queues for a Customer', () => {
    mount(false, true)
    expect(screen.queryByText('Simulation processing queue')).not.toBeInTheDocument()
    expect(api).not.toHaveBeenCalled()
  })
})
