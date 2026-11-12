import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Card } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { EmptyState, ErrorState, LoadingState } from '../../components/ui/States'
import { apiRequest } from '../../lib/api/client'
import type { components } from '../../lib/api/schema'
import { useAuth } from '../auth/context'

export function OwnerPrintingQueue() {
  const { session } = useAuth()
  const [opened, setOpened] = useState(false)
  const [offset, setOffset] = useState(0)
  const query = useQuery({ queryKey: ['submitted-printing', session?.user.id, offset], enabled: opened && session?.user.role === 'owner',
    queryFn: ({ signal }) => apiRequest<components['schemas']['RequestPage']>(`/owner/requests?stage_kind=printing&limit=20&offset=${offset}`, { signal }),
  })
  if (!session || session.user.role !== 'owner') return null
  return <Card className="submitted-printing-queue"><h2>Submitted printing requests</h2><p>Inspect private specifications and models. Open a submission to inspect its current analysis status.</p>{!opened ? <Button variant="secondary" onClick={() => setOpened(true)}>Load submitted printing requests</Button> : query.isPending ? <LoadingState label="Loading submitted requests…" /> : query.isError ? <ErrorState onRetry={() => { void query.refetch() }} /> : <>
    {query.data.items.length === 0 ? <EmptyState title="No submitted print requests" description="Validated customer submissions will appear here." /> : <ul className="request-list">{query.data.items.filter(row => !['draft', 'cancelled'].includes(row.status)).map(row => <li className="request-row" key={row.id}><p>Printing request · revision {row.revision} · {row.status.replaceAll('_', ' ')}</p><p>{row.customer_notes}</p><Link className="button button--secondary" to={`/owner/requests/${row.id}`}>Inspect printing request {row.id.slice(0, 8)}</Link></li>)}</ul>}
    <div className="request-pagination"><Button variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous submissions</Button><Button variant="ghost" disabled={query.data.next_offset === null} onClick={() => setOffset(query.data.next_offset ?? offset)}>Next submissions</Button></div>
  </>}</Card>
}
