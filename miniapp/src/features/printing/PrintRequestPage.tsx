import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { EmptyState, ErrorState, LoadingState } from '../../components/ui/States'
import { apiDownload } from '../../lib/api/client'
import { PricingPanel } from '../pricing/PricingPanel'
import { AnalysisPanel } from '../analysis/AnalysisPanel'
import { useAuth } from '../auth/context'
import { DownloadButton, FilePicker, ItemEditor, PreferencesEditor } from './PrintForms'
import { usePrintIntake } from './usePrintIntake'
import type { IntakeDetail, ItemDetail, PrintingOptions } from './types'

function ItemSummary({ item, catalog, download }: { item: ItemDetail; catalog: PrintingOptions; download: () => void }) {
  const spec = item.specification
  const labels = [...catalog.materials, ...catalog.colors, ...catalog.qualities, ...catalog.units]
  const label = (key: string | null | undefined) => labels.find(option => option.key === key)?.label ?? 'Not selected'
  return <div className="print-summary">
    <dl><div><dt>Quantity</dt><dd>{spec.quantity}</dd></div><div><dt>Material</dt><dd>{label(spec.material_key)}</dd></div><div><dt>Color</dt><dd>{label(spec.color_key)}</dd></div><div><dt>Quality</dt><dd>{label(spec.quality_key)}</dd></div><div><dt>Units</dt><dd>{label(spec.unit_key)} · {spec.unit_confirmed ? 'Confirmed' : 'Not confirmed'}</dd></div></dl>
    <p>Required by: {spec.required_by || 'Not specified'} · requirements {spec.requirements_confirmed ? 'confirmed' : 'unconfirmed'}</p>
    <p>Safety-critical use: {spec.safety_critical == null ? 'Needs discussion' : spec.safety_critical ? 'Yes' : 'No'} · unusual tolerance: {spec.unusual_tolerance == null ? 'Needs discussion' : spec.unusual_tolerance ? 'Yes' : 'No'}</p>
    {spec.description && <p>{spec.description}</p>}
    {spec.special_requirements && <div className="print-special"><Badge tone="accent">Special requirements</Badge><p>{spec.special_requirements}</p></div>}
    {['not-sure'].some(value => [spec.material_key, spec.color_key, spec.quality_key].includes(value as 'not-sure')) && <p>Owner review required for uncertain settings.</p>}
    {item.model_file?.validation_status === 'validated' && item.model_file.storage_state === 'ready' && item.model_file.download_allowed !== false && <DownloadButton download={download} />}
  </div>
}

function SavedSummary({ data, catalog }: { data: IntakeDetail; catalog: PrintingOptions }) {
  return <Card><h2>Request summary</h2><p>{data.request.customer_notes || 'No project notes.'}</p>
    <p>Handoff preference: {data.request.fulfillment_method === 'pickup' ? 'Pickup' : 'Delivery'}</p><p>{data.request.fulfillment_notes}</p>
    <p className="request-meta">Revision {data.request.revision} · {data.items.length} model{data.items.length === 1 ? '' : 's'} · Simulation</p>
    <p className="print-notice">Development options do not represent commercial stock or printer capability. No quotation or payment is available.</p>
    {data.items.some(item => !item.model_file || !item.specification.material_key || !item.specification.color_key || !item.specification.quality_key || !item.specification.unit_confirmed) && <p role="alert">Complete every model upload and printing setting before submitting.</p>}
    {data.items.length === 0 && <EmptyState title="No print models yet" description="Add at least one model to complete this printing request." />}
    {/* Individual summaries remain next to each model card in every step. */}
    <span className="sr-only">{catalog.catalog_version}</span>
  </Card>
}

