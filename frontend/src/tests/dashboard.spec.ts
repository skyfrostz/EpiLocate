import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import { apiClient } from '../api/client'
import { ApiRequestError } from '../api/errors'
import { auth, clearSession } from '../auth/session'
import type { CaseListResponse } from '../api/types'

const response: CaseListResponse = { items: [
  { case_id: 'case_first', patient_id: 'anonymous', status: 'READY', created_at: '2026-09-01T00:00:00Z', input_expires_at: null },
  { case_id: 'case_second', patient_id: 'anonymous', status: 'EXPIRED', created_at: '2026-10-01T00:00:00Z', input_expires_at: null },
], next_cursor: 'more' }
beforeEach(() => { auth.username = 'test'; auth.loaded = true })
afterEach(() => { vi.restoreAllMocks() })
async function render() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: DashboardView }, { path: '/cases/:id?', component: { template: '<div />' } }] })
  await router.push('/')
  const wrapper = mount(DashboardView, { global: { plugins: [router], stubs: {
    'a-button': { template: '<button><slot /></button>' }, 'a-tag': { template: '<span><slot /></span>' },
  } } })
  return wrapper
}
describe('Dashboard real Case API page', () => {
  it('loads one page without sorting or inventing total statistics', async () => {
    const read = vi.spyOn(apiClient, 'listCases').mockResolvedValue(response)
    const wrapper = await render()
    await flushPromises()
    expect(read).toHaveBeenCalledWith(undefined, 6, expect.any(AbortSignal))
    expect(wrapper.findAll('.case-link').map(link => link.text())).toEqual(['case_first', 'case_second'])
    expect(wrapper.text()).toContain('输入可用')
    expect(wrapper.text()).toContain('输入已到期')
    expect(wrapper.text()).toContain('还有更多病例')
    expect(wrapper.text()).not.toContain('总病例')
    wrapper.unmount()
  })
  it('distinguishes initial loading, empty response and failed refresh while retaining known data', async () => {
    let resolve!: (value: CaseListResponse) => void
    vi.spyOn(apiClient, 'listCases').mockImplementationOnce(() => new Promise(done => { resolve = done }))
      .mockResolvedValueOnce(response).mockRejectedValueOnce(new ApiRequestError(503, 'BACKEND_UNAVAILABLE', 'unsafe', true, null))
    const wrapper = await render()
    expect(wrapper.text()).toContain('正在读取病例')
    resolve({ items: [], next_cursor: null })
    await flushPromises()
    expect(wrapper.text()).toContain('暂无病例')
    const refresh = () => wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click')
    await refresh(); await flushPromises()
    expect(wrapper.text()).toContain('case_first')
    await refresh(); await flushPromises()
    expect(wrapper.text()).toContain('服务暂时不可用')
    expect(wrapper.text()).toContain('case_first')
    wrapper.unmount()
  })
  it('clears dashboard data on session invalidation and ignores stale response', async () => {
    let resolve!: (value: CaseListResponse) => void
    vi.spyOn(apiClient, 'listCases').mockImplementationOnce(() => new Promise(done => { resolve = done }))
    const wrapper = await render()
    clearSession(false)
    resolve(response)
    await flushPromises()
    expect(wrapper.text()).not.toContain('case_first')
    wrapper.unmount()
  })
})
