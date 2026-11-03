import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useJobStore } from '../stores/jobs'
import type { JobRecord } from '../api/types'
import { auth } from '../auth/session'
import JobDetailView from '../views/JobDetailView.vue'

const record = (status: JobRecord['status'], code?: string): JobRecord => ({
  job_id: 'job_test', case_id: 'case_test', kind: 'OCCLUSION', status,
  error: code ? { code, message: '/private/patient/secret' } : null,
  failure_reason: '/private/path', progress: null, estimated_remaining_time_ms: null,
  result_id: null, attempt_no: 1, retry_count: 0, lease_expire_time: null,
  last_heartbeat: null, created_at: '2026-10-01T00:00:00Z', finished_at: null,
})

beforeEach(() => { setActivePinia(createPinia()); auth.username = 'test-user'; auth.loaded = true })
afterEach(() => { vi.restoreAllMocks() })

async function render(job: JobRecord) {
  const store = useJobStore()
  store.upsert(job)
  const poll = vi.spyOn(store, 'startPolling').mockImplementation(() => {})
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/jobs/:id', component: JobDetailView },
    { path: '/cases/:id?', component: { template: '<div />' } },
  ] })
  await router.push('/jobs/job_test')
  await router.isReady()
  const wrapper = mount(JobDetailView, { global: { plugins: [router], stubs: {
    'a-button': { template: '<button><slot /></button>' }, 'a-tag': { template: '<span><slot /></span>' },
  } } })
  return { store, poll, wrapper }
}

describe('Job detail recovery and terminal failures', () => {
  it('renders Chinese states and preserves last known state during transport timeout with manual requery', async () => {
    const { store, poll, wrapper } = await render(record('RUNNING'))
    store.error = '等待任务超时。任务可能仍在服务端运行，请稍后重新查询。'
    store.timedOut = true
    await flushPromises()
    expect(wrapper.text()).toContain('运行中')
    expect(wrapper.text()).toContain('保留下方最近一次')
    expect(wrapper.text()).toContain('服务端未提供')
    expect(wrapper.find('.notice-error h3').exists()).toBe(false)
    await wrapper.get('button').trigger('click')
    expect(poll).toHaveBeenLastCalledWith('job_test')
    wrapper.unmount()
  })

  it('places expired FAILED Job outside the successful track and links to new Case', async () => {
    const { wrapper } = await render(record('FAILED', 'INPUT_EXPIRED'))
    expect(wrapper.find('.status-track').exists()).toBe(false)
    expect(wrapper.text()).toContain('原始影像已到期')
    expect(wrapper.findAll('a').some(a => a.text() === '新建病例' && a.attributes('href') === '/cases')).toBe(true)
    expect(wrapper.text()).not.toContain('/private')
    wrapper.unmount()
  })

  it('provides support and explicit Case recovery for INFERENCE_FAILED without creating a new Job', async () => {
    const { poll, wrapper } = await render(record('FAILED', 'INFERENCE_FAILED'))
    expect(wrapper.text()).toContain('维护者')
    expect(wrapper.text()).toContain('job_test')
    expect(wrapper.text()).toContain('不会自动重试')
    expect(wrapper.findAll('a').some(a => a.text() === '返回病例页' && a.attributes('href') === '/cases/case_test')).toBe(true)
    expect(poll).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).not.toContain('/private')
    wrapper.unmount()
  })

  it('does not expose unknown failure messages or reasons', async () => {
    const { wrapper } = await render(record('FAILED', 'UNKNOWN_PRIVATE_FAILURE'))
    expect(wrapper.text()).toContain('确认原因')
    expect(wrapper.text()).not.toContain('UNKNOWN_PRIVATE_FAILURE')
    expect(wrapper.text()).not.toContain('secret')
    wrapper.unmount()
  })

  it('continues querying QUEUED even with a prior lease expiry and does not invent a failure', async () => {
    const { poll, wrapper } = await render(record('QUEUED', 'LEASE_EXPIRED'))
    expect(wrapper.text()).toContain('排队中')
    expect(wrapper.find('.notice-error h3').exists()).toBe(false)
    expect(poll).toHaveBeenCalledWith('job_test')
    wrapper.unmount()
  })
})
