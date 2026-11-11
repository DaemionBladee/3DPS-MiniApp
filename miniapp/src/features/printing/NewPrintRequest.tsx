import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { ErrorState } from '../../components/ui/States'
import { apiRequest } from '../../lib/api/client'
import type { components } from '../../lib/api/schema'
import { useAuth } from '../auth/context'

export function NewPrintRequest() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [notes, setNotes] = useState('')
  const key = useRef<string | null>(null)
  const create = useMutation({ mutationFn: () => {
    if (!session) throw new Error('Authentication required')
    key.current ??= crypto.randomUUID()
    return apiRequest<components['schemas']['ProjectRequestResponse']>('/requests', { method: 'POST', csrfToken: session.csrf_token, idempotencyKey: key.current, body: JSON.stringify({ service_type: 'printing', customer_notes: notes }) })
  }, onSuccess: data => { void queryClient.invalidateQueries({ queryKey: ['requests', session?.user.id] }); void navigate(`/app/requests/${data.request.id}`) } })
  if (!session) return <ErrorState title="Sign in to create a printing draft" description="The development UI preview cannot create authenticated requests." />
  const submit = (event: FormEvent) => { event.preventDefault(); create.mutate() }
  return <div className="dashboard printing-page"><Link to="/app">← Your workspace</Link><h1>Start a printing request</h1><Link className="button button--secondary" to="/app/requests/design">Need custom design or design + printing?</Link><Card><p>Save a private simulation draft, then upload models and choose printing settings. No quotation, payment or production is available.</p><form className="print-form" onSubmit={submit}><label htmlFor="print-start-notes">Project notes (optional)</label><textarea id="print-start-notes" maxLength={2000} value={notes} disabled={create.isPending || create.isError} onChange={event => setNotes(event.target.value)} /><Button type="submit" disabled={create.isPending}>{create.isPending ? 'Creating draft…' : create.isError ? 'Retry creating draft' : 'Create printing draft'}</Button></form>{create.isError && <p role="alert">The creation response was unavailable. Retry with the same command, or return to your saved requests after a reload.</p>}</Card></div>
}
