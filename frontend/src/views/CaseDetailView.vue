<template>
  <div class="view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> CASE RECORD / 病例记录</div>
    <div class="page-heading"><div><h1>病例详情</h1><p class="page-intro">单切片 CT 输入与任务创建。</p></div><RouterLink class="back-link" to="/cases">← 返回病例中心</RouterLink></div>
    <div class="record-identity"><span>CASE ID</span><code>{{ caseId }}</code><a-tag>{{ cases.selected ? caseLabels[cases.selected.status] : '未读取' }}</a-tag></div>
    <p v-if="cases.detailError" class="notice notice-error" role="alert">{{ cases.detailError }}</p>
    <a-button v-if="cases.detailError" :loading="cases.detailLoading" @click="cases.loadCase(caseId)">重新读取病例</a-button>
    <p v-if="cases.detailLoading" class="notice" role="status">正在读取病例详情…</p>
    <template v-if="cases.selected?.case_id === caseId">
      <div class="detail-grid">
        <div class="content-card">
          <div class="card-heading"><div><h2>01 · 病例与影像输入</h2><p>输入记录 · 单切片 CT</p></div></div>
          <div class="case-meta"><span>创建时间</span><strong>{{ formatDate(cases.selected.created_at) }}</strong><span>输入可用期</span><strong>{{ formatDate(cases.selected.input_expires_at) }}</strong></div>
          <div v-if="slices.length" class="slice-list">
            <div v-for="slice in slices" :key="slice.slice_id" class="slice-row"><code>{{ slice.slice_id }}</code><span>第 {{ slice.ordinal + 1 }} 张 · {{ slice.width_px }} × {{ slice.height_px }} px</span></div>
          </div>
          <div v-else class="empty-state compact"><h3>尚无切片</h3><p>上传一张已去标识 CT DICOM；输入可用仅代表可以创建分析任务。</p></div>
          <div v-if="!slices.length" class="case-upload">
            <label for="dicom-upload">选择已去标识的单张 CT DICOM（最多 20 MiB）</label>
            <input id="dicom-upload" type="file" accept=".dcm,application/dicom" @change="chooseFile" />
            <a-button type="primary" :disabled="!selectedFile" :loading="uploading" @click="upload">上传 DICOM</a-button>
          </div>
          <p v-if="uploadError" class="notice notice-error" role="alert">{{ uploadError }}</p>
        </div>
        <div class="content-card">
          <div class="card-heading"><div><h2>02 · 影像浏览</h2><p>单切片 · 缩放与平移</p></div></div>
          <CornerstoneSliceViewer :file="previewFile" :input-state="previewState" :input-message="previewError" :slice-id="slices[0]?.slice_id ?? null" :slice-width="slices[0]?.width_px ?? null" :slice-height="slices[0]?.height_px ?? null" @retry="restoreDicom" />
        </div>
      </div>
      <div v-if="slices.length" class="content-card inference-card">
        <div class="card-heading"><div><h2>03 · 启动分析</h2><p>创建任务后进入任务详情，完成后沿结果链接阅读分析。</p></div></div>
        <p v-if="cases.selected.status === 'EXPIRED'" class="notice" role="status">原始输入已到期。请在病例中心创建新病例并重新上传；已有结果可通过原结果链接查看。</p>
        <div class="inference-controls">
          <label>模型 ID <input v-model.trim="modelId" type="text" autocomplete="off" /></label>
          <div class="action-group"><a-button :loading="submitting" :disabled="!canSubmit" @click="submit('PREDICTION')">运行 Baseline 分类</a-button><a-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit('OCCLUSION')">运行 16 / 32 / 64 px 遮挡</a-button></div>
        </div>
        <p class="viewer-note">单位：单切片。响应区域只表示模型决策响应，不等同病灶标注。</p>
        <p v-if="jobError" class="notice notice-error" role="alert">{{ jobError }}</p>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { apiClient, ApiRequestError } from '../api/client'
import { auth } from '../auth/session'
import { isSessionCurrent, sessionEpoch } from '../auth/lifecycle'
import type { CaseStatus, JobKind, SliceRecord } from '../api/types'
import CornerstoneSliceViewer from '../viewer/CornerstoneSliceViewer.vue'
import { formatDate } from '../format'
import { errorText, useCaseStore } from '../stores/cases'

const route = useRoute()
const caseLabels: Record<CaseStatus, string> = { CREATED: '待上传', READY: '输入可用', EXPIRED: '输入已到期', DELETING: '删除中' }
const router = useRouter()
const cases = useCaseStore()
const caseId = computed(() => String(route.params.id ?? ''))
const slices = computed<SliceRecord[]>(() => cases.selected?.case_id === caseId.value
  ? cases.selected.studies.flatMap(study => study.series.flatMap(series => series.slices)) : [])
