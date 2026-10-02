<template>
  <div class="view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> CASE CENTER / 病例中心</div>
    <div class="page-heading">
      <div><h1>病例中心</h1><p class="page-intro">仅显示当前已授权用户的匿名病例。</p></div>
      <a-button type="primary" :loading="creating" @click="createCase">创建匿名病例</a-button>
    </div>
    <p v-if="createError" class="notice notice-error" role="alert">{{ createError }}</p>
    <div class="content-card">
      <div class="card-heading">
        <div><h2>病例列表</h2><p>数据由 Case API 实时读取。</p></div>
        <a-button :loading="cases.loading" @click="cases.loadCases()">刷新</a-button>
      </div>
      <p v-if="cases.error" class="notice notice-error" role="alert">{{ cases.error }}</p>
      <div v-if="cases.loading && !cases.hasLoaded" class="empty-state compact" role="status">正在读取病例…</div>
      <template v-else-if="cases.hasLoaded && cases.items.length">
        <div class="table-head" aria-hidden="true"><span>CASE ID</span><span>状态</span><span>创建时间</span><span>输入可用期</span></div>
        <div v-for="item in cases.items" :key="item.case_id" class="case-row">
          <RouterLink :to="`/cases/${encodeURIComponent(item.case_id)}`" class="case-link">{{ item.case_id }}</RouterLink>
          <span><a-tag :color="item.status === 'READY' ? 'green' : 'default'">{{ caseLabels[item.status] }}</a-tag></span>
          <span>{{ formatDate(item.created_at) }}</span>
          <span>{{ formatDate(item.input_expires_at) }}</span>
        </div>
        <div v-if="cases.nextCursor" class="table-actions"><a-button :loading="cases.loading" @click="cases.loadCases(undefined, true)">加载更多</a-button></div>
      </template>
      <div v-else-if="cases.hasLoaded && !cases.error" class="empty-state compact"><h3>暂无病例</h3><p>服务端返回了空列表。可创建新的匿名病例。</p></div>
      <div v-else class="empty-state compact"><h3>病例列表未加载</h3><p>请检查网络或认证状态后重试。</p></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { apiClient } from '../api/client'
import { formatDate } from '../format'
import { errorText, useCaseStore } from '../stores/cases'
import { isSessionCurrent, sessionEpoch } from '../auth/lifecycle'
import type { CaseStatus } from '../api/types'

const cases = useCaseStore()
const caseLabels: Record<CaseStatus, string> = { CREATED: '待上传', READY: '输入可用', EXPIRED: '输入已到期', DELETING: '删除中' }
const router = useRouter()
const creating = ref(false)
const createError = ref<string | null>(null)
const createKey = ref<string | null>(null)
let generation = 0
function resetCreation() {
  generation++
  creating.value = false
  createError.value = null
  createKey.value = null
}
watch(sessionEpoch, resetCreation, { flush: 'sync' })
onBeforeUnmount(resetCreation)

onMounted(() => { void cases.loadCases() })

async function createCase() {
  if (creating.value) return
  const epoch = sessionEpoch.value
  const ownGeneration = generation
  creating.value = true
  createError.value = null
  try {
    createKey.value ??= crypto.randomUUID()
    const created = await apiClient.createCase(null, createKey.value)
    if (ownGeneration !== generation || !isSessionCurrent(epoch)) return
    await router.push(`/cases/${encodeURIComponent(created.case_id)}`)
    createKey.value = null
  } catch (cause) {
    if (ownGeneration !== generation || !isSessionCurrent(epoch)) return
    createError.value = errorText(cause)
  } finally {
    if (ownGeneration === generation && isSessionCurrent(epoch)) creating.value = false
  }
}
</script>
