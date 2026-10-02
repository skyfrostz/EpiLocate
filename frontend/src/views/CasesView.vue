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
        <div><h2>病例列表</h2><p>保留服务端顺序；筛选与显示模式不会创建分析任务。</p></div>
        <a-button :loading="cases.loading" @click="cases.loadCases()">刷新</a-button>
      </div>
      <p v-if="cases.error" class="notice notice-error" role="alert">{{ cases.error }}<span v-if="cases.items.length"> 当前保留上次成功读取的记录，可能不是最新状态。</span></p>
      <div v-if="cases.loading && !cases.hasLoaded" class="empty-state compact" role="status">正在读取病例…</div>
      <template v-else-if="cases.hasLoaded && cases.items.length">
        <CaseCollection :items="cases.items" :loading="cases.loading" />
        <div v-if="cases.nextCursor" class="table-actions"><a-button :loading="cases.loading" @click="cases.loadCases(undefined, true)">加载更多</a-button></div>
      </template>
      <div v-else-if="cases.hasLoaded && !cases.error" class="empty-state compact"><h3>暂无病例</h3><p>服务端返回了空列表。可创建新的匿名病例。</p></div>
      <div v-else class="empty-state compact"><h3>病例列表未加载</h3><p>请检查网络或认证状态后重试。</p></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiClient } from '../api/client'
import CaseCollection from '../components/CaseCollection.vue'
import { errorText, useCaseStore } from '../stores/cases'
import { isSessionCurrent, sessionEpoch } from '../auth/lifecycle'

const cases = useCaseStore()
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
