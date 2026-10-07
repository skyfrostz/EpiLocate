<template>
  <div class="view case-detail-view">
    <div class="page-heading"><div><h1>病例工作区</h1><p class="page-intro">查看单切片 CT，上传输入并发起分析。</p></div><RouterLink class="back-link" to="/cases">返回病例中心</RouterLink></div>
    <div class="record-identity"><span>病例</span><code>{{ caseId }}</code><a-tag>{{ cases.selected ? caseLabels[cases.selected.status] : '未读取' }}</a-tag></div>
    <p v-if="cases.detailError" class="notice notice-error" role="alert">{{ cases.detailError }}</p>
    <a-button v-if="cases.detailError" :loading="cases.detailLoading" @click="cases.loadCase(caseId)">重新读取病例</a-button>
    <p v-if="cases.detailLoading" class="notice" role="status">正在读取病例详情…</p>
    <template v-if="cases.selected?.case_id === caseId">
      <section class="case-workspace" aria-label="病例影像工作区">
        <aside class="content-card case-context" aria-label="病例与影像资料">
          <div class="card-heading"><div><h2>病例资料</h2><p>单切片 CT</p></div></div>
          <div class="case-meta"><span>创建时间</span><strong>{{ formatDate(cases.selected.created_at) }}</strong><span>输入可用期</span><strong>{{ formatDate(cases.selected.input_expires_at) }}</strong></div>
          <div v-if="slices.length" class="slice-list">
            <div v-for="slice in slices" :key="slice.slice_id" class="slice-row"><code>{{ slice.slice_id }}</code><span>第 {{ slice.ordinal + 1 }} 张 · {{ slice.width_px }} × {{ slice.height_px }} px</span></div>
          </div>
          <p v-else class="viewer-note">尚未上传影像。</p>
        </aside>
        <section class="content-card case-image-panel" aria-label="CT 影像">
          <div class="card-heading"><div><h2>影像查看</h2><p>拖动平移 · 滚轮缩放</p></div><a-tag v-if="slices.length">1 / 1</a-tag></div>
          <CornerstoneSliceViewer :file="previewFile" :input-state="previewState" :input-message="previewError" :slice-id="slices[0]?.slice_id ?? null" :slice-width="slices[0]?.width_px ?? null" :slice-height="slices[0]?.height_px ?? null" @retry="restoreDicom" />
        </section>
        <aside class="content-card case-analysis" aria-label="输入与分析工具">
          <div class="card-heading"><div><h2>{{ slices.length ? '发起分析' : '上传影像' }}</h2><p>{{ slices.length ? '完成后从任务详情查看结果' : '已去标识的单张 CT DICOM' }}</p></div></div>
          <template v-if="!slices.length">
            <div class="empty-state compact"><h3>准备影像输入</h3><p>选择一张已去标识的 CT DICOM。输入可用后，可创建分析任务。</p></div>
            <div class="case-upload">
              <label for="dicom-upload">选择 DICOM（最多 20 MiB）</label>
              <input id="dicom-upload" aria-label="选择已去标识的单张 CT DICOM（最多 20 MiB）" type="file" accept=".dcm,application/dicom" @change="chooseFile" />
              <a-button type="primary" :disabled="!selectedFile" :loading="uploading" @click="upload">上传 DICOM</a-button>
            </div>
          </template>
          <p v-if="uploadError" class="notice notice-error" role="alert">{{ uploadError }}</p>
          <template v-if="slices.length">
            <p v-if="cases.selected.status === 'EXPIRED'" class="notice" role="status">原始输入已到期。请在病例中心创建新病例并重新上传；已有结果可通过原结果链接查看。</p>
            <div class="inference-controls">
              <label>模型 ID <input v-model.trim="modelId" type="text" autocomplete="off" /></label>
              <div class="action-group"><a-button :loading="submitting" :disabled="!canSubmit" @click="submit('PREDICTION')">运行 Baseline 分类</a-button><a-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit('OCCLUSION')">运行 16 / 32 / 64 px 遮挡</a-button></div>
            </div>
            <p v-if="jobError" class="notice notice-error" role="alert">{{ jobError }}</p>
            <a v-if="jobError && acceptedJobHref" :href="acceptedJobHref">打开已创建任务 →</a>
          </template>
          <p class="viewer-note">分析单位：单切片。模型响应不等同病灶标注。</p>
        </aside>
      </section>
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
import { useWorkspaceStore } from '../stores/workspace'
import { errorText, useCaseStore } from '../stores/cases'

const route = useRoute()
const caseLabels: Record<CaseStatus, string> = { CREATED: '待上传', READY: '输入可用', EXPIRED: '输入已到期', DELETING: '删除中' }
const router = useRouter()
const cases = useCaseStore()
const workspace = useWorkspaceStore()
watch(() => cases.selected, value => { if (value?.case_id === caseId.value) workspace.visit(value.case_id) })
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
const acceptedJobs = new Map<string, string>()
const acceptedJobId = ref<string | null>(null)
const acceptedJobHref = computed(() => acceptedJobId.value
  ? router.resolve(`/jobs/${encodeURIComponent(acceptedJobId.value)}`).href : null)
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
  acceptedJobs.clear()
  acceptedJobId.value = null
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
  const action = `${id}:${slice.slice_id}:${modelId.value}:${kind}`
  acceptedJobId.value = acceptedJobs.get(action) ?? null
  try {
    let acceptedId = acceptedJobs.get(action)
    if (!acceptedId) {
      const key = jobKeys.get(action) ?? crypto.randomUUID()
      jobKeys.set(action, key)
      const created = kind === 'PREDICTION'
        ? await apiClient.createPrediction(id, slice.slice_id, modelId.value, key, controller.signal)
        : await apiClient.createOcclusion(id, slice.slice_id, modelId.value,
          'stage1-occlusion-instability-v1', [16, 32, 64], key, controller.signal)
      if (ownGeneration !== pageGeneration || !isSessionCurrent(epoch) || controller.signal.aborted) return
      if (created.case_id !== id) throw new Error('任务响应病例不一致。')
      acceptedId = created.job_id
      acceptedJobs.set(action, acceptedId)
    }
    acceptedJobId.value = acceptedId
    const failure = await router.push(`/jobs/${encodeURIComponent(acceptedId)}`)
    if (ownGeneration !== pageGeneration || !isSessionCurrent(epoch)) return
    if (failure) jobError.value = '任务已创建，页面未能打开。重试会打开同一任务。'
    else { jobKeys.delete(action); acceptedJobs.delete(action); acceptedJobId.value = null }
  } catch (cause) {
    if (ownGeneration !== pageGeneration || !isSessionCurrent(epoch)) return
    jobError.value = acceptedJobs.has(action)
      ? '任务已创建，页面未能打开。重试会打开同一任务。' : errorText(cause)
  } finally {
    if (ownGeneration === pageGeneration && isSessionCurrent(epoch)) submitting.value = false
  }
}
</script>
