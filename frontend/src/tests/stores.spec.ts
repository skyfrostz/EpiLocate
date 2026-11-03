import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useCaseStore } from '../stores/cases'
import { useJobStore } from '../stores/jobs'
import type { CaseSummary, JobRecord } from '../api/types'

const caseRecord: CaseSummary = {
  case_id: 'case_test', patient_id: 'pat_test', status: 'READY',
  created_at: '2026-09-26T00:00:00Z', input_expires_at: '2026-10-03T00:00:00Z',
}
const jobRecord: JobRecord = {
  job_id: 'job_test', kind: 'PREDICTION', case_id: 'case_test', status: 'QUEUED',
  attempt_no: 0, retry_count: 0, lease_expire_time: null, last_heartbeat: null,
  failure_reason: null, progress: null, estimated_remaining_time_ms: null,
  result_id: null, error: null, created_at: '2026-09-26T00:00:00Z', finished_at: null,
}

beforeEach(() => setActivePinia(createPinia()))

describe('Phase 1 Pinia state', () => {
  it('distinguishes not loaded from an empty Case list', () => {
    const store = useCaseStore()
    expect(store.hasLoaded).toBe(false)
    store.setPage([], null)
    expect(store.hasLoaded).toBe(true)
    expect(store.items).toEqual([])
    store.reset()
    expect(store.hasLoaded).toBe(false)
  })

  it('keeps only API-shaped Case and Job records', () => {
    const cases = useCaseStore()
    const jobs = useJobStore()
    cases.setPage([caseRecord], 'next-page')
    jobs.upsert(jobRecord)
    expect(cases.items[0]?.case_id).toBe('case_test')
    expect(cases.nextCursor).toBe('next-page')
    expect(jobs.byId.job_test?.status).toBe('QUEUED')
    jobs.clear()
    expect(jobs.byId).toEqual({})
  })
})
