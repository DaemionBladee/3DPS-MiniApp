import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiRequest, apiUpload } from '../../lib/api/client'
import { useAuth } from '../auth/context'
import type { IntakeDetail, ItemSpecification, PrintingOptions } from './types'

type Command = { path: `/requests${string}`; method: 'POST' | 'PATCH' | 'DELETE'; body: object; key: string }
type FailedUpload = { itemId: string; file: File; key: string; message: string }

export function usePrintIntake(requestId: string) {
  const { session } = useAuth()
  const queryClient = useQueryClient()
  const queryKey = ['printing-intake', session?.user.id, requestId] as const
  const current = useRef<IntakeDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const pending = useRef<Command | null>(null)
  const blocked = useRef<ApiError | null>(null)
  const keys = useRef(new Map<string, string>())
  const [resetEpoch, setResetEpoch] = useState(0)
  const [uploadProgress, setUploadProgress] = useState<{ name: string; percent: number } | null>(null)
  const [failedUploads, setFailedUploads] = useState<FailedUpload[]>([])
  const uploadAbort = useRef<AbortController | null>(null)
  const queue = useRef<Promise<unknown>>(Promise.resolve())
  const query = useQuery({ queryKey, enabled: !!session && !!requestId,
    queryFn: async ({ signal }) => {
      const value = await apiRequest<IntakeDetail>(`/requests/${requestId}/intake`, { signal })
      current.current = value
      return value
    },
  })
  const catalog = useQuery({ queryKey: ['printing-options', session?.user.id], enabled: !!session,
    queryFn: ({ signal }) => apiRequest<PrintingOptions>('/catalog/printing-options', { signal }),
  })
  const saved = useCallback(() => {
    const value = current.current ?? queryClient.getQueryData<IntakeDetail>(['printing-intake', session?.user.id, requestId])
    if (!value) throw new ApiError('Load the saved draft first.', 409, 'draft_not_loaded')
    return value
  }, [queryClient, session?.user.id, requestId])
  const apply = useCallback((value: IntakeDetail) => {
    current.current = value
    queryClient.setQueryData(['printing-intake', session?.user.id, requestId], value)
    void queryClient.invalidateQueries({ queryKey: ['requests', session?.user.id] })
  }, [queryClient, session?.user.id, requestId])
  const send = useCallback(async (command: Command) => {
    if (!session) throw new ApiError('Sign in before changing a draft.', 401, 'authentication_required')
    setBusy(true)
    try {
      const value = await apiRequest<IntakeDetail>(command.path, { method: command.method, body: JSON.stringify(command.body), csrfToken: session.csrf_token, idempotencyKey: command.key })
      apply(value)
      setError(null); pending.current = null; blocked.current = null
      keys.current.delete(JSON.stringify([command.path, command.method, command.body]))
      return value
    } catch (failure) {
      const problem = failure instanceof ApiError ? failure : new ApiError('Cannot save this draft. Try again.', 0, 'network_error')
      pending.current = command; setError(problem)
      if (problem.status === 0 || problem.status === 409 || problem.status >= 500 || problem.code === 'invalid_response') blocked.current = problem
      throw problem
    } finally { setBusy(false) }
  }, [session, apply])
  const mutate = useCallback((path: Command['path'], method: Command['method'], body: object) => {
    const signature = JSON.stringify([path, method, body])
    let key = keys.current.get(signature)
    if (!key) { key = crypto.randomUUID(); keys.current.set(signature, key) }
    return send({ path, method, body, key })
  }, [send])
  const enqueue = useCallback(<T,>(work: () => Promise<T>, retry = false): Promise<T> => {
    const run = () => { if (blocked.current && !retry) return Promise.reject<T>(blocked.current); return work() }
    const next = queue.current.then(run, run)
    queue.current = next.catch(() => undefined)
    return next
  }, [])
  const saveItem = useCallback((itemId: string, specification: ItemSpecification) => enqueue(() => mutate(`/requests/${requestId}/items/${itemId}`, 'PATCH', { expected_version: saved().request.version, specification })), [enqueue, mutate, requestId, saved])
  const savePreferences = useCallback((notes: string, method: 'pickup' | 'delivery', fulfillmentNotes: string) => enqueue(() => mutate(`/requests/${requestId}/intake`, 'PATCH', { expected_version: saved().request.version, customer_notes: notes, fulfillment_method: method, fulfillment_notes: fulfillmentNotes })), [enqueue, mutate, requestId, saved])
  const removeItem = useCallback((itemId: string) => enqueue(async () => { const value = await mutate(`/requests/${requestId}/items/${itemId}`, 'DELETE', { expected_version: saved().request.version }); setFailedUploads(previous => previous.filter(upload => upload.itemId !== itemId)); return value }), [enqueue, mutate, requestId, saved])
  const submit = useCallback(() => enqueue(() => mutate(`/requests/${requestId}/submit`, 'POST', { expected_version: saved().request.version })), [enqueue, mutate, requestId, saved])
  const reload = useCallback(async () => {
    const value = await apiRequest<IntakeDetail>(`/requests/${requestId}/intake`)
    apply(value); pending.current = null; blocked.current = null; keys.current.clear(); setError(null); setResetEpoch(value => value + 1)
  }, [requestId, apply])
  const retry = useCallback(() => {
    const command = pending.current
    if (command) void enqueue(() => send(command), true).catch(() => undefined)
  }, [enqueue, send])
  const transfer = useCallback(async (file: File, itemId: string, key: string) => {
    if (!session) return
    if (!catalog.data || file.size < 1 || file.size > catalog.data.max_file_bytes) throw new ApiError('Choose a non-empty model within the file size limit.', 413, 'file_too_large')
    const controller = new AbortController()
    uploadAbort.current = controller
    setUploadProgress({ name: file.name, percent: 0 }); setBusy(true)
    try {
      await apiUpload<IntakeDetail>(`/requests/${requestId}/files?item_id=${itemId}&expected_version=${saved().request.version}`, file,
        { csrfToken: session.csrf_token, idempotencyKey: key, maxBytes: catalog.data.max_file_bytes, signal: controller.signal, onProgress: percent => setUploadProgress({ name: file.name, percent }) })
      apply(await apiRequest<IntakeDetail>(`/requests/${requestId}/intake`))
      setFailedUploads(previous => previous.filter(upload => upload.itemId !== itemId))
    } catch (failure) {
      const message = failure instanceof DOMException && failure.name === 'AbortError' ? 'Upload cancelled. Select or retry the model when ready.' : failure instanceof ApiError ? failure.message : 'Upload failed. Try again.'
      setFailedUploads(previous => [...previous.filter(upload => upload.itemId !== itemId), { itemId, file, key, message }])
      apply(await apiRequest<IntakeDetail>(`/requests/${requestId}/intake`))
    } finally { uploadAbort.current = null; setUploadProgress(null); setBusy(false) }
  }, [session, requestId, saved, apply, catalog.data])
  const addFiles = useCallback((files: File[]) => enqueue(async () => {
    for (const file of files) {
      if (!catalog.data || file.size < 1 || file.size > catalog.data.max_file_bytes) {
        setError(new ApiError('Choose a non-empty model within the file size limit.', 413, 'file_too_large')); return
      }
      const oldIds = new Set(saved().items.map(item => item.id))
      const value = await mutate(`/requests/${requestId}/items`, 'POST', { expected_version: saved().request.version })
      const newItem = value.items.find(item => !oldIds.has(item.id))
      if (!newItem) throw new Error('New item was not returned')
      await transfer(file, newItem.id, crypto.randomUUID())
    }
  }), [enqueue, catalog.data, mutate, requestId, saved, transfer])
  const uploadForItem = useCallback((itemId: string, file: File) => enqueue(() => transfer(file, itemId, crypto.randomUUID())), [enqueue, transfer])
  const retryUpload = useCallback((upload: FailedUpload) => { void enqueue(() => transfer(upload.file, upload.itemId, upload.key)).catch(() => undefined) }, [enqueue, transfer])
  useEffect(() => () => uploadAbort.current?.abort(), [])
  const locked = !!error && (error.status === 0 || error.status === 409 || error.status >= 500 || error.code === 'invalid_response')
  return { query, catalog, busy, error, locked, resetEpoch, uploadProgress, failedUploads, saveItem, savePreferences, removeItem, submit, addFiles, uploadForItem, retryUpload, reload, retry,
    clearValidationError: () => { if (error && !locked) setError(null) }, cancelUpload: () => uploadAbort.current?.abort() }
}
