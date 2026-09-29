<template>
  <div class="view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> CASE RECORD / 病例记录</div>
    <div class="page-heading"><div><h1>病例详情</h1><p class="page-intro">单切片 CT 输入与任务创建。</p></div><RouterLink class="back-link" to="/cases">← 返回病例中心</RouterLink></div>
    <div class="record-identity"><span>CASE ID</span><code>{{ caseId }}</code><a-tag>{{ cases.selected?.status ?? '未读取' }}</a-tag></div>
    <p v-if="cases.detailError" class="notice notice-error" role="alert">{{ cases.detailError }}</p>
    <p v-if="cases.detailLoading" class="notice" role="status">正在读取病例详情…</p>
    <template v-if="cases.selected?.case_id === caseId">
      <div class="detail-grid">
        <div class="content-card">
          <div class="card-heading"><div><h2>影像结构</h2><p>Study / Series / Slice</p></div></div>
          <div class="case-meta"><span>创建时间</span><strong>{{ formatDate(cases.selected.created_at) }}</strong><span>输入可用期</span><strong>{{ formatDate(cases.selected.input_expires_at) }}</strong></div>
          <div v-if="slices.length" class="slice-list">
            <div v-for="slice in slices" :key="slice.slice_id" class="slice-row"><code>{{ slice.slice_id }}</code><span>第 {{ slice.ordinal + 1 }} 张 · {{ slice.width_px }} × {{ slice.height_px }} px</span></div>
          </div>
          <div v-else class="empty-state compact"><h3>尚无切片</h3><p>上传一张已去标识 CT DICOM；READY 仅代表输入可排队。</p></div>
          <div v-if="!slices.length" class="case-upload">
            <label for="dicom-upload">选择已去标识的单张 CT DICOM（最多 20 MiB）</label>
            <input id="dicom-upload" type="file" accept=".dcm,application/dicom" @change="chooseFile" />
            <a-button type="primary" :disabled="!selectedFile" :loading="uploading" @click="upload">上传 DICOM</a-button>
          </div>
          <p v-if="uploadError" class="notice notice-error" role="alert">{{ uploadError }}</p>
        </div>
        <div class="content-card">
          <div class="card-heading"><div><h2>影像浏览</h2><p>Cornerstone3D · 单切片</p></div></div>
          <CornerstoneSliceViewer :file="previewFile" :slice-id="slices[0]?.slice_id ?? null" :slice-width="slices[0]?.width_px ?? null" :slice-height="slices[0]?.height_px ?? null" />
        </div>
      </div>
      <div v-if="slices.length" class="content-card inference-card">
        <div class="card-heading"><div><h2>启动分析</h2><p>分类与遮挡任务由独立 API 创建，结果按 Job ID 查询。</p></div></div>
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
import { apiClient } from '../api/client'
import type { JobKind, SliceRecord } from '../api/types'
import CornerstoneSliceViewer from '../viewer/CornerstoneSliceViewer.vue'
import { formatDate } from '../format'
import { errorText, useCaseStore } from '../stores/cases'

const route = useRoute()
const router = useRouter()
const cases = useCaseStore()
const caseId = computed(() => String(route.params.id ?? ''))
const slices = computed<SliceRecord[]>(() => cases.selected?.case_id === caseId.value
  ? cases.selected.studies.flatMap(study => study.series.flatMap(series => series.slices)) : [])
const selectedFile = ref<File | null>(null)
const previewFile = ref<File | null>(null)
const uploading = ref(false)
const uploadError = ref<string | null>(null)
const modelId = ref('baseline_resnet18')
const submitting = ref(false)
const jobError = ref<string | null>(null)
const uploadKey = ref<string | null>(null)
const jobKeys = new Map<string, string>()
const canSubmit = computed(() => cases.selected?.status === 'READY' && slices.value.length > 0 && modelId.value.length > 0)

watch(caseId, id => { selectedFile.value = null; previewFile.value = null; uploadKey.value = null; jobKeys.clear(); void cases.loadCase(id) }, { immediate: true })
watch(slices, async value => {
  if (!value.length || previewFile.value) return
  try {
    const blob = await apiClient.getCaseDicom(caseId.value)
    previewFile.value = new File([blob], `${caseId.value}.dcm`, { type: 'application/dicom' })
  } catch {
    // The metadata remains useful when an expired input cannot be restored.
    previewFile.value = null
  }
})
onBeforeUnmount(() => { previewFile.value = null })

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
  if (!selectedFile.value) return
  uploading.value = true
  uploadError.value = null
  const file = selectedFile.value
  try {
    uploadKey.value ??= crypto.randomUUID()
    const uploaded = await apiClient.uploadCase(caseId.value, file, uploadKey.value)
    if (uploaded.case_id !== caseId.value) throw new Error('上传响应病例不一致。')
    previewFile.value = file
    selectedFile.value = null
    await cases.loadCase(caseId.value)
  } catch (cause) {
    uploadError.value = errorText(cause)
  } finally {
    uploading.value = false
  }
}

async function submit(kind: JobKind) {
  const slice = slices.value[0]
  if (!slice || !canSubmit.value) return
  submitting.value = true
  jobError.value = null
  try {
    const action = `${caseId.value}:${slice.slice_id}:${modelId.value}:${kind}`
    const key = jobKeys.get(action) ?? crypto.randomUUID()
    jobKeys.set(action, key)
    const created = kind === 'PREDICTION'
      ? await apiClient.createPrediction(caseId.value, slice.slice_id, modelId.value, key)
      : await apiClient.createOcclusion(caseId.value, slice.slice_id, modelId.value,
        'stage1-occlusion-instability-v1', [16, 32, 64], key)
    if (created.case_id !== caseId.value) throw new Error('任务响应病例不一致。')
    await router.push(`/jobs/${encodeURIComponent(created.job_id)}`)
  } catch (cause) {
    jobError.value = errorText(cause)
  } finally {
    submitting.value = false
  }
}
</script>
