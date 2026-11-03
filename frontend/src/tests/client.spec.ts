import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { ApiClient, ApiRequestError } from '../api/client'
import { clearSession } from '../auth/session'

beforeEach(() => { clearSession(false) })
afterEach(() => { vi.restoreAllMocks() })

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
})

describe('Backend API v2 client', () => {
  it('uses the frozen Case path, cursor and same-origin credentials', async () => {
    const fetchSpy = vi.fn(async () => json({ items: [], next_cursor: null }))
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher: fetchSpy as typeof fetch })
    const page = await client.listCases('opaque-cursor', 20)
    expect(page.items).toEqual([])
    expect(fetchSpy).toHaveBeenCalledWith('/api/v2/cases?limit=20&cursor=opaque-cursor',
      expect.objectContaining({ credentials: 'include' }))
  })

  it('uses a server-generated Case ID path and idempotency header for creation', async () => {
    const fetchSpy = vi.fn(async () => json({ case_id: 'case_1', patient_id: 'pat_1', status: 'CREATED', created_at: '2026-09-26T00:00:00Z' }, 201))
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher: fetchSpy as typeof fetch })
    await client.createCase(null, 'key-12345678')
    expect(fetchSpy).toHaveBeenCalledWith('/api/v2/cases', expect.objectContaining({
      method: 'POST', body: '{"patient_id":null}',
      headers: expect.objectContaining({ 'Idempotency-Key': 'key-12345678' }),
    }))
  })

  it('reads a retained Case DICOM as a private binary response', async () => {
    const fetcher = vi.fn(async () => new Response(new Blob(['dicom']), {
      status: 200, headers: { 'Content-Type': 'application/dicom' },
    }))
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher: fetcher as typeof fetch })
    const blob = await client.getCaseDicom('case_1')
    expect(blob.type).toBe('application/dicom')
    expect(blob.size).toBeGreaterThan(0)
    expect(fetcher).toHaveBeenCalledWith('/api/v2/cases/case_1/dicom', expect.anything())
  })

  it('surfaces the frozen API error object without a Mock fallback', async () => {
    const fetcher = vi.fn(async () => json({
      code: 'CASE_NOT_FOUND', message: 'Case not found.', retryable: false,
      request_id: 'req-1', details: {},
    }, 404))
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher: fetcher as typeof fetch })
    await expect(client.getCase('case_missing')).rejects.toMatchObject({
      status: 404, code: 'CASE_NOT_FOUND', requestId: 'req-1', retryable: false,
    })
  })

  it('surfaces 401 authentication errors to the UI layer', async () => {
    const fetcher = vi.fn(async () => json({
      code: 'UNAUTHENTICATED', message: 'Authentication required.', retryable: false,
      request_id: 'req-auth', details: {},
    }, 401))
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher: fetcher as typeof fetch })
    await expect(client.listCases()).rejects.toMatchObject({
      status: 401, code: 'UNAUTHENTICATED', requestId: 'req-auth', retryable: false,
    })
  })

  it('reports transport failure without creating a result', async () => {
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher: vi.fn(async () => { throw new Error('offline') }) as typeof fetch })
    await expect(client.getJob('job_1')).rejects.toMatchObject({
      status: 0, code: 'NETWORK_UNAVAILABLE', retryable: true,
    } satisfies Partial<ApiRequestError>)
  })


  it.each(['json', 'dicom', 'asset'])('normalizes a %s body timeout after successful headers', async kind => {
    const timeout = new AbortController()
    vi.spyOn(AbortSignal, 'timeout').mockReturnValue(timeout.signal)
    const response = new Response(null, { headers: { 'Content-Type': kind === 'json' ? 'application/json'
      : kind === 'dicom' ? 'application/dicom' : 'image/png' } })
    let rejectBody!: (error: unknown) => void
    const body = new Promise<never>((_resolve, reject) => { rejectBody = reject })
    if (kind === 'json') vi.spyOn(response, 'json').mockReturnValue(body)
    else vi.spyOn(response, 'blob').mockReturnValue(body)
    const fetcher = vi.fn(async () => response)
    const client = new ApiClient({ fetcher })
    const request = kind === 'json' ? client.getCase('case_1') : kind === 'dicom'
      ? client.getCaseDicom('case_1') : client.getResultAsset('result_1', 'layer')
    const rejected = expect(request).rejects.toMatchObject({ code: 'REQUEST_TIMEOUT', retryable: true })
    await flushPromises()
    const reason = new DOMException('timeout', 'TimeoutError')
    timeout.abort(reason); rejectBody(reason)
    await rejected
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('preserves caller cancellation during body consumption', async () => {
    const abort = new AbortController()
    const response = json({})
    let rejectBody!: (error: unknown) => void
    vi.spyOn(response, 'json').mockReturnValue(new Promise((_resolve, reject) => { rejectBody = reject }))
    const request = new ApiClient({ fetcher: vi.fn(async () => response) }).getCase('case_1', abort.signal)
    const rejected = expect(request).rejects.toMatchObject({ name: 'AbortError' })
    await flushPromises()
    abort.abort(); rejectBody(abort.signal.reason)
    await rejected
  })

  it('keeps malformed JSON distinct from interrupted body transfer', async () => {
    const malformed = new ApiClient({ fetcher: vi.fn(async () => new Response('{', { headers: { 'Content-Type': 'application/json' } })) })
    await expect(malformed.getCase('case_1')).rejects.toMatchObject({ code: 'INVALID_RESPONSE', retryable: false })
    const interrupted = json({})
    vi.spyOn(interrupted, 'json').mockRejectedValue(new TypeError('terminated'))
    await expect(new ApiClient({ fetcher: vi.fn(async () => interrupted) }).getCase('case_1'))
      .rejects.toMatchObject({ code: 'NETWORK_UNAVAILABLE', retryable: true })
  })

  it('rejects a success page that is not JSON', async () => {
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher: vi.fn(async () => new Response('<html>app</html>', {
      status: 200, headers: { 'Content-Type': 'text/html' },
    })) as typeof fetch })
    await expect(client.getResult('result_1')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })
})
