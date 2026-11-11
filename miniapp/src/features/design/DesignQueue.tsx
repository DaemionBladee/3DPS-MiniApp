import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { EmptyState, ErrorState, LoadingState } from '../../components/ui/States'
import { apiRequest } from '../../lib/api/client'
import { useAuth } from '../auth/context'
import type { components } from '../../lib/api/schema'

export function DesignQueue({ owner = false }: { owner?: boolean }) {
  const { session } = useAuth(), [opened, setOpened] = useState(false), [offset, setOffset] = useState(0)
  const query = useQuery({ queryKey: ['design-projects', session?.user.id, offset], enabled: opened && !!session, queryFn: ({ signal }) => apiRequest<components['schemas']['DesignPage']>(`/design-projects?limit=20&offset=${offset}`, { signal }) })
  if (!session) return null
  return <Card className="submitted-printing-queue"><h2>{owner ? 'Design review workspace' : 'Your design projects'}</h2><p>Private briefs, scope proposals and exact-version proofs. Simulation only.</p>{!opened ? <Button variant="secondary" onClick={() => setOpened(true)}>{owner ? 'Load design reviews' : 'Load design projects'}</Button> : query.isPending ? <LoadingState label="Loading design projects…" /> : query.isError ? <ErrorState onRetry={() => { void query.refetch() }} /> : <>{query.data.items.length ? <ul className="request-list">{query.data.items.map(data => <li className="request-row" key={data.id}><h3>{data.brief.description || 'Untitled design draft'}</h3><p>{data.state.replaceAll('_', ' ')} · {data.request.service_type === 'design_and_print' ? 'Design + printing' : 'Design only'}</p><Link className="button button--secondary" to={owner ? `/owner/designs/${data.id}` : `/app/design-projects/${data.id}`}>Open design {data.id.slice(0,8)}</Link></li>)}</ul> : <EmptyState title="No design projects yet" description="Saved design briefs will appear here." />}<div className="request-pagination"><Button variant="ghost" disabled={!offset} onClick={() => setOffset(Math.max(0,offset-20))}>Previous designs</Button><Button variant="ghost" disabled={query.data.next_offset === null} onClick={() => setOffset(query.data.next_offset ?? offset)}>Next designs</Button></div></>}</Card>
}
