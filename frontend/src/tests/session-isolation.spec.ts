import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia, disposePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { ApiClient } from '../api/client'
import { auth, clearSession, loadSession, login, logout } from '../auth/session'
import { useCaseStore } from '../stores/cases'
import { useJobStore } from '../stores/jobs'
import { useResultStore } from '../stores/results'
import type { CaseDetail, JobRecord, ResultRecord } from '../api/types'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
})
const detail: CaseDetail = { case_id: 'alice-case', patient_id: 'alice', status: 'READY',
  created_at: '2026-10-01T00:00:00Z', input_expires_at: null, studies: [] }
const job: JobRecord = { job_id: 'alice-job', case_id: detail.case_id, kind: 'PREDICTION', status: 'RUNNING',
  attempt_no: 0, retry_count: 0, lease_expire_time: null, last_heartbeat: null, failure_reason: null,
  progress: null, estimated_remaining_time_ms: null, result_id: null, error: null,
  created_at: detail.created_at, finished_at: null }
const result: ResultRecord = { result_id: 'alice-result', job_id: job.job_id, case_id: detail.case_id,
  slice_id: 'alice-slice', kind: 'PREDICTION', contract_version: '2.0', source: 'LIVE_CASE', status: 'COMPLETED',
  model_id: 'baseline', model_version: '1', preprocessing_version: '1', protocol_id: '1',
  prediction: null, scale_summaries: [], cross_scale: [], assets: [], provenance: {}, created_at: detail.created_at }
