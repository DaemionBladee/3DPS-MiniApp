import { Link } from 'react-router-dom'
import { useRef, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { Badge } from '../../components/ui/Badge'
import { EmptyState, ErrorState, LoadingState } from '../../components/ui/States'
import { ApiError, apiRequest } from '../../lib/api/client'
import type { components } from '../../lib/api/schema'
import { useAuth } from '../auth/context'

type Request = components['schemas']['RequestResponse']
type Command = {
  path: `/requests${string}`
  method: 'POST' | 'PATCH'
  body: components['schemas']['CreateRequest'] | components['schemas']['DraftPatch'] | components['schemas']['RequestTransition']
}
const serviceLabels = { printing: '3D printing', custom_design: 'Custom design', design_and_print: 'Design + print' } as const

function DraftRow({ row, canEdit, busy, run }: { row: Request; canEdit: boolean; busy: boolean; run: (command: Command) => void }) {
  const [notes, setNotes] = useState(row.customer_notes)
  const [reason, setReason] = useState('')
  return <li className="request-row">
    <div className="section-heading"><h3>{serviceLabels[row.service_type]}</h3><Badge>{{ draft: 'Draft', submitted: row.stage_kind === 'printing' ? 'Submitted — pending analysis' : 'Submitted design brief', analyzing: 'Analyzing', manual_review: 'Manual review', cancelled: 'Cancelled' }[row.status]}</Badge></div>
    <p className="request-meta">{row.stage_kind === 'design' ? 'Design stage' : 'Printing stage'} · Revision {row.revision} · Simulation</p>
    {canEdit && row.status === 'draft' ? <form onSubmit={event => { event.preventDefault(); run({ path: `/requests/${row.id}`, method: 'PATCH', body: { expected_version: row.version, customer_notes: notes } }) }}>
      <label htmlFor={`notes-${row.id}`}>Draft notes</label><textarea id={`notes-${row.id}`} maxLength={2000} value={notes} onChange={event => setNotes(event.target.value)} disabled={busy} />
      <Button type="submit" variant="secondary" disabled={busy || notes === row.customer_notes}>Save changes</Button>
    </form> : <p className="request-notes">{row.customer_notes || 'No notes yet.'}</p>}
    {row.stage_kind === 'printing' && <Link className="button button--secondary" to={`${canEdit ? '/app' : '/owner'}/requests/${row.id}`}>{row.status === 'draft' ? 'Open printing wizard' : 'View submitted printing request'}</Link>}
    {row.stage_kind === 'design' && <Link className="button button--secondary" to={`${canEdit ? '/app' : '/owner'}/design-requests/${row.id}`}>Open design brief</Link>}
    {row.status === 'draft' && <form className="request-cancel" onSubmit={event => { event.preventDefault(); run({ path: `/requests/${row.id}/transitions`, method: 'POST', body: { expected_version: row.version, target: 'cancelled', reason } }) }}>
      <label htmlFor={`reason-${row.id}`}>Cancellation reason</label><input id={`reason-${row.id}`} minLength={3} maxLength={500} required value={reason} onChange={event => setReason(event.target.value)} disabled={busy} />
      <Button type="submit" variant="ghost" disabled={busy || reason.trim().length < 3}>Cancel draft</Button>
    </form>}
  </li>
}

/** Only authenticated server records; the isolated mock preview never mounts this. */
export function RequestWorkspace({ owner = false }: { owner?: boolean }) {
  const { session } = useAuth()
  const queryClient = useQueryClient()
  const [opened, setOpened] = useState(false)
  const [offset, setOffset] = useState(0)
  const [kind, setKind] = useState<components['schemas']['CreateRequest']['service_type']>('printing')
  const [notes, setNotes] = useState('')
  const commandKeys = useRef(new Map<string, string>())
  const queryKey = ['requests', session?.user.id, owner, offset] as const
  const query = useQuery({ queryKey, enabled: opened && !!session,
    queryFn: ({ signal }) => apiRequest<components['schemas']['RequestPage']>(`${owner ? '/owner/requests' : '/requests'}?limit=20&offset=${offset}`, { signal }),
  })
  const mutation = useMutation({
    mutationFn: (command: Command) => {
      if (!session) throw new ApiError('Sign in before changing a draft.', 401, 'authentication_required')
      const signature = JSON.stringify(command)
      // Keep an ambiguous/failed command's key in memory for exact retries.
      let key = commandKeys.current.get(signature)
      if (!key) { key = crypto.randomUUID(); commandKeys.current.set(signature, key) }
      return apiRequest(command.path, { method: command.method, body: JSON.stringify(command.body), csrfToken: session.csrf_token, idempotencyKey: key })
    },
    onSuccess: (_result, command) => {
      commandKeys.current.delete(JSON.stringify(command))
      if (command.path === '/requests') setNotes('')
      void queryClient.invalidateQueries({ queryKey: ['requests', session?.user.id] })
    },
  })
  if (!session) return null
  const ambiguous = mutation.isError && mutation.error instanceof ApiError && (mutation.error.status === 0 || mutation.error.status >= 500 || mutation.error.code === 'invalid_response')
  const busy = mutation.isPending || ambiguous
  const submit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate({ path: '/requests', method: 'POST', body: { service_type: kind, customer_notes: notes } })
  }
  return <div className="request-workspace">
    <p>Simulation requests only. Printing drafts can be completed in the private printing wizard.</p>
    {!opened ? <Button variant="secondary" onClick={() => setOpened(true)}>{owner ? 'Load customer drafts' : 'Open project drafts'}</Button> : <>
      {!owner && <form className="request-create" onSubmit={submit} aria-label="New simulation draft">
        <label htmlFor="request-kind">Service</label><select id="request-kind" value={kind} onChange={event => setKind(event.target.value as typeof kind)} disabled={busy}>
          {Object.entries(serviceLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <label htmlFor="new-request-notes">Project notes (optional)</label><textarea id="new-request-notes" maxLength={2000} value={notes} onChange={event => setNotes(event.target.value)} disabled={busy} />
        <Button type="submit" disabled={busy}>Save simulation draft</Button>
      </form>}
      {mutation.isPending && <p role="status">Saving draft…</p>}
      {mutation.isError && <div role="alert"><p>{mutation.error instanceof ApiError ? mutation.error.message : 'The change failed. Try again.'}</p>
        {mutation.variables && <Button variant="secondary" onClick={() => mutation.mutate(mutation.variables)}>Retry change</Button>}
        <Button variant="ghost" onClick={() => { void query.refetch() }}>Refresh requests</Button>
      </div>}
      {query.isPending ? <LoadingState label="Loading requests…" /> : query.isError ? <ErrorState title="Requests unavailable" onRetry={() => { void query.refetch() }} /> : <>
        {query.data.items.length ? <ul className="request-list">{query.data.items.map(row => <DraftRow key={`${row.id}-${row.version}`} row={row} canEdit={row.customer_id === session.user.id} busy={busy} run={command => mutation.mutate(command)} />)}</ul> : <EmptyState title="No drafts here yet" description={owner ? 'Customer drafts will appear here.' : 'Save a simulation draft to start your project.'} />}
        <div className="request-pagination"><Button variant="ghost" disabled={offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous page</Button><Button variant="ghost" disabled={query.data.next_offset === null || busy} onClick={() => setOffset(query.data.next_offset ?? offset)}>Next page</Button></div>
      </>}
    </>}
  </div>
}
