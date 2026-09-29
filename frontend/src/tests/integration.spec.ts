import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { Button, Tag } from 'ant-design-vue'
import { ApiClient, apiClient } from '../api/client'
import type { JobRecord, ResultRecord } from '../api/types'
import { createAppRouter } from '../router'
import { useCaseStore } from '../stores/cases'
import { useJobStore } from '../stores/jobs'
import { useResultStore } from '../stores/results'
import { overlayCompatible } from '../viewer/geometry'
import ResultDetailView from '../views/ResultDetailView.vue'
import { auth } from '../auth/session'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
})
const job = (status: JobRecord['status'], resultId: string | null = null): JobRecord => ({
  job_id: 'job_test', kind: 'OCCLUSION', case_id: 'case_test', status, attempt_no: 1,
  retry_count: 0, lease_expire_time: null, last_heartbeat: null,
  failure_reason: null, progress: null, estimated_remaining_time_ms: null,
  result_id: resultId, error: null, created_at: '2026-09-26T00:00:00Z', finished_at: null,
})
const layer = {
  asset_id: 'response-16.png', layer_kind: 'CANDIDATE_RESPONSE' as const,
  width: 224, height: 224, coordinate_space: 'ALGORITHM_224' as const,
  value_min: 0, value_max: 1, origin: 'TOP_LEFT_PIXEL_EDGE' as const,
  x_axis: 'RIGHT' as const, y_axis: 'DOWN' as const, display_interpolation_only: true,
}
const result: ResultRecord = {
  result_id: 'result_test', job_id: 'job_test', case_id: 'case_test', slice_id: 'slice_test',
  kind: 'OCCLUSION', contract_version: '2.0', source: 'LIVE_CASE', status: 'COMPLETED',
  model_id: 'baseline_resnet18', model_version: 'hash-test', preprocessing_version: 'prep-test',
  protocol_id: 'stage1-occlusion-instability-v1', created_at: '2026-09-26T00:01:00Z',
  prediction: { predicted_class: 0, class_label: 'negative', positive_probability: 0.1,
    predicted_class_confidence: 0.9, inference_time_ms: 25 },
  scale_summaries: [{ block_size: 16, stride: 8, fill: 0.5, baseline_positive_probability: 0.1,
    median_absolute_probability_change: 0.02, flip_rate: 0, candidate_status: 'insufficient_positive_response',
    candidate_area_fraction: null, response_layer: layer, candidate_layer: null, comparison_grid_layer: null }],
  cross_scale: [], provenance: {},
  assets: [{ asset_id: layer.asset_id, layer_kind: layer.layer_kind, width: 224, height: 224,
    coordinate_space: layer.coordinate_space, media_type: 'image/png' }],
}

beforeEach(() => {
  setActivePinia(createPinia())
  auth.username = 'test-user'
  auth.csrfToken = 'test-csrf'
  auth.loaded = true
})
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

