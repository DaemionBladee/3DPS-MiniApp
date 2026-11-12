import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { apiRequest } from '../../lib/api/client'
import type { components } from '../../lib/api/schema'
import { useAuth } from '../auth/context'

type Profile = components['schemas']['SimulationProfile']
export function TaskRetry({ taskId, requestId, refresh }: { taskId: string; requestId: string; refresh: () => Promise<unknown> }) {
  const { session } = useAuth()
  const [opened, setOpened] = useState(false)
  const [reason, setReason] = useState('')
  const [profileId, setProfileId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const command = useRef<{ fingerprint: string; key: string; body: components['schemas']['RetryTask'] } | null>(null)
  const profiles = useQuery({ queryKey: ['simulation-profiles', session?.user.id], enabled: opened && session?.user.role === 'owner',
    queryFn: ({ signal }) => apiRequest<Profile[]>('/catalog/simulation-profiles', { signal }),
  })
  if (session?.user.role !== 'owner') return null
  const retry = async () => {
    setBusy(true); setError(null)
    try {
      const fingerprint = JSON.stringify([reason.trim(), profileId])
      if (command.current?.fingerprint !== fingerprint) {
        const row = await apiRequest<components['schemas']['RequestResponse']>(`/requests/${requestId}`)
        command.current = { fingerprint, key: crypto.randomUUID(), body: { expected_version: row.version, reason: reason.trim(), profile_id: profileId || null } }
      }
      await apiRequest(`/owner/processing-tasks/${taskId}/retry`, { method: 'POST', body: JSON.stringify(command.current.body), csrfToken: session.csrf_token, idempotencyKey: command.current.key })
      await refresh(); setOpened(false)
    } catch { setError('Simulation retry could not be scheduled. Refresh and check the profile or retry budget.') }
    finally { setBusy(false) }
  }
  if (!opened) return <Button variant="secondary" onClick={() => setOpened(true)}>Review simulation retry</Button>
  return <fieldset className="print-form" disabled={busy}><legend>Reschedule simulation only</legend>
    <label htmlFor={`reason-${taskId}`}>Review reason</label><textarea id={`reason-${taskId}`} minLength={8} maxLength={500} value={reason} onChange={event => setReason(event.target.value)} />
    <label htmlFor={`profile-${taskId}`}>Approved profile</label><select id={`profile-${taskId}`} value={profileId} onChange={event => setProfileId(event.target.value)}><option value="">Keep current profile</option>{profiles.data?.map(p => <option value={p.id} key={p.id}>{p.key} v{p.version} (uncalibrated)</option>)}</select>
    {profiles.isError && <p role="alert">Profiles unavailable.</p>}{error && <p role="alert">{error}</p>}
    <Button disabled={busy || reason.trim().length < 8} onClick={() => { void retry() }}>Schedule simulation retry</Button><Button variant="ghost" onClick={() => setOpened(false)}>Cancel review</Button>
  </fieldset>
}
