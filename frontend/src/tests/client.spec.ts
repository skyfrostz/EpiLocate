import { describe, expect, it, vi } from 'vitest'
import { ApiClient, ApiRequestError } from '../api/client'

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

  it('rejects a success page that is not JSON', async () => {
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher: vi.fn(async () => new Response('<html>app</html>', {
      status: 200, headers: { 'Content-Type': 'text/html' },
    })) as typeof fetch })
    await expect(client.getResult('result_1')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })
})
