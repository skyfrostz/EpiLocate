import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { apiClient } from '../api/client'
import type { ResultRecord, HeatmapLayer, ScaleSummary } from '../api/types'
import ResultDetailView from '../views/ResultDetailView.vue'
import { routes } from '../router'

// All values and pixel substitutes below are generated; no historical objects.
vi.mock('../demo-history', () => ({
  demoRows: [{ result_id: 'result_test', case_id: 'case_test', slice_id: 'slice_test', job_id: 'job_test', input_sha256: 'ab'.repeat(32) }],
  demoModel: { model_id: 'baseline_resnet18', checkpoint_sha256: 'test', preprocessing_version: 'test', protocol_id: 'test' },
}))
function summary(scale: 16 | 32 | 64): ScaleSummary {
  const layer = (name: string, kind: HeatmapLayer['layer_kind']): HeatmapLayer => ({ asset_id: `${name}-${scale}.png`, layer_kind: kind,
    coordinate_space: 'ALGORITHM_224', width: 224, height: 224, value_min: 0, value_max: 1,
    origin: 'TOP_LEFT_PIXEL_EDGE', x_axis: 'RIGHT', y_axis: 'DOWN', display_interpolation_only: true })
  return { block_size: scale, stride: 32, fill: 0.5, baseline_positive_probability: 0.7,
    median_absolute_probability_change: 0.1, flip_rate: 0, candidate_status: 'valid', candidate_area_fraction: 0.1,
    response_layer: layer('response', 'CANDIDATE_RESPONSE'), candidate_layer: layer('candidate', 'CANDIDATE_TOP10'),
    comparison_grid_layer: layer('comparison', 'COMPARISON_GRID') }
}
const scales = [summary(16), summary(32), summary(64)]
const result: ResultRecord = { result_id: 'result_test', case_id: 'case_test', slice_id: 'slice_test', job_id: 'job_test',
  kind: 'OCCLUSION', contract_version: '2.0', source: 'LIVE_CASE', status: 'COMPLETED',
  model_id: 'baseline_resnet18', model_version: 'test', preprocessing_version: 'test', protocol_id: 'test',
  prediction: { predicted_class: 1, class_label: 'must not use disease label', positive_probability: 0.7, predicted_class_confidence: 0.7, inference_time_ms: 1 },
  scale_summaries: scales, cross_scale: [], provenance: { input_sha256: 'ab'.repeat(32) }, created_at: '2026-10-01T00:00:00Z',
  assets: scales.flatMap(s => [s.response_layer!, s.candidate_layer!, s.comparison_grid_layer!].map(l => ({ ...l, media_type: 'image/png' }))),
}
const wrappers: ReturnType<typeof mount>[] = []
async function display(id = 'result_test') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/results/:id', component: ResultDetailView }] })
  await router.push(`/results/${id}`); await router.isReady()
  const wrapper = mount(ResultDetailView, { global: { plugins: [createPinia(), router], stubs: {
    'a-button': { template: '<button><slot /></button>' }, 'a-tag': { template: '<span><slot /></span>' },
    CornerstoneSliceViewer: { template: '<div data-viewer />' },
  } } }); wrappers.push(wrapper); await flushPromises(); return wrapper
}
beforeEach(() => {
  sessionStorage.clear()
  vi.spyOn(apiClient, 'getResult').mockResolvedValue(result)
  vi.spyOn(apiClient, 'getCase').mockRejectedValue(new Error('generated absent CT'))
  vi.spyOn(apiClient, 'getCaseDicom').mockRejectedValue(new Error('generated absent CT'))
  vi.spyOn(apiClient, 'getResultAsset').mockResolvedValue(new Blob(['generated']))
  vi.stubGlobal('URL', class extends URL { static createObjectURL() { return 'blob:generated' } static revokeObjectURL() {} })
})
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('ignores stale 16/32 preferences, exposes only64 and uses proxy labels', async () => {
  sessionStorage.setItem('epilocate:fusion:result_test', JSON.stringify({ scale: 16, layer: 'CANDIDATE_TOP10', visible: true, opacity: 1 }))
  const w = await display()
  expect(w.findAll('.scale-switch button').map(b => b.text())).toEqual(['64 px'])
  expect(vi.mocked(apiClient.getResultAsset).mock.calls.every(c => c[1].endsWith('-64.png'))).toBe(true)
  expect(w.text()).toContain('RICORD 1A（代理类 1）')
  expect(w.text()).not.toContain('must not use disease label')
  expect(w.findAll('a[href]').map(a => a.attributes('href')).some(h => /cases|jobs/.test(h!))).toBe(false)
  await w.findAll('.layer-switch button')[1]!.trigger('click'); await flushPromises()
  expect(vi.mocked(apiClient.getResultAsset).mock.lastCall?.[1]).toBe('candidate-64.png')
})

it('refuses an unbound direct result before reading CT or layers', async () => {
  vi.mocked(apiClient.getResult).mockResolvedValue({ ...result, result_id: 'other' })
  const w = await display('other')
  expect(w.text()).toContain('结果尚不可显示')
  expect(w.find('[data-viewer]').exists()).toBe(false)
  expect(apiClient.getCaseDicom).not.toHaveBeenCalled()
  expect(apiClient.getResultAsset).not.toHaveBeenCalled()
})

it('has no Series, 3D, jobs, system or research route', () => {
  expect(routes.map(r => r.path)).toEqual(['/login', '/', '/results/:id', '/preferences', '/:pathMatch(.*)*'])
})
