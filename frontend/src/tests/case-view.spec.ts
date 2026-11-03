import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { apiClient, ApiRequestError } from '../api/client'
import { auth, clearSession } from '../auth/session'
import { invalidateSessionData } from '../auth/lifecycle'
import { useCaseStore } from '../stores/cases'
import type { AcceptedJob, CaseDetail, UploadedCase } from '../api/types'
import CaseDetailView from '../views/CaseDetailView.vue'

vi.mock('../viewer/CornerstoneSliceViewer.vue', () => ({ default: {
  props: ['file', 'inputState', 'inputMessage'],
  template: '<div data-viewer :data-state="inputState" :data-file="file?.name" />',
} }))
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (reason: unknown) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}
function detail(id: string, ready = true): CaseDetail {
  return { case_id: id, patient_id: 'test', status: ready ? 'READY' : 'CREATED',
    created_at: '2026-10-01T00:00:00Z', input_expires_at: null,
    studies: ready ? [{ study_id: 'study', series: [{ series_id: 'series', slices: [{ slice_id: `slice-${id}`, ordinal: 0, width_px: 112, height_px: 80 }] }] }] : [] }
}
const wrappers: ReturnType<typeof mount>[] = []
const piniaInstances: ReturnType<typeof createPinia>[] = []
async function mountCase() {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/cases/:id', component: CaseDetailView }, { path: '/jobs/:id', component: { template: '<p>job</p>' } },
    { path: '/cases', component: { template: '<p>cases</p>' } },
  ] })
  await router.push('/cases/A')
  const pinia = createPinia()
  piniaInstances.push(pinia)
  const wrapper = mount(CaseDetailView, { global: { plugins: [pinia, router], stubs: {
    'a-button': { props: ['disabled', 'loading'], template: '<button :disabled="disabled || loading"><slot /></button>' },
    'a-tag': { template: '<span><slot /></span>' },
  } } })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}
function button(wrapper: ReturnType<typeof mount>, text: string) {
  return wrapper.findAll('button').find(item => item.text().includes(text))!
}
beforeEach(() => {
  clearSession()
  auth.username = 'alice'; auth.csrfToken = 'csrf'; auth.loaded = true
  vi.spyOn(apiClient, 'getCase').mockImplementation(async id => detail(id))
  vi.spyOn(apiClient, 'getCaseDicom').mockResolvedValue(new Blob(['dicom']))
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  piniaInstances.splice(0).forEach(disposePinia)
  vi.restoreAllMocks()
})

