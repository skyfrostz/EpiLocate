<template>
  <div class="view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> RESULT / 分析结果</div>
    <div class="page-heading"><div><h1>结果详情</h1><p class="page-intro">仅显示已完成 Job 的 LIVE_CASE Result。</p></div><a-button :loading="results.loading" @click="results.loadResult(resultId)">重新读取</a-button></div>
    <div class="record-identity"><span>RESULT ID</span><code>{{ resultId }}</code><a-tag :color="result ? 'green' : 'default'">{{ result?.status ?? '未读取' }}</a-tag></div>
    <p v-if="results.error" class="notice notice-error" role="alert">{{ results.error }}</p>
    <p v-if="results.loading" class="notice" role="status">正在读取 Result…</p>
    <template v-if="result">
      <nav class="result-context" aria-label="当前病例与任务">
        <RouterLink :to="`/cases/${encodeURIComponent(result.case_id)}`"><span>当前病例</span><code>{{ result.case_id }}</code></RouterLink>
        <RouterLink :to="`/jobs/${encodeURIComponent(result.job_id)}`"><span>当前任务</span><code>{{ result.job_id }}</code></RouterLink>
        <span class="result-context-slice"><span>单切片 CT</span><code>{{ result.slice_id }}</code></span>
      </nav>
      <div class="result-workspace">
        <div class="content-card fusion-card result-image-panel">
          <div class="card-heading"><div><h2>CT 与模型图层</h2><p>单切片像素空间 · Cornerstone3D</p></div><a-tag :color="geometryGate?.ok ? 'green' : 'default'">{{ result.kind === 'PREDICTION' ? '分类任务 · 无叠加图层' : geometryGate?.ok ? '像素契约匹配' : '叠加尚不可用' }}</a-tag></div>
          <p v-if="ctLoading" class="viewer-note" role="status">正在通过授权 API 读取原始 DICOM…</p>
          <p v-if="ctError" class="notice notice-error" role="alert">{{ ctError }}</p>
          <p v-if="result.kind === 'OCCLUSION' && ctState === 'ready' && !geometryGate?.ok" class="viewer-note" role="status">{{ geometryGate?.reason }}</p>
          <div v-if="result.kind === 'OCCLUSION'" class="fusion-controls">
            <label><input v-model="overlayVisible" type="checkbox" :disabled="!geometryGate?.ok || !imageReady" /> 显示叠加</label>
            <label>透明度 <input v-model.number="overlayOpacity" type="range" min="0" max="1" step="0.05" :disabled="!geometryGate?.ok || !imageReady" /> {{ Math.round(overlayOpacity * 100) }}%</label>
          </div>
          <CornerstoneSliceViewer :file="dicomFile" :slice-id="result.slice_id" :slice-width="currentSlice?.width_px ?? null" :slice-height="currentSlice?.height_px ?? null" :overlay="viewerOverlay" :overlay-visible="overlayVisible" :overlay-opacity="overlayOpacity" :initial-view="viewState" :input-state="ctState" :input-message="ctError" @retry="loadCt" @camera-changed="viewState = $event" />
          <p class="viewer-note">仅当原始 DICOM 摘要、版本、Slice、资产清单及画布映射全部通过校验时才绘制叠加。独立图层始终保留。</p>
        </div>
        <aside class="result-analysis-panel" aria-label="分类与模型响应">
        <div class="content-card result-prediction-card">
          <div class="card-heading"><div><h2>单切片分类</h2><p>Prediction · {{ result.slice_id }}</p></div></div>
          <div v-if="result.prediction" class="prediction-content">
            <div class="prediction-label"><span>预测类别</span><strong>{{ result.prediction.class_label }}</strong></div>
            <div class="metric-pair"><div><span>正类概率</span><strong>{{ formatPercent(result.prediction.positive_probability) }}</strong></div><div><span>预测类别置信度</span><strong>{{ formatPercent(result.prediction.predicted_class_confidence) }}</strong></div></div>
            <p class="viewer-note">预测单位：Slice。正类概率与预测类别置信度分别来自服务端。</p>
          </div>
          <div v-else class="empty-state compact"><h3>分类字段不可用</h3><p>此 Result 未提供预测摘要。</p></div>
        </div>
        <div class="content-card result-heatmap-card">
          <div class="card-heading"><div><h2>模型响应图</h2><p>受保护的独立图层 · 不是病灶标注</p></div><a-tag v-if="result.kind === 'OCCLUSION'">{{ selectedScale }} px</a-tag></div>
          <div v-if="result.scale_summaries.length" class="scale-switch" role="group" aria-label="遮挡尺度">
            <button v-for="summary in result.scale_summaries" :key="summary.block_size" type="button" :class="{ active: selectedScale === summary.block_size }" :aria-pressed="selectedScale === summary.block_size" @click="selectedScale = summary.block_size">{{ summary.block_size }} px</button>
          </div>
          <div v-if="selectedSummary" class="layer-switch" role="group" aria-label="模型图层">
            <button v-for="option in layerOptions" :key="option.kind" type="button" :class="{ active: selectedLayerKind === option.kind }" :aria-pressed="selectedLayerKind === option.kind" :disabled="!layerFor(option.kind)" @click="selectedLayerKind = option.kind">{{ option.label }}</button>
          </div>
          <div v-if="selectedSummary" class="scale-metrics">
            <span>中位绝对概率变化 <strong>{{ formatPercent(selectedSummary.median_absolute_probability_change) }}</strong></span>
            <span>翻转比例 <strong>{{ formatPercent(selectedSummary.flip_rate) }}</strong></span>
            <span>候选响应 <strong>{{ selectedSummary.candidate_status === 'valid' ? '有效模型响应' : selectedSummary.candidate_status === 'insufficient_positive_response' ? '正响应不足' : '候选状态不可用' }}</strong></span>
          </div>
          <div class="heatmap-frame">
            <div v-if="results.assetError || imageError"><p class="notice notice-error" role="alert">{{ results.assetError ?? imageError }}</p><button v-if="selectedLayer" class="recovery-action" type="button" @click="retryAsset">重试读取图层</button></div>
            <p v-else-if="results.assetLoading" role="status">正在读取授权图层…</p>
            <img v-else-if="results.assetUrl && selectedLayer && !imageError" :key="results.assetUrl" :src="results.assetUrl" :alt="`${selectedLayerLabel}，模型决策响应，不是病灶标注`" @load="checkImage" @error="checkImageError" />
            <p v-else>{{ result.kind === 'PREDICTION' ? '分类结果没有响应图资产。' : '当前尺度或图层未提供图层资产。' }}</p>
          </div>
          <p v-if="selectedLayer" class="asset-caption">{{ selectedLayerLabel }} · {{ selectedLayer.coordinate_space }} · {{ selectedLayer.width }} × {{ selectedLayer.height }} px</p>
          <p v-if="selectedLayer?.layer_kind === 'COMPARISON_GRID'" class="viewer-note">14×14 区域平均图；放大仅用于显示，不增加空间分辨率。</p>
        </div>
        </aside>
      </div>
        <details class="content-card model-card result-metadata">
          <summary class="card-heading"><span>模型与算法版本</span><span>服务端 provenance · 展开查看</span></summary>
          <div class="result-meta">
            <div><span>模型 ID</span><code>{{ result.model_id }}</code></div>
            <div><span>模型版本</span><code>{{ result.model_version }}</code></div>
            <div><span>预处理版本</span><code>{{ result.preprocessing_version }}</code></div>
            <div><span>协议版本</span><code>{{ result.protocol_id }}</code></div>
            <div><span>数据来源</span><strong>{{ result.source }}</strong></div>
            <div><span>任务 ID</span><RouterLink :to="`/jobs/${encodeURIComponent(result.job_id)}`">{{ result.job_id }}</RouterLink></div>
          </div>
        </details>
      <p class="result-disclaimer">图层表示模型决策响应，不是病灶标注或临床诊断。仅验证当前单切片的像素几何，未建立三维空间配准。</p>
    </template>
    <div v-else-if="!results.loading" class="content-card"><div class="empty-state compact"><h3>结果尚不可显示</h3><p>请确认 Result ID、认证状态和 API 连接，然后重新读取。</p></div></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { apiClient } from '../api/client'
