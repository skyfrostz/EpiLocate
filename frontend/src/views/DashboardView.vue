<template>
  <div class="view dashboard-view">
    <div class="page-heading"><div><h1>工作概览</h1><p class="page-intro">从最近的病例，继续今天的工作。</p></div><a-button type="primary" :loading="creating" @click="createCase"><EpIcon name="plus" /> 新建病例</a-button></div>
    <p v-if="createError" class="notice notice-error" role="alert">{{ createError }}</p>
    <section class="summary-strip" aria-label="当前已知工作状态">
      <div class="summary-metric"><span>已加载病例</span><strong>{{ hasLoaded ? items.length : '—' }}</strong><small>当前账号 · 最近一页</small></div>
      <div class="summary-metric"><span>输入可用</span><strong>{{ hasLoaded ? items.filter(c => c.status === 'READY').length : '—' }}</strong><small>已加载病例内</small></div>
      <div class="summary-metric"><span>已知进行中</span><strong>{{ activeJobs.length }}</strong><small>本会话已查询任务</small></div>
      <div class="summary-metric"><span>需要关注</span><strong>{{ hasLoaded ? items.filter(c => c.status === 'EXPIRED').length : '—' }}</strong><small>已加载病例输入到期</small></div>
    </section>
    <div class="board-grid">
      <div class="board-main">
        <section class="content-card" aria-label="继续工作"><div class="continue-row"><div class="empty-symbol"><EpIcon name="scan" :size="28" /></div><div class="continue-copy"><h2>{{ recentVisit ? '继续上次工作' : '病例工作空间' }}</h2><p v-if="continueId">{{ shortId(continueId) }}</p><p v-else>准备匿名病例，上传单切片 CT 后进入影像工作区。</p><span class="cell-sub">{{ recentVisit ? '本会话最近打开' : '按病例 API 返回顺序' }} · 单切片 CT</span></div><RouterLink v-if="continueId" :to="`/cases/${encodeURIComponent(continueId)}`">继续查看 →</RouterLink><RouterLink v-else to="/cases">进入病例中心 →</RouterLink></div></section>
        <section class="content-card" aria-labelledby="dashboard-cases-title">
          <div class="card-heading"><div><h2 id="dashboard-cases-title">最近病例</h2><p>当前账号 · 保留服务端顺序</p></div><a-button :loading="loading" @click="loadCases">刷新</a-button></div>
          <p v-if="error" class="notice notice-error" role="alert">{{ error }}{{ observedAt ? ' 保留上次读取记录，可能已过期。' : '' }}</p>
          <div v-if="loading && !hasLoaded" class="empty-state compact" role="status">正在读取病例…</div>
          <CaseTable v-else-if="items.length" :items="items" />
          <div v-else-if="hasLoaded && !error" class="empty-state"><div class="empty-symbol"><EpIcon name="cases" :size="24" /></div><h3>暂无病例</h3><p>创建匿名病例，上传已去标识的单切片 CT DICOM。</p><a-button :loading="creating" @click="createCase">新建病例</a-button></div>
          <div v-else-if="error" class="empty-state compact"><h3>病例无法读取</h3><p>检查网络和认证状态后点击“刷新”。</p></div>
          <div class="table-actions"><span>{{ nextCursor ? '还有更多病例' : '当前页记录' }}</span><RouterLink to="/cases">查看病例中心 →</RouterLink></div>
        </section>
        <p class="board-note">分析状态需进入病例或任务核对。模型响应 ≠ 病灶标注；研究输出 ≠ 临床诊断。</p>
      </div>
      <aside class="board-aside" aria-label="任务与服务">
        <section class="content-card"><div class="card-heading"><div><h2>任务进展</h2><p>本会话已知 · 上次查询状态</p></div><RouterLink to="/jobs" aria-label="查看任务记录">全部 →</RouterLink></div>
          <div v-for="job in knownJobs.slice(-3).reverse()" :key="job.job_id" class="task-mini"><header><RouterLink :to="`/jobs/${encodeURIComponent(job.job_id)}`">{{ job.kind === 'PREDICTION' ? '分类任务' : '遮挡分析' }}</RouterLink><EpStatus v-bind="jobStatus(job.status)" /></header><code>{{ shortId(job.case_id) }}</code><small class="muted">打开任务核对当前状态</small></div>
          <div v-if="!knownJobs.length" class="empty-state compact"><EpIcon name="jobs" :size="24" /><h3>暂无已确认任务</h3><p>打开任务详情后在这里继续查看。</p></div>
        </section>
        <section class="content-card"><div class="card-heading"><div><h2>服务可用性</h2><p>当前浏览器可见范围</p></div><RouterLink to="/system" aria-label="查看系统状态">详情 →</RouterLink></div>
          <div class="availability-row"><div>病例 API<small>{{ observedAt ? formatDate(new Date(observedAt).toISOString()) : '尚无成功读取记录' }}</small></div><EpStatus :label="error ? '读取失败' : observedAt ? '曾响应' : '未查询'" :tone="error ? 'warning' : 'neutral'" /></div>
          <div v-for="name in ['GPU 遥测','在线 Worker','存储与队列']" :key="name" class="availability-row"><span>{{ name }}</span><EpStatus label="未接入" tone="neutral" /></div>
        </section>
        <section class="content-card"><div class="card-heading"><div><h2>最近工作</h2><p>仅本会话病例访问</p></div></div><ul v-if="workspace.visits.length" class="activity-list"><li v-for="visit in workspace.visits.slice(0,3)" :key="visit.caseId"><RouterLink :to="`/cases/${encodeURIComponent(visit.caseId)}`">{{ shortId(visit.caseId) }}</RouterLink><time>{{ formatDate(new Date(visit.observedAt).toISOString()) }}</time></li></ul><p v-else class="viewer-note">尚未打开病例。登录状态重新验证后记录会清空。</p></section>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { apiClient } from '../api/client'
import { errorText } from '../api/errors'
import type { CaseSummary } from '../api/types'
import { isSessionCurrent, sessionEpoch } from '../auth/lifecycle'
import { formatDate } from '../format'
import CaseTable from '../components/CaseTable.vue'
import EpIcon from '../components/EpIcon.vue'
import EpStatus from '../components/EpStatus.vue'
import { jobStatus, shortId } from '../domain/clinical'
import { useCreateCase } from '../composables/useCreateCase'
import { useJobStore } from '../stores/jobs'
import { useWorkspaceStore } from '../stores/workspace'

const { creating, createError, createCase } = useCreateCase()
const jobs = useJobStore()
const workspace = useWorkspaceStore()
const knownJobs = computed(() => Object.values(jobs.byId))
const activeJobs = computed(() => knownJobs.value.filter(j => ['CREATED','QUEUED','RUNNING'].includes(j.status)))
const observedAt = ref<number | null>(null)
const recentVisit = computed(() => workspace.visits[0])
const continueId = computed(() => recentVisit.value?.caseId ?? items.value[0]?.case_id)
const items = ref<CaseSummary[]>([])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const hasLoaded = ref(false)
const error = ref<string | null>(null)

let generation = 0
let controller: AbortController | undefined
function reset() {
  generation++; controller?.abort(); observedAt.value = null
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
    items.value = page.items; nextCursor.value = page.next_cursor; hasLoaded.value = true; observedAt.value = Date.now()
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
