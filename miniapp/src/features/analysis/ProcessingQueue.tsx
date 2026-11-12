import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { EmptyState, ErrorState, LoadingState } from '../../components/ui/States'
import { apiRequest } from '../../lib/api/client'
import type { components } from '../../lib/api/schema'
import { useAuth } from '../auth/context'
import { TaskRetry } from './TaskRetry'

export function ProcessingQueue() {
  const { session } = useAuth()
  const [opened, setOpened] = useState(false)
  const [offset, setOffset] = useState(0)
  const query = useQuery({ queryKey: ['processing-queue', session?.user.id, offset], enabled: opened && session?.user.role === 'owner',
    queryFn: ({ signal }) => apiRequest<components['schemas']['TaskPage']>(`/owner/processing-tasks?limit=20&offset=${offset}`, { signal }),
    refetchInterval: opened ? 5000 : false,
  })
  if (session?.user.role !== 'owner') return null
  return <Card><h2>Simulation processing queue</h2><p>Private analysis, failures and review indicators. Physical printing remains disabled.</p>
    {!opened ? <Button variant="secondary" onClick={() => setOpened(true)}>Load processing queue</Button> : query.isPending ? <LoadingState /> : query.isError ? <ErrorState onRetry={() => { void query.refetch() }} /> : <>
      {query.data.items.length === 0 && <EmptyState title="No analysis tasks" description="Submitted printing models will appear here." />}
      {query.data.items.map(task => <div key={task.id} className="request-row"><p>{task.state} · attempts {task.attempts}/{task.max_attempts}</p>{task.error_code && <p>Failure: {task.error_code.replaceAll('_', ' ')}</p>}{task.special_requirements && <p>Special requirements — Owner review needed.</p>}<Link to={`/owner/requests/${task.request_id}`}>Inspect analysis {task.id.slice(0, 8)}</Link>{['failed', 'succeeded'].includes(task.state) && <TaskRetry taskId={task.id} requestId={task.request_id} refresh={query.refetch} />}</div>)}
      <div className="request-pagination"><Button variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous tasks</Button><Button variant="ghost" disabled={query.data.next_offset == null} onClick={() => setOffset(query.data.next_offset ?? offset)}>Next tasks</Button><Button variant="secondary" onClick={() => { void query.refetch() }}>Refresh queue</Button></div>
    </>}
  </Card>
}
