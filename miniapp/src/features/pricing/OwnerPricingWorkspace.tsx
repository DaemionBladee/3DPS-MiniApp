import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { apiRequest } from '../../lib/api/client'
import type { components } from '../../lib/api/schema'
import { useAuth } from '../auth/context'

type Configuration = components['schemas']['PricingConfiguration']
type Policy = components['schemas']['PublishPolicy']
type Fixture = components['schemas']['PublishAvailability']
type Command = { path: '/owner/pricing/policies' | '/owner/pricing/availability-fixtures'; body: Policy | Fixture; key: string }

export function OwnerPricingWorkspace() {
  const { session } = useAuth()
  const [open, setOpen] = useState(false), [stage, setStage] = useState<'printing' | 'design'>('printing')
  const [policy, setPolicy] = useState(''), [fixture, setFixture] = useState(''), [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false), [message, setMessage] = useState<string | null>(null)
  const pending = useRef<Command | null>(null)
  const query = useQuery({ queryKey: ['pricing-configuration', session?.user.id], enabled: open && session?.user.role === 'owner',
    queryFn: ({ signal }) => apiRequest<Configuration>('/owner/pricing/configuration', { signal }), staleTime: 0,
  })
  if (session?.user.role !== 'owner') return null
  const load = async () => {
    setBusy(true); setMessage(null)
    try {
      const template = await apiRequest<components['schemas']['PricingPolicyDefinition-Output']>(`/owner/pricing/hypothetical-policy?stage_kind=${stage}`)
      setPolicy(JSON.stringify(template, null, 2))
    } catch { setMessage('Hypothetical template unavailable.') } finally { setBusy(false) }
  }
  const publish = async (kind: 'policy' | 'fixture') => {
    setBusy(true); setMessage(null)
    try {
      if (!pending.current) {
        const configuration = await query.refetch()
        if (!configuration.data || configuration.isError) throw new Error('Configuration unavailable')
        const data = configuration.data
        const command: Command = kind === 'policy'
          ? { path: '/owner/pricing/policies', key: crypto.randomUUID(), body: {
            expected_version: Math.max(0, ...data.policies.filter(p => p.stage_kind === stage).map(p => p.version)),
            configuration: JSON.parse(policy) as Policy['configuration'], reason,
          } }
          : { path: '/owner/pricing/availability-fixtures', key: crypto.randomUUID(), body: {
            expected_version: data.availability?.version ?? 0,
            configuration: JSON.parse(fixture) as Fixture['configuration'], reason,
          } }
        pending.current = command
      }
      const command = pending.current
      await apiRequest(command.path, { method: 'POST', csrfToken: session.csrf_token, idempotencyKey: command.key, body: JSON.stringify(command.body) })
      pending.current = null; setMessage('Simulation configuration version published privately. Existing estimates must be refreshed.')
      await query.refetch()
    } catch { setMessage('Configuration was not confirmed. Validate JSON, decimal strings and reason. Retry preserves the exact command; reload to resolve a version conflict.') }
    finally { setBusy(false) }
  }
  const blocked = busy || !!pending.current
  return <Card><h2>Simulation pricing configuration</h2><p>No commercial rates, live stock or production capacity are configured by default. These fixtures cannot authorize checkout or reserve resources.</p>
    {!open ? <Button onClick={() => setOpen(true)}>Load pricing workspace</Button> : <>
      {query.isPending && <p role="status">Loading private policies…</p>}
      {query.isError && <p role="alert">Configuration unavailable. <Button onClick={() => { void query.refetch() }}>Retry configuration</Button></p>}
      {query.data && <><ul>{query.data.policies.map(p => <li key={p.id}>{p.stage_kind} · version {p.version} · {p.currency_code} · {p.active ? 'active simulation' : 'historical'}</li>)}</ul>
        <p>Availability fixture: {query.data.availability ? `version ${query.data.availability.version}, expires ${query.data.availability.expires_at}` : 'Unknown; manual review required'}</p></>}
      <fieldset className="print-form" disabled={blocked}><legend>Versioned policy</legend>
        <label htmlFor="pricing-stage">Pricing stage</label><select id="pricing-stage" value={stage} onChange={event => { setStage(event.target.value as typeof stage); setPolicy('') }}><option value="printing">Physical printing · MMK</option><option value="design">Digital design simulation · XTR</option></select>
        <Button variant="secondary" onClick={() => { void load() }}>Load hypothetical policy template</Button>
        <p>Template amounts are invented test values. All decimal amounts and fractions must be JSON strings. Use null for unknown costs; a zero requires an explicit zero_cost_reasons entry. Eligibility thresholds must be deliberately configured.</p>
        <label htmlFor="pricing-policy-json">Simulation policy JSON</label><textarea id="pricing-policy-json" className="pricing-json" spellCheck={false} value={policy} onChange={event => setPolicy(event.target.value)} />
        <label htmlFor="pricing-fixture-json">Simulation stock and capacity JSON</label><textarea id="pricing-fixture-json" className="pricing-json" spellCheck={false} placeholder={'{"simulation_only":true,"ttl_seconds":3600,"stock":[],"capacity":[]}'} value={fixture} onChange={event => setFixture(event.target.value)} />
        <p>Stock entries: material_key, color_key, available_g (decimal string or null). Capacity entries: exact approved profile_id, available_seconds (integer or null). Empty entries mean unknown.</p>
        <label htmlFor="pricing-reason">Configuration review reason</label><textarea id="pricing-reason" minLength={8} maxLength={500} value={reason} onChange={event => setReason(event.target.value)} />
      </fieldset>
      {message && <p role="status">{message}</p>}
      {pending.current ? <div className="print-actions"><Button disabled={busy} onClick={() => { void publish('policy') }}>Retry exact configuration command</Button><Button disabled={busy} variant="secondary" onClick={() => { pending.current = null; setMessage(null); void query.refetch() }}>Discard retry and reload configuration</Button></div> : <div className="print-actions"><Button disabled={busy || !policy || reason.trim().length < 8 || !query.data} onClick={() => { void publish('policy') }}>Publish simulation policy version</Button><Button disabled={busy || !fixture || reason.trim().length < 8 || !query.data} onClick={() => { void publish('fixture') }}>Publish simulation availability version</Button></div>}
    </>}
  </Card>
}
