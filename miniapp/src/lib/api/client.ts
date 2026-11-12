export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly correlationId: string | undefined

  constructor(message: string, status: number, code: string, correlationId?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.correlationId = correlationId
  }
}

type ApiPath = `/${string}`
type RequestOptions = Omit<RequestInit, 'credentials' | 'mode' | 'redirect'> & {
  csrfToken?: string
  idempotencyKey?: string
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

export function apiUrl(path: ApiPath): string {
  // Disallow origin overrides and traversal, including URL-normalized backslashes.
  if (!/^\/[a-zA-Z0-9][a-zA-Z0-9/_?=&%.,:+-]*$/.test(path)
    || /[\\#]/.test(path)
    || /(?:^|\/)(?:\.|%2e){1,2}(?:\/|\?|$)/i.test(path)
    || /%2f|%5c/i.test(path)) {
    throw new ApiError('Invalid API path', 0, 'invalid_path')
  }

  return `/api/v1${path}`
}

export function responseError(path: ApiPath, status: number, body: unknown): ApiError {
  const problem = isRecord(body) ? body : {}
  if (status === 401 && path !== '/auth/me' && path !== '/auth/telegram') window.dispatchEvent(new Event('3dps:session-expired'))
  const messages: Record<number, string> = {
    401: 'Your session has expired. Open the app again in Telegram.',
    403: 'You do not have access to this action.',
    404: 'This item could not be found.',
    409: 'This item has changed. Refresh before trying again.',
    413: 'This file is too large.',
    415: 'This file format or content is not supported.',
    429: 'A rate or storage limit was reached. Wait or remove unused draft models.',
    422: 'Check the request fields or file, then try again.',
  }
  return new ApiError(messages[status] ?? 'The service is unavailable. Please try again.', status,
    typeof problem['code'] === 'string' ? problem['code'] : 'http_error',
    typeof problem['correlation_id'] === 'string' ? problem['correlation_id'] : undefined)
}

/** One same-origin transport and safe error policy for generated API contracts. */
export async function apiRequest<T = unknown>(path: ApiPath, options: RequestOptions = {}): Promise<T> {
  const url = apiUrl(path)
  const { csrfToken, idempotencyKey, ...request } = options
  const method = (request.method ?? 'GET').toUpperCase()
  const headers = new Headers(request.headers)
  headers.set('Accept', 'application/json')
  if (csrfToken) headers.set('X-CSRF-Token', csrfToken)
  if (idempotencyKey) headers.set('Idempotency-Key', idempotencyKey)
  const isTelegramHandshake = path === '/auth/telegram' && method === 'POST'
  // Anonymous login has no session CSRF token yet; FastAPI requires verified
  // Telegram launch data and its browser-origin policy (including opaque WebViews).
  // No other mutating endpoint can use this narrow exception.
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !csrfToken && !isTelegramHandshake) {
    throw new ApiError('A session CSRF token is required for changes', 0, 'csrf_required')
  }
  if (typeof request.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(url, {
      ...request,
      method,
      headers,
      credentials: 'same-origin',
      mode: 'same-origin',
      redirect: 'error',
    })
  } catch (error) {
    if (request.signal?.aborted) throw error
    throw new ApiError('Cannot reach the service. Please try again.', 0, 'network_error')
  }

  if (response.ok && (response.status === 204 || response.status === 205 || method === 'HEAD')) {
    return undefined as T
  }
  const contentType = response.headers.get('content-type') ?? ''
  let body: unknown
  if (method !== 'HEAD' && (contentType.includes('application/json') || contentType.includes('application/problem+json'))) {
    try { body = await response.json() } catch {
      throw new ApiError('The service returned an invalid response.', response.status, 'invalid_response')
    }
  }
  if (!response.ok) {
    throw responseError(path, response.status, body)
  }
  if (body === undefined) throw new ApiError('The service returned an invalid response.', response.status, 'invalid_response')
  return body as T
}


/** Raw binary upload with actual browser upload progress; model bytes stay in memory. */
export async function apiUpload<T>(path: ApiPath, file: File, options: {
  csrfToken: string; idempotencyKey: string; maxBytes: number; signal: AbortSignal; onProgress: (percent: number) => void
}): Promise<T> {
  const url = apiUrl(path)
  if (!options.csrfToken) throw new ApiError('A session CSRF token is required for changes', 0, 'csrf_required')
  if (options.signal.aborted) throw new DOMException('Upload cancelled', 'AbortError')
  if (file.size < 1 || file.size > options.maxBytes) throw new ApiError('This file is too large or empty.', 413, 'file_too_large')
  const bytes = await file.arrayBuffer()
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const checksum = Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('')
  if (options.signal.aborted) throw new DOMException('Upload cancelled', 'AbortError')
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const abort = () => xhr.abort()
    const clear = () => options.signal.removeEventListener('abort', abort)
    xhr.open('POST', url)
    xhr.withCredentials = true
    xhr.timeout = 90_000
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')
    xhr.setRequestHeader('X-CSRF-Token', options.csrfToken)
    xhr.setRequestHeader('Idempotency-Key', options.idempotencyKey)
    xhr.setRequestHeader('X-File-Name', encodeURIComponent(file.name))
    xhr.setRequestHeader('X-File-Size', String(file.size))
    xhr.setRequestHeader('X-Content-SHA256', checksum)
    xhr.upload.onprogress = event => { if (event.lengthComputable) options.onProgress(Math.min(100, Math.round(event.loaded / event.total * 100))) }
    xhr.onload = () => {
      clear()
      if (xhr.responseURL && xhr.responseURL !== new URL(url, window.location.origin).href) {
        reject(new ApiError('The upload endpoint redirected unexpectedly.', 0, 'unexpected_redirect')); return
      }
      let body: unknown
      try { body = JSON.parse(xhr.responseText) } catch { reject(new ApiError('The service returned an invalid response.', xhr.status, 'invalid_response')); return }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T)
      else reject(responseError(path, xhr.status, body))
    }
    xhr.onerror = () => { clear(); reject(new ApiError('Cannot reach the service. Please try again.', 0, 'network_error')) }
    xhr.ontimeout = xhr.onerror
    xhr.onabort = () => { clear(); reject(new DOMException('Upload cancelled', 'AbortError')) }
    options.signal.addEventListener('abort', abort, { once: true })
    xhr.send(file)
  })
}

export async function apiPrivateBlob(path: ApiPath): Promise<Blob> {
  const response = await fetch(apiUrl(path), { credentials: 'same-origin', mode: 'same-origin', redirect: 'error' })
  if (!response.ok) {
    let body: unknown
    try { body = await response.json() } catch { body = null }
    throw responseError(path, response.status, body)
  }
  return response.blob()
}

export async function apiDownload(path: ApiPath, name: string): Promise<void> {
  const url = URL.createObjectURL(await apiPrivateBlob(path))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = name; anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