import { ApiRequestError, errorText } from '../api/errors'
import { sessionEpoch } from '../auth/lifecycle'
import type { CaseDetail, HeatmapLayer, SliceRecord } from '../api/types'
import { formatPercent } from '../format'
import { useResultStore } from '../stores/results'
import CornerstoneSliceViewer from '../viewer/CornerstoneSliceViewer.vue'
import { resolveOverlayGeometry, type ViewerCameraState, type ViewerOverlayInput } from '../viewer/geometry'

const route = useRoute()
const results = useResultStore()
const resultId = computed(() => String(route.params.id ?? ''))
const result = computed(() => results.current?.result_id === resultId.value ? results.current : null)
const selectedScale = ref<16 | 32 | 64>(16)
type LayerKind = HeatmapLayer['layer_kind']
interface FusionPreferences { scale: 16 | 32 | 64; layer: LayerKind; visible: boolean; opacity: number; view: ViewerCameraState | null }
const preferenceKey = (id: string) => `epilocate:fusion:${id}`
function readPreferences(id: string): FusionPreferences | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(preferenceKey(id)) ?? 'null') as Partial<FusionPreferences> | null
    if (!value || ![16, 32, 64].includes(value.scale ?? 0) ||
        !['CANDIDATE_RESPONSE', 'CANDIDATE_TOP10', 'COMPARISON_GRID'].includes(value.layer ?? '') ||
        typeof value.visible !== 'boolean' || typeof value.opacity !== 'number' ||
        !Number.isFinite(value.opacity) || value.opacity < 0 || value.opacity > 1) return null
    const view = value.view
    const validView = view && typeof view.zoom === 'number' && Number.isFinite(view.zoom) &&
      view.zoom >= 0.25 && view.zoom <= 8 && Array.isArray(view.pan) && view.pan.length === 2 &&
      view.pan.every(item => typeof item === 'number' && Number.isFinite(item) && Math.abs(item) <= 100000)
    return { ...value, view: validView ? view : null } as FusionPreferences
  } catch { return null }
}
const selectedLayerKind = ref<HeatmapLayer['layer_kind']>('CANDIDATE_RESPONSE')
const overlayVisible = ref(false)
const overlayOpacity = ref(0.5)
const viewState = ref<ViewerCameraState | null>(null)
const imageError = ref<string | null>(null)
const imageReady = ref(false)
const caseDetail = ref<CaseDetail | null>(null)
const dicomFile = ref<File | null>(null)
const dicomSha256 = ref<string | null>(null)
const ctLoading = ref(false)
const ctError = ref<string | null>(null)
const ctState = ref<'empty' | 'loading' | 'ready' | 'expired' | 'error'>('empty')
let ctGeneration = 0
let ctController: AbortController | null = null

