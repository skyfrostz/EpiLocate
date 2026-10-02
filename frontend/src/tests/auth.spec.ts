import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClient } from '../api/client'
import { auth, clearSession, loadSession, login, logout } from '../auth/session'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
})

beforeEach(() => {
  clearSession()
  sessionStorage.clear()
  auth.loaded = false
  vi.unstubAllGlobals()
})

describe('browser session', () => {
  it('loads a server session and sends CSRF without a Backend Bearer', async () => {
    const fetcher = vi.fn(async () => json({ username: 'alice', csrf_token: 'csrf-test' }))
    vi.stubGlobal('fetch', fetcher)
    expect(await loadSession()).toBe(true)
    expect(auth.username).toBe('alice')
    const apiFetch = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => json({ case_id: 'case_1' }, 201))
    await new ApiClient({ fetcher: apiFetch as typeof fetch }).createCase(null, 'key-12345678')
    const headers = apiFetch.mock.calls[0]?.[1]?.headers as Record<string, string>
    expect(headers['X-CSRF-Token']).toBe('csrf-test')
    expect(headers.Authorization).toBeUndefined()
  })

  it('reports login throttling and logs out with CSRF', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(json({ code: 'LOGIN_RATE_LIMITED' }, 429))
      .mockResolvedValueOnce(json({ username: 'alice', csrf_token: 'csrf-new' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetcher)
    await expect(login('alice', 'wrong')).rejects.toThrow('尝试次数过多')
    await login('alice', 'correct-password')
    expect(auth.username).toBe('alice')
    sessionStorage.setItem('epilocate:fusion:result_alice', '{"scale":16}')
    sessionStorage.setItem('unrelated-preference', 'keep')
    await logout()
    expect(auth.username).toBeNull()
    expect(sessionStorage.getItem('epilocate:fusion:result_alice')).toBeNull()
    expect(sessionStorage.getItem('epilocate:session-account')).toBeNull()
    expect(sessionStorage.getItem('unrelated-preference')).toBe('keep')
    expect(fetcher.mock.calls[2]?.[1]?.headers).toEqual({ 'X-CSRF-Token': 'csrf-new' })
  })

  it('preserves same-user preferences on refresh and clears them when identity changes', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(json({ username: 'alice', csrf_token: 'a' }))
      .mockResolvedValueOnce(json({ username: 'alice', csrf_token: 'a' }))
      .mockResolvedValueOnce(json({ username: 'bob', csrf_token: 'b' }))
    vi.stubGlobal('fetch', fetcher)
    await loadSession()
    sessionStorage.setItem('epilocate:fusion:result_alice', '{"scale":16}')
    await loadSession(true)
    expect(sessionStorage.getItem('epilocate:fusion:result_alice')).not.toBeNull()
    await loadSession(true)
    expect(sessionStorage.getItem('epilocate:fusion:result_alice')).toBeNull()
    expect(sessionStorage.getItem('epilocate:session-account')).toBe('bob')
  })

  it('clears the browser session after an API 401', async () => {
    auth.username = 'alice'
    auth.csrfToken = 'csrf-test'
    auth.loaded = true
    const client = new ApiClient({ fetcher: vi.fn(async () => json({ code: 'UNAUTHENTICATED' }, 401)) as typeof fetch })
    await expect(client.listCases()).rejects.toMatchObject({ status: 401 })
    expect(auth.username).toBeNull()
  })
})
