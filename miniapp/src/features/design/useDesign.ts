import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiRequest, apiUpload } from '../../lib/api/client'
import { useAuth } from '../auth/context'
import type { DesignDetail } from './types'
import type { components } from '../../lib/api/schema'

type Command = { path: `/design-projects/${string}` | `/owner/design-projects/${string}` | `/requests/${string}`; method: 'POST' | 'PATCH' | 'DELETE'; body: object; key: string }
export function useDesign(identity?: string, requestId?: string) {
  const { session } = useAuth()
  const client = useQueryClient()
  const queryKey = ['design', session?.user.id, identity, requestId] as const
  const current = useRef<DesignDetail | undefined>(undefined)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [epoch, setEpoch] = useState(0)
  const failed = useRef<Command | null>(null)
  const [uploadFailure, setUploadFailure] = useState<{ file: File; purpose: string; key: string } | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const abort = useRef<AbortController | null>(null)
  const query = useQuery({ queryKey, enabled: !!session && !!(identity || requestId), queryFn: async ({ signal }) => {
    const data = await apiRequest<DesignDetail>(identity ? `/design-projects/${identity}` : `/requests/${requestId}/design`, { signal })
    current.current = data
    return data
  } })
  const apply = useCallback((data: DesignDetail) => {
    current.current = data; client.setQueryData(['design', session?.user.id, identity, requestId], data)
    void client.invalidateQueries({ queryKey: ['requests', session?.user.id] })
    void client.invalidateQueries({ queryKey: ['design-projects', session?.user.id] })
  }, [client, session?.user.id, identity, requestId])
  const reload = useCallback(async () => {
    const result = await apiRequest<DesignDetail>(identity ? `/design-projects/${identity}` : `/requests/${requestId}/design`)
    apply(result); setError(null); failed.current = null; setUploadFailure(null); setEpoch(value => value+1)
  }, [identity, requestId, apply])
  const send = useCallback(async (command: Command) => {
    if (!session) throw new ApiError('Sign in first.', 401, 'authentication_required')
    setBusy(true)
    try {
      const result = await apiRequest<DesignDetail>(command.path, { method: command.method, body: JSON.stringify(command.body), idempotencyKey: command.key, csrfToken: session.csrf_token })
      apply(result); setError(null); failed.current = null
      return result
    } catch (failure) {
      const problem = failure instanceof ApiError ? failure : new ApiError('Cannot save this design. Retry or reload saved data.', 0, 'network_error')
      failed.current = command; setError(problem); throw problem
    } finally { setBusy(false) }
  }, [session, apply])
  const mutate = useCallback((action: string, body: object = {}, owner = false, method: Command['method'] = 'POST') => {
    const data = current.current
    if (!data) return Promise.reject(new Error('Load the design first'))
    return send({ path: `/${owner ? 'owner/' : ''}design-projects/${data.id}/${action}`, body: { expected_version: data.request.version, ...body }, method, key: crypto.randomUUID() })
  }, [send])
  const transfer = useCallback(async (file: File, purpose: string, key: string = crypto.randomUUID()) => {
    const data = current.current
    if (!session || !data) return
    const controller = new AbortController(); abort.current = controller
    setBusy(true); setProgress(0)
    try {
      const result = await apiUpload<DesignDetail>(`/requests/${data.request.id}/design/files?purpose=${purpose}&expected_version=${data.request.version}`, file, { csrfToken: session.csrf_token, idempotencyKey: key, maxBytes: 25*1024*1024, signal: controller.signal, onProgress: setProgress })
      apply(await apiRequest<DesignDetail>(`/design-projects/${result.id}`)); setUploadFailure(null); setError(null)
    } catch (failure) {
      setUploadFailure({ file, purpose, key })
      setError(failure instanceof ApiError ? failure : new ApiError('Upload interrupted. Retry or reload; committed data is preserved.', 0, 'upload_interrupted'))
    } finally { setBusy(false); setProgress(null); abort.current = null }
  }, [session, apply])
  const initialize = () => {
    if (session && requestId) void (async () => {
      const request = await apiRequest<components['schemas']['RequestResponse']>(`/requests/${requestId}`)
      return send({ path: `/requests/${requestId}/design`, method: 'POST', body: { expected_version: request.version }, key: crypto.randomUUID() })
    })().catch(() => undefined)
  }
  useEffect(() => () => abort.current?.abort(), [])
  return { query, busy, error, epoch, progress, mutate, transfer, reload, initialize, uploadFailure, cancel: () => abort.current?.abort(), retry: () => { if (uploadFailure) void transfer(uploadFailure.file, uploadFailure.purpose, uploadFailure.key); else if (failed.current) void send(failed.current).catch(() => undefined) } }
}
