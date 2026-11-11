import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiRequest } from './client'

afterEach(() => vi.unstubAllGlobals())

describe('same-origin API transport', () => {
  it('uses relative versioned paths, same-origin cookies and no role header', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ status: 'ok' }))
    vi.stubGlobal('fetch', fetcher)
    await expect(apiRequest('/health')).resolves.toEqual({ status: 'ok' })
    const [url, options] = fetcher.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/health')
    expect(options).toMatchObject({ credentials: 'same-origin', mode: 'same-origin', redirect: 'error', method: 'GET' })
    const headers = new Headers(options.headers)
    expect(headers.get('Accept')).toBe('application/json')
    expect(headers.has('Authorization')).toBe(false)
    expect(headers.has('X-Role')).toBe(false)
  })

  it.each(['//evil.example/path', '/../auth', '/%2e%2e/auth', '/%2e./auth', '/files%2f..', '/x\\..\\auth', '/health#fragment'])('rejects origin/path escape %s before fetching', async path => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    await expect(apiRequest(path as `/${string}`)).rejects.toMatchObject({ code: 'invalid_path' })
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('normalizes network and HTML proxy failures without exposing response content', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new TypeError('internal address'))
      .mockResolvedValueOnce(new Response('<h1>internal trace</h1>', { status: 502, headers: { 'content-type': 'text/html' } }))
    vi.stubGlobal('fetch', fetcher)
    await expect(apiRequest('/health')).rejects.toMatchObject({ status: 0, code: 'network_error' })
    await expect(apiRequest('/health')).rejects.toMatchObject({ status: 502, message: 'The service is unavailable. Please try again.' })
  })

  it.each([401, 403, 404, 409, 413, 422])('preserves typed HTTP %s and safe correlation metadata', async status => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ code: 'request_rejected', correlation_id: 'test-ref', message: 'unsafe internal details' }, { status })))
    await expect(apiRequest('/health')).rejects.toMatchObject({ status, code: 'request_rejected', correlationId: 'test-ref' })
    try { await apiRequest('/health') } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      expect((error as ApiError).message).not.toContain('unsafe internal')
    }
  })

  it('refuses writes without CSRF and carries explicit CSRF/idempotency when supplied', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204, headers: { 'content-type': 'application/json' } }))
    vi.stubGlobal('fetch', fetcher)
    await expect(apiRequest('/example', { method: 'POST', body: '{}' })).rejects.toMatchObject({ code: 'csrf_required' })
    expect(fetcher).not.toHaveBeenCalled()
    await expect(apiRequest('/example', { method: 'POST', body: '{}', csrfToken: 'test-csrf', idempotencyKey: 'test-command' })).resolves.toBeUndefined()
    const [, options] = fetcher.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(options.headers)
    expect(headers.get('X-CSRF-Token')).toBe('test-csrf')
    expect(headers.get('Idempotency-Key')).toBe('test-command')
    expect(headers.get('Content-Type')).toBe('application/json')
  })

  it('allows only the anonymous Telegram handshake without a CSRF token', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ status: 'fixture' }))
    vi.stubGlobal('fetch', fetcher)
    await apiRequest('/auth/telegram', { method: 'POST', body: JSON.stringify({ init_data: 'raw-test-proof' }) })
    expect(fetcher).toHaveBeenCalledTimes(1)
    await expect(apiRequest('/auth/logout', { method: 'POST' })).rejects.toMatchObject({ code: 'csrf_required' })
    await expect(apiRequest('/auth/telegram/other', { method: 'POST' })).rejects.toMatchObject({ code: 'csrf_required' })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('does not broadcast initial authentication 401 responses as expired sessions', async () => {
    const expired = vi.fn()
    window.addEventListener('3dps:session-expired', expired)
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(Response.json({}, { status: 401 }))))
    try {
      await expect(apiRequest('/auth/me')).rejects.toMatchObject({ status: 401 })
      await expect(apiRequest('/auth/telegram', { method: 'POST', body: '{}' })).rejects.toMatchObject({ status: 401 })
      expect(expired).not.toHaveBeenCalled()
      await expect(apiRequest('/owner/auth-check')).rejects.toMatchObject({ status: 401 })
      expect(expired).toHaveBeenCalledOnce()
    } finally { window.removeEventListener('3dps:session-expired', expired) }
  })

  it('handles a successful HEAD response without trying to parse an empty JSON body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 200, headers: { 'content-type': 'application/json' } })))
    await expect(apiRequest('/health', { method: 'HEAD' })).resolves.toBeUndefined()
  })

  it('rejects malformed JSON and accidental HTML success instead of treating Vite fallback as API data', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response('{', { headers: { 'content-type': 'application/json' } }))
      .mockResolvedValueOnce(new Response('<html>SPA</html>', { headers: { 'content-type': 'text/html' } })))
    await expect(apiRequest('/health')).rejects.toMatchObject({ code: 'invalid_response' })
    await expect(apiRequest('/health')).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('keeps cancellation distinguishable from connection failure', async () => {
    const controller = new AbortController()
    controller.abort()
    const error = new DOMException('Cancelled', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(error))
    await expect(apiRequest('/health', { signal: controller.signal })).rejects.toBe(error)
  })
})