const layerOptions: Array<{ kind: HeatmapLayer['layer_kind']; label: string }> = [
  { kind: 'CANDIDATE_RESPONSE', label: '响应图' },
  { kind: 'CANDIDATE_TOP10', label: '候选区域' },
  { kind: 'COMPARISON_GRID', label: '尺度比较' },
]
const selectedSummary = computed(() => result.value?.scale_summaries.find(item => item.block_size === selectedScale.value) ?? null)
function layerFor(kind: HeatmapLayer['layer_kind']): HeatmapLayer | null {
  const summary = selectedSummary.value
  return kind === 'CANDIDATE_RESPONSE' ? summary?.response_layer ?? null
    : kind === 'CANDIDATE_TOP10' ? summary?.candidate_layer ?? null
      : summary?.comparison_grid_layer ?? null
}
const selectedLayer = computed(() => layerFor(selectedLayerKind.value))
const selectedLayerLabel = computed(() => layerOptions.find(option => option.kind === selectedLayerKind.value)?.label ?? '')
const currentSlice = computed<SliceRecord | null>(() => caseDetail.value?.studies.flatMap(study => study.series.flatMap(series => series.slices))
  .find(slice => slice.slice_id === result.value?.slice_id) ?? null)
const geometryGate = computed(() => result.value
  ? resolveOverlayGeometry(result.value, caseDetail.value, dicomSha256.value, selectedSummary.value, selectedLayer.value)
  : null)
const viewerOverlay = computed<ViewerOverlayInput | null>(() =>
  geometryGate.value?.ok && selectedLayer.value && results.assetUrl && imageReady.value && dicomFile.value && result.value
    ? { url: results.assetUrl, sliceId: result.value.slice_id,
        layer: selectedLayer.value, geometry: geometryGate.value.geometry } : null)