describe('case navigation and uncertain POST outcomes', () => {
  it.each(['PREDICTION', 'OCCLUSION'] as const)('reopens the accepted %s after a route rejection without another POST', async kind => {
    const create = vi.spyOn(apiClient, kind === 'PREDICTION' ? 'createPrediction' : 'createOcclusion')
      .mockResolvedValue({ case_id: 'A', job_id: 'accepted-job', status: 'CREATED', status_url: '/jobs/accepted-job' })
    const { wrapper, router } = await mountCase()
    const navigate = vi.spyOn(router, 'push').mockRejectedValueOnce(new Error('Chunk unavailable')).mockResolvedValueOnce(undefined)
    const label = kind === 'PREDICTION' ? 'Baseline' : '遮挡'
    await button(wrapper, label).trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('重试会打开同一任务')
    expect(wrapper.find('a[href="/jobs/accepted-job"]').text()).toContain('打开已创建任务')
    await button(wrapper, label).trigger('click'); await flushPromises()
    expect(create).toHaveBeenCalledTimes(1)
    expect(navigate.mock.calls.map(call => call[0])).toEqual(['/jobs/accepted-job', '/jobs/accepted-job'])
  })

  it('retains the accepted Job when a navigation guard aborts', async () => {
    const create = vi.spyOn(apiClient, 'createPrediction').mockResolvedValue({ case_id: 'A', job_id: 'accepted-job', status: 'CREATED', status_url: '/jobs/accepted-job' })
    const { wrapper, router } = await mountCase()
    const removeGuard = router.beforeEach(to => to.path.startsWith('/jobs/') ? false : true)
    await button(wrapper, 'Baseline').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('重试会打开同一任务')
    removeGuard()
    await button(wrapper, 'Baseline').trigger('click'); await flushPromises()
    expect(create).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.path).toBe('/jobs/accepted-job')
  })

  it('does not offer another action’s accepted Job after a rejected submission', async () => {
    vi.spyOn(apiClient, 'createPrediction').mockResolvedValue({ case_id: 'A', job_id: 'accepted-job', status: 'CREATED', status_url: '/jobs/accepted-job' })
    vi.spyOn(apiClient, 'createOcclusion').mockRejectedValue(new ApiRequestError(503, 'BACKEND_UNAVAILABLE', '服务暂时不可用', true, null))
    const { wrapper, router } = await mountCase()
    vi.spyOn(router, 'push').mockRejectedValue(new Error('Chunk unavailable'))
    await button(wrapper, 'Baseline').trigger('click'); await flushPromises()
    expect(wrapper.find('a[href="/jobs/accepted-job"]').exists()).toBe(true)
    await button(wrapper, '遮挡').trigger('click'); await flushPromises()
    expect(wrapper.find('a[href="/jobs/accepted-job"]').exists()).toBe(false)
  })

  it('clears an accepted Job recovery target on account invalidation', async () => {
    const create = vi.spyOn(apiClient, 'createPrediction')
      .mockResolvedValueOnce({ case_id: 'A', job_id: 'alice-job', status: 'CREATED', status_url: '/jobs/alice-job' })
      .mockResolvedValueOnce({ case_id: 'A', job_id: 'bob-job', status: 'CREATED', status_url: '/jobs/bob-job' })
    const { wrapper, router } = await mountCase()
    const navigate = vi.spyOn(router, 'push').mockRejectedValueOnce(new Error('Chunk unavailable')).mockResolvedValueOnce(undefined)
    await button(wrapper, 'Baseline').trigger('click'); await flushPromises()
    clearSession(false); auth.username = 'bob'; auth.loaded = true
    invalidateSessionData()
    await flushPromises()
    await useCaseStore(piniaInstances.at(-1)).loadCase('A')
    await flushPromises()
    await button(wrapper, 'Baseline').trigger('click'); await flushPromises()
    expect(create).toHaveBeenCalledTimes(2)
    expect(navigate.mock.calls.map(call => call[0])).toEqual(['/jobs/alice-job', '/jobs/bob-job'])
    expect(create.mock.calls[0]![3]).not.toBe(create.mock.calls[1]![3])
  })

  it('aborts A input and ignores its late response after switching to B', async () => {
    const a = deferred<Blob>(), b = deferred<Blob>()
    const getDicom = vi.mocked(apiClient.getCaseDicom).mockImplementation(id => id === 'A' ? a.promise : b.promise)
    const { wrapper, router } = await mountCase()
    const signal = getDicom.mock.calls[0]![1]!
    await router.push('/cases/B')
    await flushPromises()
    expect(signal.aborted).toBe(true)
    a.resolve(new Blob(['old-A']))
    await flushPromises()
    expect(wrapper.find('[data-viewer]').attributes('data-state')).toBe('loading')
    expect(wrapper.find('[data-viewer]').attributes('data-file')).toBeUndefined()
    b.resolve(new Blob(['current-B']))
    await flushPromises()
    expect(wrapper.find('[data-viewer]').attributes('data-state')).toBe('ready')
    expect(wrapper.text()).toContain('slice-B')
  })

  it.each(['success', 'failure'])('ignores a late job %s after navigating to another case', async outcome => {
    const pending = deferred<AcceptedJob>()
    const create = vi.spyOn(apiClient, 'createPrediction').mockReturnValue(pending.promise)
    const { wrapper, router } = await mountCase()
    await button(wrapper, 'Baseline').trigger('click')
    await router.push('/cases/B')
    await flushPromises()
    expect(create.mock.calls[0]![4]!.aborted).toBe(true)
    if (outcome === 'success') pending.resolve({ case_id: 'A', job_id: 'old-job', status: 'CREATED', status_url: '/jobs/old-job' })
    else pending.reject(new Error('old-case-job-error'))
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/cases/B')
    expect(wrapper.text()).not.toContain('old-case-job-error')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('reuses a job key after an uncertain network response and rotates it after success', async () => {
    const create = vi.spyOn(apiClient, 'createPrediction')
      .mockRejectedValueOnce(new ApiRequestError(0, 'NETWORK_UNAVAILABLE', '网络中断', true, null))
      .mockResolvedValue({ case_id: 'A', job_id: 'job-1', status: 'CREATED', status_url: '/jobs/job-1' })
    const { wrapper, router } = await mountCase()
    // Keep the same view active to simulate a deliberate second job after acceptance.
    vi.spyOn(router, 'push').mockResolvedValue(undefined)
    await button(wrapper, 'Baseline').trigger('click'); await flushPromises()
    await button(wrapper, 'Baseline').trigger('click'); await flushPromises()
    await button(wrapper, 'Baseline').trigger('click'); await flushPromises()
    expect(create).toHaveBeenCalledTimes(3)
    const keys = create.mock.calls.map(call => call[3])
    expect(keys[0]).toBe(keys[1])
    expect(keys[2]).not.toBe(keys[1])
  })

  it.each(['success', 'failure'])('ignores a late upload %s after leaving the view', async outcome => {
    vi.mocked(apiClient.getCase).mockImplementation(async id => detail(id, false))
    const pending = deferred<UploadedCase>()
    const upload = vi.spyOn(apiClient, 'uploadCase').mockReturnValue(pending.promise)
    const { wrapper } = await mountCase()
    const input = wrapper.find('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [new File(['dicom'], 'slice.dcm')] })
    await input.trigger('change')
    await button(wrapper, '上传 DICOM').trigger('click')
    wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
    const detailsBeforeResponse = vi.mocked(apiClient.getCase).mock.calls.length
    expect(upload.mock.calls[0]![3]!.aborted).toBe(true)
    if (outcome === 'success') pending.resolve({ case_id: 'A', study_id: 'study', series_id: 'series', slice_id: 'slice-A', status: 'READY', input_expires_at: '2026-10-02T00:00:00Z' })
    else pending.reject(new Error('old-upload-error'))
    await flushPromises()
    expect(apiClient.getCase).toHaveBeenCalledTimes(detailsBeforeResponse)
  })

  it('reuses the upload key when retrying an unchanged file after a network failure', async () => {
    vi.mocked(apiClient.getCase).mockImplementation(async id => detail(id, false))
    const upload = vi.spyOn(apiClient, 'uploadCase').mockRejectedValue(new ApiRequestError(0, 'NETWORK_UNAVAILABLE', '网络中断', true, null))
    const { wrapper } = await mountCase()
    const input = wrapper.find('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [new File(['dicom'], 'slice.dcm')] })
    await input.trigger('change')
    await button(wrapper, '上传 DICOM').trigger('click'); await flushPromises()
    await button(wrapper, '上传 DICOM').trigger('click'); await flushPromises()
    expect(upload).toHaveBeenCalledTimes(2)
    expect(upload.mock.calls[0]![2]).toBe(upload.mock.calls[1]![2])
  })
})
