<template>
  <div class="view dashboard-view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> OVERVIEW / 总览</div>
    <div class="dashboard-heading">
      <div>
        <h1>影像研究工作台</h1>
        <p class="page-intro">从匿名病例进入影像、任务和结果。界面只呈现服务端已确认的数据。</p>
      </div>
      <div class="heading-badge"><span class="badge-crosshair" aria-hidden="true" /> SINGLE SLICE · CT</div>
    </div>

    <div class="dashboard-grid">
      <section class="primary-panel">
        <div class="panel-topline"><span>工作入口</span><span>01 / 03</span></div>
        <div class="scan-illustration" aria-hidden="true">
          <div class="scan-frame"><div class="scan-crosshair" /><div class="scan-focus" /></div>
          <span class="scan-coord scan-coord-a">AXIAL</span>
          <span class="scan-coord scan-coord-b">X · Y</span>
        </div>
        <div class="primary-panel-copy">
          <span class="panel-kicker">CASE FIRST</span>
          <h2>先找到病例，再阅读分析。</h2>
          <p>病例、任务和结果保持独立记录。打开病例后，可沿匿名 ID 追踪后续工作。</p>
          <a-button type="primary" size="large" @click="router.push('/cases')">进入病例中心 <span aria-hidden="true">↗</span></a-button>
        </div>
      </section>

      <section class="workflow-panel" aria-label="工作流程">
        <div class="section-small-heading"><span>工作流程</span><span>TRACEABLE FLOW</span></div>
        <div class="workflow-step"><span class="step-number">01</span><div><h3>病例准备</h3><p>查看已授权的匿名病例与影像输入。</p></div><span class="step-glyph">↗</span></div>
        <div class="workflow-step"><span class="step-number">02</span><div><h3>任务执行</h3><p>按 Job ID 查询创建、排队、运行及终态。</p></div><span class="step-glyph">↗</span></div>
        <div class="workflow-step"><span class="step-number">03</span><div><h3>结果阅读</h3><p>分类、模型版本和响应图以 Result 为准。</p></div><span class="step-glyph">↗</span></div>
        <div class="workflow-note"><span class="note-mark">i</span><p>任务与结果通过各自链接恢复。病例列表由服务端读取，模型响应用于研究解释。</p></div>
      </section>
    </div>

    <section class="content-card" aria-labelledby="dashboard-cases-title">
      <div class="card-heading"><div><h2 id="dashboard-cases-title">当前账号的病例</h2><p>展示 Case API 返回的第一页，保留服务端顺序。</p></div><a-button :loading="loading" @click="loadCases">刷新</a-button></div>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}</p>
      <div v-if="loading && !hasLoaded" class="empty-state compact" role="status">正在读取病例…</div>
      <template v-else-if="items.length">
        <div class="table-head" aria-hidden="true"><span>CASE ID</span><span>状态</span><span>创建时间</span><span>输入可用期</span></div>
        <div v-for="item in items" :key="item.case_id" class="case-row">
          <RouterLink :to="`/cases/${encodeURIComponent(item.case_id)}`" class="case-link">{{ item.case_id }}</RouterLink>
          <span><a-tag :color="item.status === 'READY' ? 'green' : 'default'">{{ caseLabels[item.status] }}</a-tag></span>
          <span>{{ formatDate(item.created_at) }}</span><span>{{ formatDate(item.input_expires_at) }}</span>
        </div>
        <p v-if="nextCursor" class="viewer-note">还有更多病例，可在病例中心继续查看。</p>
      </template>
      <div v-else-if="hasLoaded && !error" class="empty-state compact"><h3>暂无病例</h3><p>创建匿名病例，上传已去标识的单切片 CT DICOM 开始研究。</p></div>
      <div v-else-if="error" class="empty-state compact"><h3>病例无法读取</h3><p>检查网络和认证状态后点击“刷新”。</p></div>
      <RouterLink class="back-link" to="/cases">查看全部病例 →</RouterLink>
    </section>

    <section class="scope-strip" aria-label="当前范围">
      <div><span>影像范围</span><strong>单切片 CT</strong></div>
      <div><span>数据来源</span><strong>服务端真实记录</strong></div>
      <div><span>解释边界</span><strong>模型响应 ≠ 病灶标注</strong></div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { apiClient } from '../api/client'
import { errorText } from '../api/errors'
import type { CaseStatus, CaseSummary } from '../api/types'
import { isSessionCurrent, sessionEpoch } from '../auth/lifecycle'
import { formatDate } from '../format'

const router = useRouter()
const items = ref<CaseSummary[]>([])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const hasLoaded = ref(false)
const error = ref<string | null>(null)
const caseLabels: Record<CaseStatus, string> = { CREATED: '待上传', READY: '输入可用', EXPIRED: '输入已到期', DELETING: '删除中' }
let generation = 0
let controller: AbortController | undefined
function reset() {
  generation++; controller?.abort()
  items.value = []; nextCursor.value = null; loading.value = false; hasLoaded.value = false; error.value = null
}
async function loadCases() {
  const ownGeneration = ++generation, epoch = sessionEpoch.value
  controller?.abort()
  const abort = controller = new AbortController()
  loading.value = true; error.value = null
  try {
    const page = await apiClient.listCases(undefined, 6, abort.signal)
    if (ownGeneration !== generation || !isSessionCurrent(epoch)) return
    items.value = page.items; nextCursor.value = page.next_cursor; hasLoaded.value = true
  } catch (cause) {
    if (ownGeneration === generation && isSessionCurrent(epoch)) error.value = errorText(cause)
  } finally {
    if (ownGeneration === generation && isSessionCurrent(epoch)) loading.value = false
  }
}
watch(sessionEpoch, reset, { flush: 'sync' })
onMounted(() => { void loadCases() })
onBeforeUnmount(reset)
</script>