watch(resultId, id => { void results.loadResult(id) }, { immediate: true })
async function loadCt() {
  const value = result.value
  ctController?.abort()
  const controller = new AbortController()
  ctController = controller
  const ownGeneration = ++ctGeneration
  const ownEpoch = sessionEpoch.value
  caseDetail.value = null
  dicomFile.value = null
  dicomSha256.value = null
  ctError.value = null
  ctLoading.value = Boolean(value)
  ctState.value = value ? 'loading' : 'empty'
  if (!value) return
  try {
    const [detail, blob] = await Promise.all([
      apiClient.getCase(value.case_id, controller.signal), apiClient.getCaseDicom(value.case_id, controller.signal),
    ])
    if (ownGeneration !== ctGeneration || ownEpoch !== sessionEpoch.value) return
    const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
    if (ownGeneration !== ctGeneration || ownEpoch !== sessionEpoch.value) return
    const hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
    if (hash !== String(value.provenance.input_sha256 ?? '').toLowerCase()) throw new Error('DICOM SHA-256 与 Result provenance 不一致。')
    caseDetail.value = detail
    dicomSha256.value = hash
    dicomFile.value = new File([blob], 'authorized-slice.dcm', { type: 'application/dicom' })
    ctState.value = 'ready'
  } catch (cause) {
    if (ownGeneration === ctGeneration && ownEpoch === sessionEpoch.value && !controller.signal.aborted) {
      ctError.value = cause instanceof Error && cause.message.includes('SHA-256') ? cause.message : errorText(cause)
      ctState.value = cause instanceof ApiRequestError && cause.status === 410 ? 'expired' : 'error'
    }
  } finally {
    if (ownGeneration === ctGeneration) ctLoading.value = false
  }
}
watch(result, value => {
  if (value) {
    const preferences = readPreferences(value.result_id)
    selectedScale.value = preferences && value.scale_summaries.some(item => item.block_size === preferences.scale)
      ? preferences.scale : value.scale_summaries[0]?.block_size ?? 16
    selectedLayerKind.value = preferences?.layer ?? 'CANDIDATE_RESPONSE'
    overlayVisible.value = preferences?.visible ?? false
    overlayOpacity.value = preferences?.opacity ?? 0.5
    viewState.value = preferences?.view ?? null
  }
  void loadCt()
})
watch(selectedSummary, () => {
  if (!layerFor(selectedLayerKind.value)) selectedLayerKind.value = layerOptions.find(option => layerFor(option.kind))?.kind ?? 'CANDIDATE_RESPONSE'
})
watch([resultId, selectedScale, selectedLayerKind, overlayVisible, overlayOpacity, viewState], () => {
  if (!result.value) return
  try {
    sessionStorage.setItem(preferenceKey(resultId.value), JSON.stringify({
      scale: selectedScale.value, layer: selectedLayerKind.value,
      visible: overlayVisible.value, opacity: overlayOpacity.value, view: viewState.value,
    } satisfies FusionPreferences))
  } catch { /* Browser storage may be unavailable; the current view remains usable. */ }
})
watch([result, selectedScale, selectedLayerKind], () => {
  retryAsset()
})
function retryAsset() {
  imageError.value = null
  imageReady.value = false
  void results.loadAsset(selectedLayer.value)
}
function invalidateLocal() {
  ctGeneration++
  ctController?.abort()
  ctController = null
  caseDetail.value = null
  dicomFile.value = null
  dicomSha256.value = null
  ctLoading.value = false
  ctError.value = null
  ctState.value = 'empty'
  imageReady.value = false
  imageError.value = null
  overlayVisible.value = false
  overlayOpacity.value = 0.5
  viewState.value = null
  selectedScale.value = 16
  selectedLayerKind.value = 'CANDIDATE_RESPONSE'
}
watch(sessionEpoch, () => {
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index--) {
      const key = sessionStorage.key(index)
      if (key?.startsWith('epilocate:fusion:')) sessionStorage.removeItem(key)
    }
  } catch { /* Storage can be unavailable. */ }
  results.clear()
  invalidateLocal()
}, { flush: 'sync' })
onBeforeUnmount(() => { invalidateLocal(); results.clear() })

function checkImage(event: Event) {
  const image = event.target as HTMLImageElement
  if (image.getAttribute('src') !== results.assetUrl || results.assetLoading || !result.value) return
  const layer = selectedLayer.value
  if (!layer || image.naturalWidth !== layer.width || image.naturalHeight !== layer.height) {
    imageError.value = '响应图尺寸与结果元数据不一致，已停止显示。'
    imageReady.value = false
  } else imageReady.value = true
}
function checkImageError(event: Event) {
  const image = event.target as HTMLImageElement
  if (image.getAttribute('src') !== results.assetUrl || !result.value) return
  imageError.value = '响应图无法解码。'
  imageReady.value = false
}
</script>
