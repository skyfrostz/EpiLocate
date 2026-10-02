import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { apiClient, ApiRequestError } from '../api/client'
import { sessionEpoch } from '../auth/lifecycle'
import type { CaseDetail, ResultRecord } from '../api/types'
import ResultDetailView from '../views/ResultDetailView.vue'
import { AUDITED_GEOMETRY } from '../viewer/geometry'

const result: ResultRecord = {
  result_id: 'result_test', case_id: 'case_test', slice_id: 'slice_test', job_id: 'job_test',
  kind: 'PREDICTION', contract_version: '2.0', source: 'LIVE_CASE', status: 'COMPLETED',
  model_id: 'baseline_resnet18', model_version: 'test', preprocessing_version: 'test', protocol_id: 'test',
  prediction: null, scale_summaries: [], cross_scale: [], assets: [], provenance: { input_sha256: 'AB'.repeat(32) }, created_at: '2026-10-01T00:00:00Z',
}
const detail: CaseDetail = { case_id: 'case_test', patient_id: 'test', status: 'READY', created_at: '2026-10-01T00:00:00Z', input_expires_at: null,
  studies: [{ study_id: 'study_test', series: [{ series_id: 'series_test', slices: [{ slice_id: 'slice_test', ordinal: 0, width_px: 112, height_px: 80 }] }] }] }
const blob = () => Object.assign(new Blob(['dicom']), { arrayBuffer: async () => new ArrayBuffer(1) })
function prepareOcclusion() {
  const layer = { asset_id: 'response_test', layer_kind: 'CANDIDATE_RESPONSE' as const, width: 224, height: 224,
    coordinate_space: 'ALGORITHM_224' as const, value_min: 0, value_max: 1, origin: 'TOP_LEFT_PIXEL_EDGE' as const,
    x_axis: 'RIGHT' as const, y_axis: 'DOWN' as const, display_interpolation_only: true }
  vi.mocked(apiClient.getResult).mockResolvedValue({ ...result, kind: 'OCCLUSION',
    model_id: AUDITED_GEOMETRY.modelId, model_version: AUDITED_GEOMETRY.modelVersion,
    preprocessing_version: AUDITED_GEOMETRY.preprocessingVersion, protocol_id: AUDITED_GEOMETRY.protocolId,
    scale_summaries: [{ block_size: 16, stride: 8, fill: 0.5, baseline_positive_probability: 0.1,
      median_absolute_probability_change: 0.02, flip_rate: 0, candidate_status: 'valid', candidate_area_fraction: 0.1,
      response_layer: layer, candidate_layer: null, comparison_grid_layer: null }],
    assets: [{ ...layer, media_type: 'image/png' }],
  })
  vi.spyOn(apiClient, 'getResultAsset').mockResolvedValue(new Blob(['synthetic-png'], { type: 'image/png' }))
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL() { return 'blob:synthetic-response' }
    static revokeObjectURL() { /* Synthetic asset has no native URL to release. */ }
  })
}
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
  it.each([
    { status: 410, code: 'INPUT_EXPIRED', state: 'expired', message: '原始影像已到期' },
    { status: 0, code: 'NETWORK_UNAVAILABLE', state: 'error', message: '无法连接服务' },
  ])('prioritizes CT $state over absent-case geometry diagnostics and keeps the independent layer', async ({ status, code, state, message }) => {
    prepareOcclusion()
    vi.spyOn(apiClient, 'getCaseDicom').mockRejectedValue(new ApiRequestError(status, code, 'unsafe-details', false, null))
    const wrapper = await mountResult()
    expect(wrapper.find('[data-viewer]').attributes('data-state')).toBe(state)
    expect(wrapper.text()).toContain(message)
    expect(wrapper.text()).not.toContain('病例与结果不一致')
    expect(wrapper.find('.fusion-controls input[type="checkbox"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.heatmap-frame img').attributes('src')).toBe('blob:synthetic-response')
  })

  it('waits for CT readiness before showing a real case mismatch', async () => {
    prepareOcclusion()
    let resolve!: (value: Blob) => void
    vi.spyOn(apiClient, 'getCaseDicom').mockReturnValue(new Promise<Blob>(done => { resolve = done }))
    vi.mocked(apiClient.getCase).mockResolvedValue({ ...detail, case_id: 'different_case' })
    const wrapper = await mountResult()
    expect(wrapper.find('[data-viewer]').attributes('data-state')).toBe('loading')
    expect(wrapper.text()).not.toContain('病例与结果不一致')
    resolve(blob()); await flushPromises()
    expect(wrapper.find('[data-viewer]').attributes('data-state')).toBe('ready')
    expect(wrapper.text()).toContain('病例与结果不一致')
    expect(wrapper.find('.fusion-controls input[type="checkbox"]').attributes('disabled')).toBeDefined()
  })

  it('restores the geometry status after an expired input is successfully reread', async () => {
    prepareOcclusion()
    vi.spyOn(apiClient, 'getCaseDicom')
      .mockRejectedValueOnce(new ApiRequestError(410, 'INPUT_EXPIRED', 'unsafe-details', false, null))
      .mockResolvedValueOnce(blob())
    const wrapper = await mountResult()
    expect(wrapper.text()).not.toContain('病例与结果不一致')
    await wrapper.findAll('button').find(button => button.text() === '重新读取')!.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-viewer]').attributes('data-state')).toBe('ready')
    expect(wrapper.text()).toContain('像素契约匹配')
    expect(wrapper.text()).not.toContain('原始影像已到期')
    expect(wrapper.text()).not.toContain('病例与结果不一致')
  })

  it('explains that a classification result has no overlay rather than implying failure', async () => {
    vi.spyOn(apiClient, 'getCaseDicom').mockResolvedValue(blob())
    const wrapper = await mountResult()
    expect(wrapper.text()).toContain('分类任务 · 无叠加图层')
    expect(wrapper.text()).not.toContain('叠加尚不可用')
    expect(wrapper.find('.scale-switch').exists()).toBe(false)
  })

  it('reports selected scales accessibly and keeps absent model layers disabled', async () => {
    vi.spyOn(apiClient, 'getCaseDicom').mockResolvedValue(blob())
    vi.mocked(apiClient.getResult).mockResolvedValue({ ...result, kind: 'OCCLUSION', scale_summaries: [16, 32, 64].map(scale => ({
      block_size: scale as 16 | 32 | 64, stride: scale / 2 as 8 | 16 | 32, fill: 0.5,
      baseline_positive_probability: 0.1, median_absolute_probability_change: 0, flip_rate: 0,
      candidate_status: 'insufficient_positive_response' as const, candidate_area_fraction: null,
      response_layer: null, candidate_layer: null, comparison_grid_layer: null,
    })) })
    const wrapper = await mountResult()
    for (const index of [1, 2, 0, 2]) {
      await wrapper.findAll('.scale-switch button')[index]!.trigger('click'); await flushPromises()
      expect(wrapper.findAll('.scale-switch button').filter(button => button.attributes('aria-pressed') === 'true')).toHaveLength(1)
      expect(wrapper.findAll('.scale-switch button')[index]!.attributes('aria-pressed')).toBe('true')
      expect(wrapper.findAll('.layer-switch button').every(button => button.attributes('disabled') !== undefined)).toBe(true)
      expect(wrapper.text()).toContain('当前尺度或图层未提供图层资产')
    }
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
