import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Card } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { ErrorState } from '../../components/ui/States'
import { apiRequest } from '../../lib/api/client'
import { useAuth } from '../auth/context'
import type { components } from '../../lib/api/schema'
import type { DesignDetail } from './types'

export function NewDesignRequest() {
  const { session } = useAuth(), navigate = useNavigate()
  const [kind, setKind] = useState<'custom_design' | 'design_and_print'>('custom_design')
  const key = useRef<string | null>(null)
  const create = useMutation({ mutationFn: async () => {
    if (!session) throw new Error('Sign in first')
    key.current ??= crypto.randomUUID()
    const result = await apiRequest<components['schemas']['ProjectRequestResponse']>('/requests', { method: 'POST', csrfToken: session.csrf_token, idempotencyKey: key.current, body: JSON.stringify({ service_type: kind }) })
    return apiRequest<DesignDetail>(`/requests/${result.request.id}/design`)
  }, onSuccess: data => { void navigate(`/app/design-projects/${data.id}`) } })
  if (!session) return <ErrorState title="Sign in to create a design brief" description="UI preview cannot create authenticated projects." />
  return <div className="dashboard printing-page"><Link to="/app">← Your workspace</Link><h1>Start a design request</h1><Card><p>Describe an idea without needing an STL, a printer or filament. This workflow is simulation only.</p><form className="print-form" onSubmit={event => { event.preventDefault(); create.mutate() }}><label htmlFor="design-service">Design service</label><select id="design-service" value={kind} disabled={create.isPending || create.isError} onChange={event => setKind(event.target.value as typeof kind)}><option value="custom_design">Custom design — digital files</option><option value="design_and_print">Design + printing — separate stages</option></select><Button type="submit" disabled={create.isPending}>{create.isPending ? 'Creating…' : create.isError ? 'Retry design draft creation' : 'Create design draft'}</Button></form>{create.isError && <p role="alert">Creation could not be confirmed. Retry with the same command, or reload and inspect saved projects before creating another.</p>}</Card></div>
}
