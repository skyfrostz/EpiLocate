import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { auth, clearSession, loadSession, login, logout, startSessionSync } from '../auth/session'
import { sessionEpoch } from '../auth/lifecycle'
import { SESSION_SYNC_KEY } from '../auth/sessionSync'
import { ApiClient } from '../api/client'
import { useCaseStore } from '../stores/cases'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
function notify(nonce = '12345678-abcd-1234-abcd-123456789012') {
  window.dispatchEvent(new StorageEvent('storage', { key: SESSION_SYNC_KEY, newValue: nonce }))
}
let dispose: () => void
let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  clearSession(false)
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  auth.username = 'alice'; auth.csrfToken = 'alice-csrf'; auth.loaded = true
  dispose = startSessionSync()
})
afterEach(() => { dispose(); disposePinia(pinia); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('shared Cookie identity synchronization', () => {
  it('immediately clears old identity/cache and rejects its delayed API response on another tab login', async () => {
    const pendingSession = deferred<Response>(), pendingCases = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(() => pendingSession.promise))
    const store = useCaseStore()
    store.setPage([{ case_id: 'alice-case', patient_id: 'alice', status: 'CREATED', created_at: '', input_expires_at: null }], null)
    const request = new ApiClient({ fetcher: vi.fn(() => pendingCases.promise) as typeof fetch }).listCases()
    const rejected = expect(request).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
    const epoch = sessionEpoch.value
    notify()
    expect(sessionEpoch.value).toBeGreaterThan(epoch)
    expect(auth.username).toBeNull()
    expect(auth.csrfToken).toBeNull()
    expect(auth.loaded).toBe(false)
    expect(store.items).toEqual([])
    const blockedFetch = vi.fn()
    await expect(new ApiClient({ fetcher: blockedFetch }).listCases()).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
    expect(blockedFetch).not.toHaveBeenCalled()
    pendingCases.resolve(json({ items: ['old-patient'], next_cursor: null }))
    await rejected
    pendingSession.resolve(json({ username: 'bob', csrf_token: 'bob-csrf' }))
    await flushPromises()
    expect(auth.username).toBe('bob')
    expect(auth.loaded).toBe(true)
  })

  it('processes remote logout and failed checks without rebroadcasting', async () => {
    const write = vi.spyOn(Storage.prototype, 'setItem')
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
    notify()
    await flushPromises()
    expect(auth.username).toBeNull()
    expect(auth.loaded).toBe(true)
    expect(write.mock.calls.filter(call => call[0] === SESSION_SYNC_KEY)).toEqual([])
  })

  it('publishes only a nonce on local login/logout and ignores its own notification', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(json({ username: 'bob', csrf_token: 'secret-csrf' }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetcher)
    await login('bob', 'secret-password')
    const notice = localStorage.getItem(SESSION_SYNC_KEY)!
    expect(notice).toMatch(/^[a-f0-9-]{36}$/i)
    expect(notice).not.toContain('bob')
    const epoch = sessionEpoch.value
    notify(notice)
    expect(sessionEpoch.value).toBe(epoch)
    expect(fetcher).toHaveBeenCalledTimes(1)
    await logout()
    expect(localStorage.getItem(SESSION_SYNC_KEY)).not.toBe(notice)
  })

  it.each(['focus', 'pageshow'])('rechecks shared Cookie identity on window %s and coalesces route session reads', async event => {
    const pending = deferred<Response>()
    const fetcher = vi.fn(() => pending.promise)
    vi.stubGlobal('fetch', fetcher)
    if (event === 'focus') window.dispatchEvent(new Event('focus'))
    else window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))
    expect(auth.username).toBe('alice')
    expect(auth.loaded).toBe(true)
    expect(auth.verifying).toBe(true)
    const guardRead = loadSession()
    expect(fetcher).toHaveBeenCalledTimes(1)
    pending.resolve(json({ username: 'bob', csrf_token: 'bob-csrf' }))
    expect(await guardRead).toBe(true)
    expect(auth.username).toBe('bob')
  })

  it('does not interrupt pending login when focus or restored pageshow fires', async () => {
    const pending = deferred<Response>()
    const fetcher = vi.fn(() => pending.promise)
    vi.stubGlobal('fetch', fetcher)
    const signingIn = login('bob', 'password')
    window.dispatchEvent(new Event('focus'))
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))
    expect(fetcher).toHaveBeenCalledTimes(1)
    pending.resolve(json({ username: 'bob', csrf_token: 'bob-csrf' }))
    await signingIn
    expect(auth.username).toBe('bob')
  })


  it('preserves cached records and view preferences on unchanged-session focus', async () => {
    const pending = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(() => pending.promise))
    const store = useCaseStore()
    store.setPage([{ case_id: 'alice-case', patient_id: 'alice', status: 'CREATED', created_at: '', input_expires_at: null }], null)
    sessionStorage.setItem('epilocate:session-account', 'alice')
    sessionStorage.setItem('epilocate:fusion:result_1', '{"scale":64}')
    const epoch = sessionEpoch.value
    window.dispatchEvent(new Event('focus'))
    expect(auth.verifying).toBe(true)
    expect(sessionEpoch.value).toBe(epoch)
    expect(store.items[0]?.case_id).toBe('alice-case')
    pending.resolve(json({ username: 'alice', csrf_token: 'alice-csrf' }))
    await flushPromises()
    expect(auth.verifying).toBe(false)
    expect(sessionEpoch.value).toBe(epoch)
    expect(store.items[0]?.case_id).toBe('alice-case')
    expect(sessionStorage.getItem('epilocate:fusion:result_1')).toBe('{"scale":64}')
  })

  it.each(['same', 'different', 'new-cookie'])('holds an in-flight business response until the %s session is verified', async identity => {
    const pendingSession = deferred<Response>(), pendingCases = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(() => pendingSession.promise))
    const apiFetch = vi.fn(() => pendingCases.promise)
    const request = new ApiClient({ fetcher: apiFetch }).listCases()
    let settled = false
    const outcome = request.then(value => { settled = true; return value }, error => { settled = true; return error })
    await flushPromises()
    window.dispatchEvent(new Event('focus'))
    pendingCases.resolve(new Response('{"items":[],"next_cursor":null}', { headers: { 'Content-Type': 'application/json' } }))
    await flushPromises()
    expect(settled).toBe(false)
    pendingSession.resolve(json({ username: identity === 'different' ? 'bob' : 'alice',
      csrf_token: identity === 'same' ? 'alice-csrf' : 'new-csrf' }))
    const value = await outcome
    if (identity === 'same') expect(value).toEqual({ items: [], next_cursor: null })
    else expect(value).toMatchObject({ code: 'SESSION_CHANGED' })
    expect(apiFetch).toHaveBeenCalledTimes(1)
  })

  it.each(['same', 'different', 'cancelled'])('defers a new request during focus validation: %s', async outcome => {
    const pending = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(() => pending.promise))
    const fetcher = vi.fn(async () => new Response('{"items":[],"next_cursor":null}', { headers: { 'Content-Type': 'application/json' } }))
    const abort = new AbortController()
    window.dispatchEvent(new Event('focus'))
    const request = new ApiClient({ fetcher }).listCases(undefined, 30, abort.signal)
    const result = request.catch(error => error)
    await flushPromises()
    expect(fetcher).not.toHaveBeenCalled()
    if (outcome === 'cancelled') abort.abort()
    pending.resolve(json({ username: outcome === 'different' ? 'bob' : 'alice',
      csrf_token: outcome === 'different' ? 'bob-csrf' : 'alice-csrf' }))
    const value = await result
    if (outcome === 'same') {
      expect(value).toEqual({ items: [], next_cursor: null })
      expect(fetcher).toHaveBeenCalledTimes(1)
    } else {
      expect(fetcher).not.toHaveBeenCalled()
      expect(value).toMatchObject(outcome === 'cancelled' ? { name: 'AbortError' } : { code: 'SESSION_CHANGED' })
    }
  })

  it.each([401, 503])('clears state if a passive check fails with %s', async status => {
    const epoch = sessionEpoch.value
    vi.stubGlobal('fetch', vi.fn(async () => json({ code: 'UNAUTHENTICATED' }, status)))
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(auth.username).toBeNull()
    expect(auth.verifying).toBe(false)
    expect(auth.loaded).toBe(true)
    expect(sessionEpoch.value).toBeGreaterThan(epoch)
  })

  it('bounds a stalled passive check and clears the old session on timeout', async () => {
    const timeout = new AbortController()
    vi.spyOn(AbortSignal, 'timeout').mockReturnValue(timeout.signal)
    const fetcher = vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init.signal!.addEventListener('abort', () => reject(init.signal!.reason), { once: true })
    }))
    vi.stubGlobal('fetch', fetcher)
    window.dispatchEvent(new Event('focus'))
    expect(auth.verifying).toBe(true)
    expect(AbortSignal.timeout).toHaveBeenCalledWith(15000)
    timeout.abort(new DOMException('timeout', 'TimeoutError'))
    await flushPromises()
    expect(auth.username).toBeNull()
    expect(auth.verifying).toBe(false)
    expect(auth.error).toContain('无法连接')
  })

  it('keeps immediate remote invalidation authoritative over an older passive check', async () => {
    const older = deferred<Response>(), newer = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise))
    window.dispatchEvent(new Event('focus'))
    notify()
    expect(auth.username).toBeNull()
    expect(auth.loaded).toBe(false)
    newer.resolve(json({ username: 'bob', csrf_token: 'bob-csrf' }))
    await flushPromises()
    older.resolve(json({ username: 'alice', csrf_token: 'alice-csrf' }))
    await flushPromises()
    expect(auth.username).toBe('bob')
    expect(auth.csrfToken).toBe('bob-csrf')
    expect(auth.verifying).toBe(false)
  })

  it('discards an older session-check response after a newer remote notification', async () => {
    const older = deferred<Response>(), newer = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise))
    notify()
    notify('22345678-abcd-1234-abcd-123456789012')
    newer.resolve(json({ username: 'bob', csrf_token: 'new-csrf' }))
    await flushPromises()
    older.resolve(json({ username: 'alice', csrf_token: 'old-csrf' }))
    await flushPromises()
    expect(auth.username).toBe('bob')
    expect(auth.csrfToken).toBe('new-csrf')
  })
})
