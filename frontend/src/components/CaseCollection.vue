<template>
  <div class="case-collection" :aria-busy="loading">
    <div class="collection-toolbar">
      <label class="collection-search"><span>查找病例</span><input v-model="search" type="search" placeholder="搜索已加载的匿名 ID" autocomplete="off" /></label>
      <label class="collection-filter"><span>输入状态</span><select :value="status" @change="setOption('status', ($event.target as HTMLSelectElement).value)"><option value="all">全部状态</option><option v-for="(label, key) in labels" :key="key" :value="key">{{ label }}</option></select></label>
      <div class="segmented-control" role="group" aria-label="病例显示模式"><button type="button" :aria-pressed="mode === 'list'" @click="setOption('view', 'list')">列表</button><button type="button" :aria-pressed="mode === 'cards'" @click="setOption('view', 'cards')">卡片</button></div>
    </div>
    <div class="collection-summary"><span role="status">已加载 {{ items.length }} 条 · 当前显示 {{ filtered.length }} 条</span><span>筛选仅作用于已加载记录</span></div>
    <div v-if="filtered.length" :class="['collection-records', { 'collection-cards': mode === 'cards' }]">
      <div v-if="mode === 'list'" class="table-head" aria-hidden="true"><span>匿名病例 ID</span><span>输入状态</span><span>创建时间</span><span>输入可用期</span></div>
      <article v-for="item in filtered" :key="item.case_id" class="case-row">
        <RouterLink :to="`/cases/${encodeURIComponent(item.case_id)}`" class="case-link"><span v-if="mode === 'cards'" class="case-card-kicker">CASE RECORD</span>{{ item.case_id }}<span v-if="mode === 'cards'" class="case-card-open">打开病例 ↗</span></RouterLink>
        <span class="case-status" :data-status="item.status"><i aria-hidden="true" />{{ labels[item.status] ?? '未知状态' }}</span>
        <span class="case-date"><small aria-hidden="true">创建时间</small><span class="sr-only">创建时间：</span>{{ formatDate(item.created_at) }}</span><span class="case-date"><small aria-hidden="true">输入可用期</small><span class="sr-only">输入可用期：</span>{{ formatDate(item.input_expires_at) }}</span>
      </article>
    </div>
    <div v-else class="empty-state compact"><h3>没有匹配的病例</h3><p>调整筛选条件，或加载更多记录后再次查找。</p><button class="recovery-action" type="button" @click="clearFilters">清除筛选</button></div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import type { CaseStatus, CaseSummary } from '../api/types'
import { formatDate } from '../format'

const props = defineProps<{ items: CaseSummary[]; loading?: boolean }>()
const route = useRoute(), router = useRouter()
const labels: Record<CaseStatus, string> = { CREATED: '待上传', READY: '输入可用', EXPIRED: '输入已到期', DELETING: '删除中' }
// Search remains in memory so anonymous identifiers are not copied into URL/history.
const search = ref('')
const status = computed(() => typeof route.query.status === 'string' && Object.hasOwn(labels, route.query.status) ? route.query.status : 'all')
const mode = computed(() => route.query.view === 'cards' ? 'cards' : 'list')
const filtered = computed(() => props.items.filter(item => (status.value === 'all' || item.status === status.value) && item.case_id.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())))
let pendingQuery: LocationQueryRaw | null = null
let queryGeneration = 0
function setOption(key: 'view' | 'status', value: string) {
  // Merge rapid independent choices before Vue Router commits its asynchronous navigation.
  const query = { ...(pendingQuery ?? route.query), [key]: value === 'all' || value === 'list' ? undefined : value }
  pendingQuery = query
  const generation = ++queryGeneration
  void router.replace({ query }).finally(() => { if (generation === queryGeneration) pendingQuery = null })
}
function clearFilters() { search.value = ''; setOption('status', 'all') }
watch(() => route.path, () => { search.value = ''; pendingQuery = null; queryGeneration++ })
</script>
