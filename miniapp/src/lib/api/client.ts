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

/** Transport only. Domain DTOs will be generated from actual M02/M03 OpenAPI. */
export async function apiRequest<T = unknown>(path: ApiPath, options: RequestOptions = {}): Promise<T> {
  // Disallow origin overrides and traversal, including URL-normalized backslashes.
  if (!/^\/[a-zA-Z0-9][a-zA-Z0-9/_?=&%.,:+-]*$/.test(path)
    || /[\\#]/.test(path)
    || /(?:^|\/)(?:\.|%2e){1,2}(?:\/|\?|$)/i.test(path)
    || /%2f|%5c/i.test(path)) {
    throw new ApiError('Invalid API path', 0, 'invalid_path')
  }

  const { csrfToken, idempotencyKey, ...request } = options
  const method = (request.method ?? 'GET').toUpperCase()
  const headers = new Headers(request.headers)
  headers.set('Accept', 'application/json')
  if (csrfToken) headers.set('X-CSRF-Token', csrfToken)
  if (idempotencyKey) headers.set('Idempotency-Key', idempotencyKey)
  const isTelegramHandshake = path === '/auth/telegram' && method === 'POST'
  // Anonymous login has no session CSRF token yet; FastAPI requires exact Origin.
  // No other mutating endpoint can use this narrow exception.
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !csrfToken && !isTelegramHandshake) {
    throw new ApiError('A session CSRF token is required for changes', 0, 'csrf_required')
  }
  if (typeof request.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`/api/v1${path}`, {
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
    const problem = isRecord(body) ? body : {}
    // Never display arbitrary proxy/HTML/server error bodies or credential-bearing internals.
    if (response.status === 401 && path !== '/auth/me' && path !== '/auth/telegram') {
      window.dispatchEvent(new Event('3dps:session-expired'))
    }
    const messages: Record<number, string> = {
      401: 'Your session has expired. Open the app again in Telegram.',
      403: 'You do not have access to this action.',
      404: 'This item could not be found.',
      409: 'This item has changed. Refresh before trying again.',
      413: 'This file is too large.',
      429: 'Too many sign-in attempts. Please wait before trying again.',
      422: 'Check the information and try again.',
    }
    throw new ApiError(
      messages[response.status] ?? 'The service is unavailable. Please try again.',
      response.status,
      typeof problem['code'] === 'string' ? problem['code'] : 'http_error',
      typeof problem['correlation_id'] === 'string' ? problem['correlation_id'] : undefined,
    )
  }
  if (body === undefined) throw new ApiError('The service returned an invalid response.', response.status, 'invalid_response')
  return body as T
}
