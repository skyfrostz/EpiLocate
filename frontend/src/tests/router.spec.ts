import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { createAppRouter } from '../router'

describe('Phase 1 routes', () => {
  it.each([
    ['/', 'dashboard'],
    ['/cases', 'cases'],
    ['/cases/case_123', 'case-detail'],
    ['/jobs/job_123', 'job-detail'],
    ['/results/result_123', 'result-detail'],
  ])('resolves %s to %s', (path, name) => {
    const route = createAppRouter(createMemoryHistory()).resolve(path)
    expect(route.name).toBe(name)
  })

  it('keeps the ID from a deep link', () => {
    const route = createAppRouter(createMemoryHistory()).resolve('/jobs/job_abc')
    expect(route.params.id).toBe('job_abc')
  })
})
