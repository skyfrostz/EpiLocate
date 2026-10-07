import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { apiClient, ApiRequestError } from '../api/client'
import { sessionEpoch } from '../auth/lifecycle'
import type { CaseDetail, ResultRecord } from '../api/types'
import ResultDetailView from '../views/ResultDetailView.vue'

const result: ResultRecord = {
  result_id: 'result_test', case_id: 'case_test', slice_id: 'slice_test', job_id: 'job_test',
  kind: 'PREDICTION', contract_version: '2.0', source: 'LIVE_CASE', status: 'COMPLETED',
  model_id: 'baseline_resnet18', model_version: 'test', preprocessing_version: 'test', protocol_id: 'test',
  prediction: null, scale_summaries: [], cross_scale: [], assets: [], provenance: { input_sha256: 'AB'.repeat(32) }, created_at: '2026-10-01T00:00:00Z',
}
const detail: CaseDetail = { case_id: 'case_test', patient_id: 'test', status: 'READY', created_at: '2026-10-01T00:00:00Z', input_expires_at: null,
  studies: [{ study_id: 'study_test', series: [{ series_id: 'series_test', slices: [{ slice_id: 'slice_test', ordinal: 0, width_px: 112, height_px: 80 }] }] }] }
const blob = () => Object.assign(new Blob(['dicom']), { arrayBuffer: async () => new ArrayBuffer(1) })
const wrappers: ReturnType<typeof mount>[] = []
async function mountResult() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/results/:id', component: ResultDetailView }] })
  await router.push('/results/result_test')
  await router.isReady()
  const wrapper = mount(ResultDetailView, { global: { plugins: [createPinia(), router], stubs: {
    'a-button': { template: '<button><slot /></button>' }, 'a-tag': { template: '<span><slot /></span>' },
    CornerstoneSliceViewer: { props: ['file', 'inputState', 'inputMessage'], template: '<div data-viewer :data-state="inputState" :data-file="Boolean(file)" />' },
  } } })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}
beforeEach(() => {
  sessionStorage.clear()
  vi.spyOn(apiClient, 'getResult').mockResolvedValue(result)
  vi.spyOn(apiClient, 'getCase').mockResolvedValue(detail)
  vi.stubGlobal('crypto', { subtle: { digest: vi.fn(async () => new Uint8Array(32).fill(0xab).buffer) } })
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('result input recovery and session isolation', () => {
  it('shows an expired CT without premature geometry mismatch diagnostics', async () => {
    vi.mocked(apiClient.getResult).mockResolvedValue({ ...result, kind: 'OCCLUSION' })
    vi.spyOn(apiClient, 'getCaseDicom').mockRejectedValue(
      new ApiRequestError(410, 'INPUT_EXPIRED', '原始影像已到期', false, null),
    )
    const wrapper = await mountResult()
    expect(wrapper.find('[data-viewer]').attributes('data-state')).toBe('expired')
    expect(wrapper.text()).toContain('原始影像已到期')
    expect(wrapper.text()).not.toContain('模型或预处理版本尚无经过核验的几何映射')
  })

  it('accepts matching upper-case SHA-256 without weakening input verification', async () => {
    vi.spyOn(apiClient, 'getCaseDicom').mockResolvedValue(blob())
    const wrapper = await mountResult()
    expect(wrapper.find('[data-viewer]').attributes('data-state')).toBe('ready')
    expect(wrapper.find('[data-viewer]').attributes('data-file')).toBe('true')
    expect(wrapper.text()).not.toContain('SHA-256 与 Result')
  })

  it('aborts and rejects late DICOM after session invalidation', async () => {
    let resolve!: (value: Blob) => void
    const getDicom = vi.spyOn(apiClient, 'getCaseDicom').mockReturnValue(new Promise<Blob>(done => { resolve = done }))
    const wrapper = await mountResult()
    expect(wrapper.find('[data-viewer]').attributes('data-state')).toBe('loading')
    const signal = getDicom.mock.calls[0]![1]!
    sessionStorage.setItem('epilocate:fusion:other_result', 'previous-user-view')
    sessionEpoch.value++
    expect(signal.aborted).toBe(true)
    expect(sessionStorage.getItem('epilocate:fusion:other_result')).toBeNull()
    resolve(blob())
    await flushPromises()
    expect(wrapper.find('[data-viewer]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('CT 与模型图层')
  })
})