describe('Phase 2 API and state integration', () => {
  it('calls the browser fetch without using the API client as its receiver', async () => {
    const browserFetch = vi.fn(function (this: unknown) {
      if (this instanceof ApiClient) throw new TypeError('Illegal invocation')
      return Promise.resolve(json({ items: [], next_cursor: null }))
    })
    vi.stubGlobal('fetch', browserFetch)
    try {
      const client = new ApiClient({ baseUrl: '/api/v2' })
      expect((await client.listCases()).items).toEqual([])
      expect(browserFetch).toHaveBeenCalledTimes(1)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('loads the real Case route response and keeps an API error visible', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(json({ items: [{ case_id: 'case_test', patient_id: 'pat_test',
      status: 'READY', created_at: '2026-09-26T00:00:00Z', input_expires_at: null }], next_cursor: null }))
      .mockResolvedValueOnce(json({ code: 'UNAUTHENTICATED', message: 'Authentication required.',
        retryable: false, request_id: 'req-test', details: {} }, 401))
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher })
    const store = useCaseStore()
    const loading = store.loadCases(client)
    expect(store.loading).toBe(true)
    await loading
    expect(fetcher).toHaveBeenCalledWith('/api/v2/cases?limit=30', expect.anything())
    expect(store.items[0]?.case_id).toBe('case_test')
    await store.loadCases(client)
    expect(store.error).toContain('未认证')
    expect(store.hasLoaded).toBe(true)
  })

  it('polls CREATED through COMPLETED and stops after the terminal state', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn().mockResolvedValueOnce(json(job('CREATED')))
      .mockResolvedValueOnce(json(job('QUEUED')))
      .mockResolvedValueOnce(json(job('RUNNING')))
      .mockResolvedValueOnce(json(job('COMPLETED', 'result_test')))
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher })
    const store = useJobStore()
    store.startPolling('job_test', client, { intervalMs: 1000 })
    await flushPromises()
    expect(store.current?.status).toBe('CREATED')
    await vi.advanceTimersByTimeAsync(3000)
    expect(store.current?.status).toBe('COMPLETED')
    expect(store.current?.result_id).toBe('result_test')
    expect(store.isPolling).toBe(false)
    expect(fetcher).toHaveBeenCalledTimes(4)
  })

  it('stops polling on 401 and on elapsed timeout without inventing a terminal Job', async () => {
    vi.useFakeTimers()
    const client401 = new ApiClient({ baseUrl: '/api/v2', fetcher: vi.fn(async () => json({
      code: 'UNAUTHENTICATED', message: 'Authentication required.', retryable: false,
      request_id: 'req-auth', details: {},
    }, 401)) })
    const store = useJobStore()
    store.startPolling('job_test', client401, { intervalMs: 100 })
    await flushPromises()
    expect(store.isPolling).toBe(false)
    expect(store.error).toContain('未认证')
    let clock = 0
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher: vi.fn(async () => json(job('RUNNING'))) })
    store.startPolling('job_test', client, { intervalMs: 100, timeoutMs: 500, now: () => clock })
    await flushPromises()
    clock = 600
    await vi.advanceTimersByTimeAsync(100)
    expect(store.timedOut).toBe(true)
    expect(store.current?.status).toBe('RUNNING')
    expect(store.isPolling).toBe(false)
  })

  it('renders a contract-shaped LIVE_CASE result and its authorized response asset', async () => {
    vi.spyOn(apiClient, 'getResult').mockResolvedValue(result)
    vi.spyOn(apiClient, 'getResultAsset').mockResolvedValue(new Blob(['png-bytes'], { type: 'image/png' }))
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:test-response') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    const router = createAppRouter(createMemoryHistory())
    await router.push('/results/result_test')
    await router.isReady()
    const wrapper = mount(ResultDetailView, { global: { plugins: [createPinia(), router, Button, Tag] } })
    await flushPromises()
    expect(wrapper.text()).toContain('10%')
    expect(wrapper.text()).toContain('90%')
    expect(wrapper.text()).toContain('hash-test')
    expect(wrapper.text()).toContain('LIVE_CASE')
    expect(wrapper.text()).toContain('正响应不足')
    expect(wrapper.find('img[alt*="不是病灶标注"]').attributes('src')).toBe('blob:test-response')
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(apiClient.getResultAsset).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-response')
  })

  it('rejects a mismatched source or overlay coordinate space', async () => {
    const store = useResultStore()
    const client = new ApiClient({ baseUrl: '/api/v2', fetcher: vi.fn(async () => json({ ...result, source: 'MOCK' })) })
    await store.loadResult('result_test', client)
    expect(store.current).toBeNull()
    expect(store.error).not.toBeNull()
    expect(overlayCompatible({ url: 'blob:test', sliceId: 'slice_test', layer }, 'slice_test', 112, 80)).toBe(false)
    expect(overlayCompatible({ url: 'blob:test', sliceId: 'slice_other', layer: {
      ...layer, coordinate_space: 'RAW_PIXEL_EDGE', width: 112, height: 80,
    } }, 'slice_test', 112, 80)).toBe(false)
  })
})