export function PrintRequestPage({ owner = false }: { owner?: boolean }) {
  const { requestId = '' } = useParams()
  const { session } = useAuth()
  const intake = usePrintIntake(requestId)
  const [step, setStep] = useState(0)
  const [dirty, setDirty] = useState<Record<string, boolean>>({})
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const markDirty = useCallback((key: string, value: boolean) => setDirty(previous => previous[key] === value ? previous : { ...previous, [key]: value }), [])
  const hasDirty = Object.values(dirty).some(Boolean)
  if (!session) return <ErrorState title="Sign in to manage printing requests" description="The isolated UI preview has no authenticated draft records." />
  if (intake.query.isPending || intake.catalog.isPending) return <LoadingState label="Loading saved printing request…" />
  if (intake.query.isError || intake.catalog.isError || !intake.query.data || !intake.catalog.data) return <ErrorState title="Printing request unavailable" description="Check your connection and resource access." onRetry={() => { void intake.query.refetch(); void intake.catalog.refetch() }} />
  const data = intake.query.data
  const catalog = intake.catalog.data
  const draft = data.request.status === 'draft'
  const editable = draft && !owner && data.request.customer_id === session.user.id
  const disabled = !editable || intake.busy || intake.locked
  const complete = data.items.length > 0 && data.items.every(item => item.model_file?.validation_status === 'validated' && item.model_file.storage_state === 'ready' && item.specification.material_key && item.specification.color_key && item.specification.quality_key && item.specification.unit_confirmed)
  const download = (item: ItemDetail) => {
    const file = item.model_file
    if (file) void apiDownload(`/files/${file.id}/download`, file.original_name).catch(() => setDownloadError('The private model could not be downloaded. Check your session and try again.'))
  }
  return <div className="dashboard printing-page">
    <Link to={owner ? '/owner' : '/app'} className="print-back">← {owner ? 'Owner workspace' : 'Your projects'}</Link>
    <section className="welcome-row"><div><p className="eyebrow">PRIVATE PRINTING REQUEST</p><h1>{['submitted', 'analyzing', 'manual_review'].includes(data.request.status) ? 'Printing request submitted' : data.request.status === 'cancelled' ? 'Cancelled printing request' : 'Your printing draft'}</h1><p className="page-description">{owner ? `Customer: ${data.customer_display_name}` : 'Your files and settings are saved privately to this request.'}</p></div><Badge tone="accent">Simulation only</Badge></section>
    {['submitted', 'analyzing', 'manual_review'].includes(data.request.status) && <AnalysisPanel requestId={requestId} version={data.request.version} owner={owner} refresh={intake.reload} />}
    {['submitted', 'analyzing', 'manual_review'].includes(data.request.status) && <PricingPanel key={requestId} requestId={requestId} version={data.request.version} owner={owner} />}
    {editable && <nav aria-label="Printing intake steps" className="print-steps">{['Models', 'Specifications', 'Fulfillment', 'Review'].map((name, index) => <Button key={name} variant={step === index ? 'primary' : 'secondary'} aria-current={step === index ? 'step' : undefined} disabled={intake.busy || hasDirty || intake.locked} onClick={() => setStep(index)}>{index + 1}. {name}</Button>)}</nav>}
    <Card className="print-notice"><p>{catalog.notice}</p><p>STL, Core 3MF and OBJ · up to {Math.floor(catalog.max_file_bytes / 1024 / 1024)} MiB each · {catalog.max_request_files} models per request.</p><p>OBJ material/texture references and unsupported 3MF extensions must be removed before upload.</p></Card>
    {intake.error && <Card role="alert"><h2>{intake.error.status === 409 ? 'Draft changed or upload conflicted' : 'Draft could not be saved'}</h2><p>{intake.error.message}</p><div className="print-actions"><Button onClick={intake.retry}>Retry saved change</Button><Button variant="secondary" onClick={() => { void intake.reload().then(() => setDirty({})).catch(() => undefined) }}>Reload saved draft</Button></div></Card>}
    {downloadError && <p role="alert">{downloadError}</p>}
    {editable && step === 0 && <Card><h2>1. Model upload</h2><p>Choose one model for each print item. Uploads remain private.</p><FilePicker disabled={disabled || hasDirty || data.items.length >= catalog.max_request_files} onFiles={files => { void intake.addFiles(files).catch(() => undefined) }} /></Card>}
    {intake.uploadProgress && <Card role="status"><p>Uploading {intake.uploadProgress.name}</p><progress max={100} value={intake.uploadProgress.percent} aria-label="Model upload progress" /><p>{intake.uploadProgress.percent}% transferred — structural validation follows.</p><Button variant="secondary" onClick={intake.cancelUpload}>Cancel upload</Button></Card>}
    {intake.failedUploads.map(upload => <Card key={upload.itemId} role="alert"><p>{upload.file.name}: {upload.message}</p><Button disabled={intake.busy} onClick={() => intake.retryUpload(upload)}>Retry upload</Button></Card>)}
    {data.items.map((item, index) => <Card className="print-item" key={`${item.id}-${intake.resetEpoch}`} aria-label={`Print item ${index + 1}`}>
      <div className="section-heading"><h2>{item.model_file?.original_name ?? `Model ${index + 1} — upload incomplete`}</h2><Badge>{item.model_file?.validation_status === 'validated' ? 'Format checked' : 'Upload required'}</Badge></div>
      {item.model_file && <p className="request-meta">{item.model_file.format?.toUpperCase()} · {item.model_file.size_bytes.toLocaleString()} bytes · uploaded at revision {item.model_file.request_revision}</p>}
      {typeof item.model_file?.format_details['declared_unit'] === 'string' && <p className="request-meta">File-declared units: {String(item.model_file.format_details['declared_unit'])}</p>}
      {!item.model_file && editable && <FilePicker multiple={false} label="Choose a model for this item" disabled={disabled || hasDirty} onFiles={files => { if (files[0]) void intake.uploadForItem(item.id, files[0]).catch(() => undefined) }} />}
      {editable && step === 1 ? <ItemEditor item={item} catalog={catalog} disabled={disabled} paused={!!intake.error} save={intake.saveItem} markDirty={markDirty} clearError={intake.clearValidationError} /> : <ItemSummary item={item} catalog={catalog} download={() => download(item)} />}
      {editable && step === 0 && <Button variant="ghost" disabled={disabled || hasDirty} onClick={() => { void intake.removeItem(item.id).catch(() => undefined) }}>Remove model item</Button>}
    </Card>)}
    {editable && step === 2 && <Card><h2>3. Fulfillment preferences</h2><PreferencesEditor key={intake.resetEpoch} notes={data.request.customer_notes} method={data.request.fulfillment_method} fulfillmentNotes={data.request.fulfillment_notes} disabled={disabled} paused={!!intake.error} save={intake.savePreferences} markDirty={markDirty} clearError={intake.clearValidationError} /></Card>}
    {(!editable || step === 3) && <SavedSummary data={data} catalog={catalog} />}
    {editable && <div className="print-bottom-bar"><p role="status">{intake.busy ? 'Saving securely…' : hasDirty ? 'Waiting for draft autosave…' : 'All displayed changes saved'}</p>{step < 3 ? <Button disabled={disabled || hasDirty} onClick={() => setStep(previous => previous + 1)}>Continue</Button> : <Button disabled={disabled || hasDirty || !complete || !!intake.error} onClick={() => { void intake.submit().catch(() => undefined) }}>Submit printing request</Button>}</div>}
  </div>
}
