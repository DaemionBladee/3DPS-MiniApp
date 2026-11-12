import { useQuery } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { EmptyState, ErrorState, LoadingState } from '../../components/ui/States'
import { apiRequest } from '../../lib/api/client'
import type { components } from '../../lib/api/schema'
import { useAuth } from '../auth/context'
import { TaskRetry } from './TaskRetry'

type Status = components['schemas']['AnalysisStatus']
type Results = components['schemas']['AnalysisResults']
const labels: Record<Status['state'], string> = {
  not_submitted: 'Not submitted', pending: 'Pending analysis', processing: 'Processing',
  completed: 'Analysis completed', manual_review: 'Manual review required',
  needs_clarification: 'Needs clarification', failed: 'Analysis failed', superseded: 'Analysis superseded',
}

export function AnalysisPanel({ requestId, version, owner = false, refresh }: {
  requestId: string; version: number; owner?: boolean; refresh: () => Promise<unknown>
}) {
  const { session } = useAuth()
  const status = useQuery({ queryKey: ['analysis-status', session?.user.id, requestId], enabled: !!session,
    queryFn: ({ signal }) => apiRequest<Status>(`/requests/${requestId}/analysis`, { signal }),
    refetchInterval: query => ['pending', 'processing'].includes(query.state.data?.state ?? '') ? 4000 : false,
  })
  const result = useQuery({ queryKey: ['analysis-results', session?.user.id, requestId, status.dataUpdatedAt],
    enabled: !!session && !!status.data,
    queryFn: ({ signal }) => apiRequest<Results>(`/requests/${requestId}/analysis/results`, { signal }),
  })
  const reload = async () => { await Promise.all([status.refetch(), result.refetch(), refresh()]) }
  if (status.isPending) return <LoadingState label="Loading private analysis status…" />
  if (status.isError || result.isError) return <ErrorState title="Analysis unavailable" description="Check your session and try again." onRetry={() => { void reload() }} />
  const state = status.data.state
  return <Card className="analysis-panel"><h2>{labels[state]}</h2>
    <p className="print-notice">Simulation estimate — not a final quotation.</p>
    {state === 'pending' && <p>Your submitted revision is saved. Analysis is not running yet; no slicing result or quotation is available.</p>}
    {state === 'processing' && <p>A private model is being processed in an isolated virtual slicer.</p>}
    {state === 'needs_clarification' && <p>Confirm the model’s intended scale and dimensions with the Owner. The submitted specification remains frozen.</p>}
    {['manual_review', 'failed'].includes(state) && <p>The Owner must review this request. No quote or production is authorized.</p>}
    {status.data.tasks.map(task => <div key={task.id} className="print-summary"><p>Model analysis: {task.state} · attempt {task.attempts ?? 0}</p>{task.error_code && <p role="status">Reason: {task.error_code.replaceAll('_', ' ')}</p>}
      {owner && session?.user.role === 'owner' && ['failed', 'succeeded'].includes(task.state) && <TaskRetry taskId={task.id} requestId={requestId} refresh={reload} />}
    </div>)}
    {result.data?.items.map(item => <section key={item.id} aria-label="Model simulation result" className="print-summary">
      <h3>{item.outcome === 'estimated' ? 'Virtual slicing estimate' : 'Model requires review'}</h3>
      <dl><div><dt>Calculated dimensions (mm)</dt><dd>{['x', 'y', 'z'].map(axis => item.geometry.dimensions_mm[axis as 'x' | 'y' | 'z'].toFixed(2)).join(' × ')}</dd></div>
        <div><dt>Customer scale</dt><dd>{item.submitted_specification.unit_key} · {item.submitted_specification.dimension_x_mm != null ? `${item.submitted_specification.dimension_x_mm} × ${item.submitted_specification.dimension_y_mm} × ${item.submitted_specification.dimension_z_mm} mm` : 'Confirmed units; no target dimensions supplied'}</dd></div>
        <div><dt>Mesh volume</dt><dd>{item.geometry.volume_mm3 == null ? 'Uncertain' : `${item.geometry.volume_mm3.toFixed(2)} mm³`}</dd></div>
        <div><dt>Topology</dt><dd>{item.geometry.watertight ? 'Watertight' : 'Review required'} · {item.geometry.component_count} component(s)</dd></div>
        <div><dt>Build volume</dt><dd>{item.geometry.build_volume_compatible ? 'Fits virtual profile' : 'Incompatible'}</dd></div>
        <div><dt>Profile</dt><dd>{item.profile.key} · v{item.profile.version} · PrusaSlicer {item.engine_version}</dd></div>
      </dl>
      {item.estimate && <><p>Per model: {item.estimate.filament_g.toFixed(2)} g · {Math.ceil(item.estimate.print_seconds / 60)} min ({item.estimate.print_seconds} seconds).</p><p>Requested quantity: {item.quantity}. Batch packing and total production time have not been estimated.</p><p>Support material estimate unavailable. This profile has supports disabled.</p></>}
      {item.special_requirements && <p className="print-special">Special requirements need Owner review.</p>}
      {item.geometry.review_reasons.length > 0 && <p>Review: {item.geometry.review_reasons.map(value => value.replaceAll('_', ' ')).join('; ')}.</p>}
      <p>Warnings: {item.geometry.warnings.map(value => value.replaceAll('_', ' ')).join('; ')}.</p>
      <details><summary>Revision and profile provenance</summary><p>Request revision {item.request_revision} · result {item.id}</p><p className="analysis-checksum">Input SHA-256: {item.input_sha256}</p><p className="analysis-checksum">Profile SHA-256: {item.profile.config_sha256}</p></details>
    </section>)}
    {result.data?.items.length === 0 && ['completed', 'superseded'].includes(state) && <EmptyState title="No current result" description="Only results matching the current revision are displayed." />}
    <Button variant="secondary" onClick={() => { void reload() }}>Refresh analysis</Button><span className="sr-only">Request version {version}</span>
  </Card>
}
