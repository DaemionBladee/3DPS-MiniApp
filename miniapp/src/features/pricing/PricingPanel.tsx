import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { ErrorState, LoadingState } from '../../components/ui/States'
import { apiRequest } from '../../lib/api/client'
import type { components } from '../../lib/api/schema'
import { useAuth } from '../auth/context'

type CustomerEstimate = components['schemas']['CustomerEstimate']
type OwnerEstimate = components['schemas']['OwnerEstimate']
type Evaluation = components['schemas']['EvaluatePrice']
type Basis = components['schemas']['DesignPricingBasis']
type Pending = { body: Evaluation; key: string }

export function PricingPanel({ requestId, version, owner = false, design = false, scopeId }: {
  requestId: string; version: number; owner?: boolean; design?: boolean; scopeId?: string | undefined
}) {
  const { session } = useAuth()
  const privateView = owner && session?.user.role === 'owner'
  const [hours, setHours] = useState(''), [revisionHours, setRevisionHours] = useState('')
  const [complexity, setComplexity] = useState<Basis['complexity']>('standard')
  const [rights, setRights] = useState<Basis['usage_rights']>('personal')
  const [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null)
  const pending = useRef<Pending | null>(null)
  const path = `/${privateView ? 'owner/' : ''}requests/${requestId}/estimates` as const
  const query = useQuery({ queryKey: ['pricing', session?.user.id, privateView, requestId, version], enabled: !!session,
    queryFn: ({ signal }) => apiRequest<{ estimate: CustomerEstimate | OwnerEstimate | null }>(path, { signal }),
    // Policies, native results and availability can change independently of the page's request version.
    refetchInterval: 5000, staleTime: 0,
  })
  const calculate = async () => {
    if (!session || busy) return
    setBusy(true); setError(null)
    try {
      if (!pending.current) {
        const current = await apiRequest<components['schemas']['RequestResponse']>(`/requests/${requestId}`)
        pending.current = { key: crypto.randomUUID(), body: { expected_version: current.version,
          ...(design && scopeId ? { design_basis: { scope_id: scopeId, estimated_hours: hours, hours_per_revision: revisionHours, complexity, usage_rights: rights } } : {}),
        } }
      }
      const command = pending.current
      await apiRequest(path, { method: 'POST', csrfToken: session.csrf_token, idempotencyKey: command.key, body: JSON.stringify(command.body) })
      pending.current = null
      await query.refetch()
    } catch { setError('Estimate could not be refreshed. Check configuration and request status. Retry sends the exact original command.') }
    finally { setBusy(false) }
  }
  const value = query.data?.estimate
  const privateValue = value && 'lines' in value ? value : null
  // Hide cached amounts during validation, after an error, and once their server deadline expires.
  const fresh = value?.current && !query.isFetching && !query.isError && Date.parse(value.expires_at) > Date.now()
  const canCalculate = !design || (privateView && !!scopeId && !!hours && !!revisionHours)
  return <Card className="pricing-panel"><h2>{design ? 'Design service test estimate' : 'Printing test estimate'}</h2>
    <p className="print-notice">NON-BINDING TEST ESTIMATE — hypothetical simulation costs, not a final quotation.</p>
    <p>No acceptance, payment or production is authorized. Design XTR and printing MMK amounts are separate and cannot be added.</p>
    {query.isPending && <LoadingState label="Checking current test estimate…" />}
    {query.isError && <ErrorState title="Test estimate unavailable" description="Check your session and connection." onRetry={() => { void query.refetch() }} />}
    {!query.isPending && !query.isError && !value && <p>No test estimate has been calculated.</p>}
    {value && <><p role="status">{fresh && value.priced && value.estimated_total != null ? `Estimated total: ${value.estimated_total} ${value.currency_code}` : 'Current price unavailable — review or refresh required.'}</p>
      <p>Estimate {value.number} · specification revision {value.request_revision} · policy {value.policy_version}</p>
      <p>{fresh && value.decision === 'pass' ? 'Simulation eligibility checks passed; live issuance remains disabled.' : 'Owner review required.'}</p>
      {value.stale_reasons.length > 0 && <p>Stale: {value.stale_reasons.join(', ').replaceAll('_', ' ')}</p>}
      <ul>{value.assumptions.map(reason => <li key={reason}>{reason.replaceAll('_', ' ')}</li>)}</ul>
    </>}
    {privateValue && <details><summary>Owner cost breakdown and eligibility</summary>
      <p>Historical calculated total: {privateValue.historical_total ?? 'Unknown'} {privateValue.currency_code}</p>
      <div className="pricing-table"><table><caption>Private cost components</caption><thead><tr><th>Component</th><th>Quantity</th><th>Rate</th><th>Amount</th></tr></thead><tbody>{privateValue.lines.map(line => <tr key={line.position}><td>{line.component_code}</td><td>{line.quantity ?? 'Unknown'}</td><td>{line.rate ?? 'Unknown'}</td><td>{line.amount ?? 'Unknown'}</td></tr>)}</tbody></table></div>
      <p>Missing costs: {privateValue.unknown_costs.join(', ') || 'None'}</p>
      <ul>{privateValue.eligibility_rules.map(rule => <li key={rule.code}>{rule.result}: {rule.code} — {rule.detail}</li>)}</ul>
      <p className="analysis-checksum">Policy SHA-256: {privateValue.policy_checksum}</p><p className="analysis-checksum">Sources SHA-256: {privateValue.source_sha256}</p>
      <details><summary>Exact policy and source snapshots</summary><pre className="pricing-snapshot">{JSON.stringify({ policy: privateValue.policy_snapshot, sources: privateValue.source_snapshot }, null, 2)}</pre></details>
    </details>}
    {design && privateView && <fieldset className="print-form" disabled={busy || !!pending.current}><legend>Owner scope pricing basis</legend>
      <p>Scope: {scopeId ?? 'Publish a scope proposal first'}. This calculation does not approve scope or release delivery rights.</p>
      <label htmlFor="design-pricing-hours">Estimated design hours</label><input id="design-pricing-hours" inputMode="decimal" value={hours} onChange={event => setHours(event.target.value)} />
      <label htmlFor="design-pricing-revisions">Hours per included revision</label><input id="design-pricing-revisions" inputMode="decimal" value={revisionHours} onChange={event => setRevisionHours(event.target.value)} />
      <label htmlFor="design-pricing-complexity">Scope complexity</label><select id="design-pricing-complexity" value={complexity} onChange={event => setComplexity(event.target.value as Basis['complexity'])}>{['simple','standard','complex'].map(v => <option key={v}>{v}</option>)}</select>
      <label htmlFor="design-pricing-rights">Usage rights basis</label><select id="design-pricing-rights" value={rights} onChange={event => setRights(event.target.value as Basis['usage_rights'])}>{['personal','commercial','exclusive'].map(v => <option key={v}>{v}</option>)}</select>
    </fieldset>}
    {error && <p role="alert">{error}</p>}
    {(!design || privateView) && <Button disabled={busy || !canCalculate} onClick={() => { void calculate() }}>{busy ? 'Calculating…' : pending.current ? 'Retry exact estimate command' : 'Calculate test estimate'}</Button>}
    {pending.current && <Button variant="secondary" disabled={busy} onClick={() => { pending.current = null; setError(null); void query.refetch() }}>Discard retry and reload estimate</Button>}
  </Card>
}
