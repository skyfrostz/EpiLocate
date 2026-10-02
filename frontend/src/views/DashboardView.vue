<template>
  <div class="view dashboard-view">
    <div class="dashboard-heading">
      <div><h1>影像研究工作台</h1><p class="page-intro">从病例输入到模型响应，每一步都可追溯。</p></div>
      <a-button type="primary" size="large" @click="router.push('/cases')">进入病例中心</a-button>
    </div>
    <section class="workspace-snapshot" aria-label="当前页输入状态">
      <div class="snapshot-intro"><span>当前页概览</span><strong>单切片 CT</strong><small>仅统计下方已读取记录</small></div>
      <div v-for="state in snapshotStates" :key="state.key" class="snapshot-metric"><span>{{ state.label }}</span><strong>{{ hasLoaded ? items.filter(item => item.status === state.key).length : '—' }}</strong></div>
      <div class="snapshot-source"><span :class="['source-indicator', { 'source-stale': error }]">{{ error ? '读取失败' : loading ? '读取中' : hasLoaded ? '已读取' : '等待读取' }}</span><small>{{ error && hasLoaded ? '保留上次记录' : '授权 Case API' }}</small></div>
    </section>

    <section class="content-card" aria-labelledby="dashboard-cases-title">
      <div class="card-heading"><div><h2 id="dashboard-cases-title">当前账号的病例</h2><p>展示服务端第一页，最多 6 条；不代表全部病例。</p></div><a-button :loading="loading" @click="loadCases">刷新</a-button></div>
      <p v-if="error" class="notice notice-error" role="alert">{{ error }}<span v-if="items.length"> 当前显示上次成功读取的记录，可能不是最新状态。</span></p>
      <div v-if="loading && !hasLoaded" class="empty-state compact" role="status">正在读取病例…</div>
      <template v-else-if="items.length">
        <CaseCollection :items="items" :loading="loading" />
        <p v-if="nextCursor" class="viewer-note">还有更多病例，可在病例中心继续查看。</p>
      </template>
      <div v-else-if="hasLoaded && !error" class="empty-state compact"><h3>暂无病例</h3><p>创建匿名病例，上传已去标识的单切片 CT DICOM 开始研究。</p></div>
      <div v-else-if="error" class="empty-state compact"><h3>病例无法读取</h3><p>检查网络和认证状态后点击“刷新”。</p></div>
      <RouterLink class="back-link" to="/cases">查看全部病例 →</RouterLink>
    </section>

    <section class="workspace-guide" aria-label="工作流程">
      <div><span class="guide-step">1</span><div><h3>准备输入</h3><p>在病例中心创建记录，上传已去标识的单张 CT。</p></div></div>
      <div><span class="guide-step">2</span><div><h3>启动分析</h3><p>选择分类或遮挡任务，通过任务链接恢复进度。</p></div></div>
      <div><span class="guide-step">3</span><div><h3>阅读结果</h3><p>核对模型版本。响应图用于研究，不是病灶标注。</p></div></div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { apiClient } from '../api/client'
import { errorText } from '../api/errors'
import type { CaseSummary } from '../api/types'
import { isSessionCurrent, sessionEpoch } from '../auth/lifecycle'
import CaseCollection from '../components/CaseCollection.vue'

const router = useRouter()
const items = ref<CaseSummary[]>([])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const hasLoaded = ref(false)
const error = ref<string | null>(null)
const snapshotStates = [{ key: 'READY', label: '输入可用' }, { key: 'CREATED', label: '待上传' }, { key: 'EXPIRED', label: '输入已到期' }] as const
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