let pinia: ReturnType<typeof createPinia>
beforeEach(() => {
  clearSession()
  sessionStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  auth.username = 'alice'
  auth.csrfToken = 'alice-csrf'
  auth.loaded = true
  vi.stubGlobal('URL', class extends URL {
    static revokeObjectURL = vi.fn()
    static createObjectURL = vi.fn(() => 'blob:alice-image')
  })
})
afterEach(() => { disposePinia(pinia); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('identity boundaries across browser data and outstanding requests', () => {
  it.each(['logout', 'account change'])('%s clears caches, releases the image and aborts polling', async reason => {
    vi.useFakeTimers()
    const cases = useCaseStore(), jobs = useJobStore(), results = useResultStore()
    cases.setPage([detail], 'alice-next')
    cases.select(detail)
    jobs.upsert(job)
    results.current = result
    results.assetUrl = 'blob:alice-image'
    const pending = deferred<JobRecord>()
    const getJob = vi.fn((_id: string, _signal?: AbortSignal) => pending.promise)
    jobs.startPolling(job.job_id, { getJob } as unknown as ApiClient, { intervalMs: 100 })
    if (reason === 'logout') clearSession()
    else {
      vi.stubGlobal('fetch', vi.fn(async () => json({ username: 'bob', csrf_token: 'bob-csrf' })))
      await login('bob', 'password')
    }
    expect(cases.items).toEqual([])
    expect(cases.selected).toBeNull()
    expect(cases.nextCursor).toBeNull()
    expect(cases.hasLoaded).toBe(false)
    expect(jobs.byId).toEqual({})
    expect(jobs.currentId).toBeNull()
    expect(jobs.isPolling).toBe(false)
    expect(getJob.mock.calls[0]![1]!.aborted).toBe(true)
    expect(results.current).toBeNull()
    expect(results.assetUrl).toBeNull()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:alice-image')
    pending.resolve(job)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(500)
    expect(getJob).toHaveBeenCalledTimes(1)
    expect(jobs.byId).toEqual({})
  })

  it.each([200, 401])('rejects an old %s response without clearing the new account', async status => {
    const pending = deferred<Response>()
    const client = new ApiClient({ fetcher: vi.fn(() => pending.promise) as typeof fetch })
    const request = client.listCases()
    const rejected = expect(request).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
    clearSession()
    vi.stubGlobal('fetch', vi.fn(async () => json({ username: 'bob', csrf_token: 'bob-csrf' })))
    await login('bob', 'password')
    pending.resolve(json(status === 200 ? { items: [detail], next_cursor: null } : { code: 'UNAUTHENTICATED' }, status))
    await rejected
    expect(auth.username).toBe('bob')
    expect(auth.error).toBeNull()
  })

  it('does not apply an old 401 when identity changes between response receipt and validation', async () => {
    const pending = deferred<Response>()
    const client = new ApiClient({ fetcher: vi.fn(() => pending.promise) as typeof fetch })
    const request = client.listCases()
    const rejected = expect(request).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
    pending.resolve(json({ code: 'UNAUTHENTICATED' }, 401))
    // send() resumes first; request() resumes after this queued identity change.
    queueMicrotask(() => {
      clearSession()
      auth.username = 'bob'
      auth.csrfToken = 'bob-csrf'
    })
    await rejected
    expect(auth.username).toBe('bob')
    expect(auth.csrfToken).toBe('bob-csrf')
    expect(auth.error).toBeNull()
  })

  it('does not let an older logout clear a newer login for the same username', async () => {
    const pending = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce(json({ username: 'alice', csrf_token: 'new-alice-csrf' })))
    const signingOut = logout()
    await login('alice', 'new-password')
    pending.resolve(new Response(null, { status: 204 }))
    await signingOut
    expect(auth.username).toBe('alice')
    expect(auth.csrfToken).toBe('new-alice-csrf')
  })

  it.each(['json', 'dicom', 'asset'])('rejects delayed %s body consumption after logout', async kind => {
    const pending = deferred<unknown>()
    const response = json({})
    if (kind === 'json') vi.spyOn(response, 'json').mockImplementation(() => pending.promise)
    else {
      response.headers.set('content-type', kind === 'dicom' ? 'application/dicom' : 'image/png')
      vi.spyOn(response, 'blob').mockImplementation(() => pending.promise as Promise<Blob>)
    }
    const client = new ApiClient({ fetcher: vi.fn(async () => response) as typeof fetch })
    const request = kind === 'json' ? client.getCase('alice-case') : kind === 'dicom'
      ? client.getCaseDicom('alice-case') : client.getResultAsset('alice-result', 'image')
    const rejected = expect(request).rejects.toMatchObject({ code: 'SESSION_CHANGED' })
    await flushPromises()
    clearSession()
    pending.resolve(kind === 'json' ? detail : new Blob(['old-image']))
    await rejected
  })

  it.each(['login', 'session'])('a pending %s response cannot resurrect logout', async operation => {
    const pending = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(() => pending.promise))
    const request = operation === 'login' ? login('alice', 'password') : loadSession(true)
    const rejected = operation === 'login' ? expect(request).rejects.toMatchObject({ code: 'SESSION_CHANGED' }) : null
    clearSession()
    pending.resolve(json({ username: 'alice', csrf_token: 'stale-csrf' }))
    if (rejected) await rejected
    else expect(await request).toBe(false)
    expect(auth.username).toBeNull()
    expect(auth.csrfToken).toBeNull()
  })

  it('store requests that ignore abort cannot repopulate cleared case or result data', async () => {
    const cases = useCaseStore(), results = useResultStore()
    const caseRequest = deferred<CaseDetail>(), resultRequest = deferred<ResultRecord>()
    const client = { getCase: vi.fn(() => caseRequest.promise), getResult: vi.fn(() => resultRequest.promise) } as unknown as ApiClient
    const requests = [cases.loadCase(detail.case_id, client), results.loadResult(result.result_id, client)]
    clearSession()
    caseRequest.resolve(detail)
    resultRequest.resolve(result)
    await Promise.all(requests)
    expect(cases.selected).toBeNull()
    expect(results.current).toBeNull()
    expect(cases.detailLoading).toBe(false)
    expect(results.loading).toBe(false)
  })
})
