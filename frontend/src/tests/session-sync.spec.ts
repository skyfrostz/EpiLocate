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
    expect(auth.username).toBeNull()
    expect(auth.loaded).toBe(false)
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