const selectedFile = ref<File | null>(null)
const previewFile = ref<File | null>(null)
const previewState = ref<'empty' | 'loading' | 'ready' | 'expired' | 'error'>('empty')
const previewError = ref<string | null>(null)
const uploading = ref(false)
const uploadError = ref<string | null>(null)
const modelId = ref('baseline_resnet18')
const submitting = ref(false)
const jobError = ref<string | null>(null)
const uploadKey = ref<string | null>(null)
const jobKeys = new Map<string, string>()
let pageGeneration = 0
let previewGeneration = 0
let previewAbort: AbortController | undefined
let mutationAbort: AbortController | undefined
const canSubmit = computed(() => cases.selected?.status === 'READY' && slices.value.length > 0 && modelId.value.length > 0)

function resetPage() {
  pageGeneration++
  previewGeneration++
  previewAbort?.abort()
  mutationAbort?.abort()
  selectedFile.value = null
  previewFile.value = null
  previewState.value = 'empty'
  previewError.value = null
  uploadKey.value = null
  uploadError.value = null
  jobError.value = null
  uploading.value = false
  submitting.value = false
  jobKeys.clear()
}
watch([caseId, sessionEpoch], ([id]) => {
  resetPage()
  if (auth.username) void cases.loadCase(id)
}, { immediate: true, flush: 'sync' })
watch(slices, value => {
  if (value.length && !previewFile.value) void restoreDicom()
})
async function restoreDicom() {
  if (!slices.value.length || !auth.username) return
  const id = caseId.value
  const epoch = sessionEpoch.value
  const ownGeneration = ++previewGeneration
  previewAbort?.abort()
  const controller = previewAbort = new AbortController()
  previewFile.value = null
  previewState.value = 'loading'
  previewError.value = null
  try {
    const blob = await apiClient.getCaseDicom(id, controller.signal)
    if (controller.signal.aborted || ownGeneration !== previewGeneration || id !== caseId.value || !isSessionCurrent(epoch)) return
    previewFile.value = new File([blob], 'authorized-slice.dcm', { type: 'application/dicom' })
    previewState.value = 'ready'
  } catch (cause) {
    if (controller.signal.aborted || ownGeneration !== previewGeneration || !isSessionCurrent(epoch)) return
    previewFile.value = null
    previewState.value = cause instanceof ApiRequestError && (cause.status === 410 || cause.code === 'INPUT_EXPIRED') ? 'expired' : 'error'
    previewError.value = errorText(cause)
  }
}
onBeforeUnmount(() => { resetPage(); cases.clearDetail() })

function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
  uploadKey.value = null
  uploadError.value = null
  if (selectedFile.value && selectedFile.value.size > 20 * 1024 * 1024) {
    uploadError.value = '文件超过后端 20 MiB 限制。'
    selectedFile.value = null
  }
}

async function upload() {
  if (!selectedFile.value || uploading.value) return
  const id = caseId.value
  const epoch = sessionEpoch.value
  const ownGeneration = pageGeneration
  const controller = mutationAbort = new AbortController()
  uploading.value = true
  uploadError.value = null
  const file = selectedFile.value
  try {
    uploadKey.value ??= crypto.randomUUID()
    const uploaded = await apiClient.uploadCase(id, file, uploadKey.value, controller.signal)
    if (ownGeneration !== pageGeneration || !isSessionCurrent(epoch) || controller.signal.aborted) return
    if (uploaded.case_id !== id) throw new Error('上传响应病例不一致。')
    previewFile.value = file
    previewState.value = 'ready'
    previewError.value = null
    selectedFile.value = null
    await cases.loadCase(id)
  } catch (cause) {
    if (ownGeneration !== pageGeneration || !isSessionCurrent(epoch)) return
    uploadError.value = errorText(cause)
  } finally {
    if (ownGeneration === pageGeneration && isSessionCurrent(epoch)) uploading.value = false
  }
}

async function submit(kind: JobKind) {
  const slice = slices.value[0]
  if (!slice || !canSubmit.value || submitting.value) return
  const id = caseId.value
  const epoch = sessionEpoch.value
  const ownGeneration = pageGeneration
  const controller = mutationAbort = new AbortController()
  submitting.value = true
  jobError.value = null
  try {
    const action = `${id}:${slice.slice_id}:${modelId.value}:${kind}`
    const key = jobKeys.get(action) ?? crypto.randomUUID()
    jobKeys.set(action, key)
    const created = kind === 'PREDICTION'
      ? await apiClient.createPrediction(id, slice.slice_id, modelId.value, key, controller.signal)
      : await apiClient.createOcclusion(id, slice.slice_id, modelId.value,
        'stage1-occlusion-instability-v1', [16, 32, 64], key, controller.signal)
    if (ownGeneration !== pageGeneration || !isSessionCurrent(epoch) || controller.signal.aborted) return
    if (created.case_id !== id) throw new Error('任务响应病例不一致。')
    jobKeys.delete(action)
    await router.push(`/jobs/${encodeURIComponent(created.job_id)}`)
  } catch (cause) {
    if (ownGeneration !== pageGeneration || !isSessionCurrent(epoch)) return
    jobError.value = errorText(cause)
  } finally {
    if (ownGeneration === pageGeneration && isSessionCurrent(epoch)) submitting.value = false
  }
}
</script>
