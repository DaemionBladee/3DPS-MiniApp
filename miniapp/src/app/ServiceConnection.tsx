import { useQuery } from '@tanstack/react-query'
import { apiRequest } from '../lib/api/client'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ErrorState, LoadingState } from '../components/ui/States'

/** Optional local transport check; never a mock server or an identity probe. */
export function ServiceConnection() {
  const connection = useQuery({
    queryKey: ['service-health'],
    queryFn: ({ signal }) => apiRequest('/health', { signal }),
    enabled: false,
  })
  return <Card className="connection-card" aria-labelledby="connection-title">
    <h2 id="connection-title">Service connection</h2>
    <p>This local preview has no connected project records. You can check the API when a backend is available.</p>
    {connection.isFetching ? <LoadingState label="Checking service connection…" />
      : connection.isError ? <ErrorState title="Service not connected" description={connection.error.message} onRetry={() => { void connection.refetch() }} />
        : connection.isSuccess ? <p role="status">Service reachable. This does not sign you in or enable ordering.</p>
          : <Button variant="secondary" onClick={() => { void connection.refetch() }}>Check connection</Button>}
  </Card>
}
