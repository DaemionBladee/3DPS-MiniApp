import { waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiUpload } from './client'

class FakeXHR {
  static instances: FakeXHR[] = []
  headers = new Headers()
  method = ''; url = ''; body: unknown
  withCredentials = false; timeout = 0; status = 0; responseText = ''; responseURL = ''
  upload = { onprogress: null as ((event: ProgressEvent) => void) | null }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  ontimeout: (() => void) | null = null
  onabort: (() => void) | null = null
  constructor() { FakeXHR.instances.push(this) }
  open(method: string, url: string) { this.method = method; this.url = url }
  setRequestHeader(name: string, value: string) { this.headers.set(name, value) }
  send(body: unknown) { this.body = body }
  abort() { this.onabort?.() }
  respond(status: number, body: unknown) { this.status = status; this.responseText = JSON.stringify(body); this.onload?.() }
}
const path = '/requests/00000000-0000-4000-8000-000000000001/files?item_id=00000000-0000-4000-8000-000000000002&expected_version=2' as const
const bytes = new TextEncoder().encode('synthetic STL bytes')
const digestHex = '31be929d58092b6272457284b289c3c37a65f90200b273f26808247b07dd3e8f'
const digest = vi.fn(async () => Uint8Array.from(digestHex.match(/../g)!, byte => Number.parseInt(byte, 16)).buffer)
function model() {
  const file = new File([bytes], 'စမ်းသပ်.stl', { type: 'application/untrusted-client-type' })
  Object.defineProperty(file, 'arrayBuffer', { value: vi.fn(async () => bytes.buffer) })
  return file
}
const options = () => ({ csrfToken: 'memory-csrf-token', idempotencyKey: 'synthetic-command-key', maxBytes: 1024, signal: new AbortController().signal, onProgress: vi.fn() })
beforeEach(() => { FakeXHR.instances = []; vi.stubGlobal('XMLHttpRequest', FakeXHR); digest.mockClear(); vi.stubGlobal('crypto', { subtle: { digest } }) })

describe('secure binary upload transport', () => {
  it('hashes exact model bytes and sends cookie/CSRF/key with actual progress', async () => {
    const file = model(); const config = options()
    const result = apiUpload(path, file, config)
    await waitFor(() => expect(FakeXHR.instances).toHaveLength(1))
    const xhr = FakeXHR.instances[0]!
    expect(xhr.url).toBe(`/api/v1${path}`); expect(xhr.method).toBe('POST')
    expect(xhr.withCredentials).toBe(true); expect(xhr.body).toBe(file)
    expect(xhr.headers.get('X-CSRF-Token')).toBe('memory-csrf-token')
    expect(xhr.headers.get('Idempotency-Key')).toBe('synthetic-command-key')
    expect(xhr.headers.get('X-File-Size')).toBe(String(bytes.length))
    expect(xhr.headers.get('X-File-Name')).toBe(encodeURIComponent(file.name))
    expect(xhr.headers.get('X-Content-SHA256')).toBe(digestHex)
    expect(digest).toHaveBeenCalledWith('SHA-256', bytes.buffer)
    expect(xhr.headers.get('Content-Type')).toBe('application/octet-stream')
    xhr.upload.onprogress?.(new ProgressEvent('progress', { lengthComputable: true, loaded: 5, total: 10 }))
    expect(config.onProgress).toHaveBeenCalledWith(50)
    xhr.respond(201, { accepted: true })
    await expect(result).resolves.toEqual({ accepted: true })
  })

  it('aborts an in-flight upload and never invents completion', async () => {
    const controller = new AbortController(); const config = { ...options(), signal: controller.signal }
    const result = apiUpload(path, model(), config)
    const assertion = expect(result).rejects.toMatchObject({ name: 'AbortError' })
    await waitFor(() => expect(FakeXHR.instances).toHaveLength(1))
    controller.abort()
    await assertion
    expect(config.onProgress).not.toHaveBeenCalled()
  })

  it.each([401, 403, 409, 413, 415, 422, 429])('normalizes upload HTTP %s without echoing unsafe server text', async status => {
    const result = apiUpload(path, model(), options())
    const assertion = expect(result).rejects.toMatchObject({ status, code: 'safe_code' })
    await waitFor(() => expect(FakeXHR.instances).toHaveLength(1))
    FakeXHR.instances[0]!.respond(status, { code: 'safe_code', message: 'DO_NOT_DISPLAY_UNTRUSTED_CONTENT' })
    await assertion
  })

  it('rejects unsafe paths, missing CSRF and oversized input before reading bytes', async () => {
    const file = model()
    await expect(apiUpload('//external.invalid/files', file, options())).rejects.toBeInstanceOf(ApiError)
    await expect(apiUpload(path, file, { ...options(), csrfToken: '' })).rejects.toMatchObject({ code: 'csrf_required' })
    await expect(apiUpload(path, file, { ...options(), maxBytes: 1 })).rejects.toMatchObject({ status: 413 })
    expect(file.arrayBuffer).not.toHaveBeenCalled(); expect(FakeXHR.instances).toHaveLength(0)
  })

  it('rejects a redirected upload response', async () => {
    const result = apiUpload(path, model(), options())
    const assertion = expect(result).rejects.toMatchObject({ code: 'unexpected_redirect' })
    await waitFor(() => expect(FakeXHR.instances).toHaveLength(1))
    FakeXHR.instances[0]!.responseURL = 'https://external.invalid/files'
    FakeXHR.instances[0]!.respond(200, {})
    await assertion
  })
})
