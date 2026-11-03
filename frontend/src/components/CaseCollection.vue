<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import type { CaseStatus, CaseSummary } from '../api/types'
import { sessionEpoch } from '../auth/lifecycle'
import { inputStatus, shortId } from '../domain/clinical'
import { formatDate } from '../format'
import CaseTable from './CaseTable.vue'
import EpStatus from './EpStatus.vue'

const props = defineProps<{ items: CaseSummary[]; expires?: boolean }>()
const route = useRoute()
const router = useRouter()
const statuses: CaseStatus[] = ['CREATED', 'READY', 'EXPIRED', 'DELETING']
const search = ref('')
type Choices = { view: 'list' | 'cards'; status: CaseStatus | 'all' }
function readStatus(value: unknown): Choices['status'] {
  return statuses.find(status => status === value) ?? 'all'
}
const pending = shallowRef<Choices>()
const choices = computed<Choices>(() => pending.value ?? {
  view: route.query.view === 'cards' ? 'cards' : 'list',
  status: readStatus(route.query.status),
})
const filtered = computed(() => {
  const needle = search.value.trim().toLowerCase()
  return props.items.filter(item => (choices.value.status === 'all' || choices.value.status === item.status)
    && item.case_id.toLowerCase().includes(needle))
})

// Merge rapid view/status changes before the router commits. Only enum values enter the URL.
async function choose(change: Partial<Choices>) {
  const next = { ...choices.value, ...change }
  pending.value = next
  try {
    await router.replace({ path: route.path, query: {
      view: next.view === 'cards' ? 'cards' : undefined,
      status: next.status === 'all' ? undefined : next.status,
    } })
  } finally {
    if (pending.value === next) pending.value = undefined
  }
}
function clearFilters() {
  search.value = ''
  void choose({ status: 'all' })
}
watch([sessionEpoch, () => route.path], () => {
  search.value = ''
  pending.value = undefined
}, { flush: 'sync' })
</script>

<template>
  <div class="filter-toolbar">
    <label>筛选已加载病例<input v-model="search" type="search" autocomplete="off" placeholder="按 Case ID 查找" /></label>
    <label>输入状态<select aria-label="输入状态" :value="choices.status" @change="choose({ status: readStatus(($event.target as HTMLSelectElement).value) })">
      <option value="all">全部输入状态</option><option v-for="status in statuses" :key="status" :value="status">{{ inputStatus(status).label }}</option>
    </select></label>
    <slot />
    <div class="case-view-switch" role="group" aria-label="病例显示模式">
      <button type="button" :aria-pressed="choices.view === 'list'" @click="choose({ view: 'list' })">列表</button>
      <button type="button" :aria-pressed="choices.view === 'cards'" @click="choose({ view: 'cards' })">卡片</button>
    </div>
  </div>
  <div v-if="items.length && !filtered.length" class="empty-state compact" role="status">
    <h3>没有符合筛选条件的病例</h3><p>搜索仅覆盖已加载记录。</p><button type="button" @click="clearFilters">清空筛选</button>
  </div>
  <template v-else-if="filtered.length">
    <CaseTable v-if="choices.view === 'list'" :items="filtered" :expires="expires" />
    <ul v-else class="case-cards" aria-label="病例卡片">
      <li v-for="item in filtered" :key="item.case_id">
        <RouterLink class="case-link" :to="`/cases/${encodeURIComponent(item.case_id)}`" :aria-label="`打开病例 ${item.case_id}`">{{ shortId(item.case_id) }}</RouterLink>
        <EpStatus v-bind="inputStatus(item.status)" />
        <dl><dt>创建时间</dt><dd>{{ formatDate(item.created_at) }}</dd>
          <template v-if="expires"><dt>输入可用期</dt><dd>{{ formatDate(item.input_expires_at) }}</dd></template>
          <dt>分析状态</dt><dd>未查询</dd>
        </dl>
        <details class="identity-detail"><summary>查看完整标识</summary><code>{{ item.case_id }}</code><span class="cell-sub">匿名上下文：{{ item.patient_id }}</span></details>
      </li>
    </ul>
  </template>
  <p v-if="filtered.length && (search.trim() || choices.status !== 'all')" class="viewer-note" role="status">匹配 {{ filtered.length }} 例 · 仅当前已加载记录</p>
</template>

<style scoped>
.case-view-switch { display:flex; align-items:center; gap:4px }
.case-view-switch button { min-height:44px; padding:0 12px; border:1px solid var(--ep-line); border-radius:var(--ep-radius); background:var(--ep-surface); color:var(--ep-muted); cursor:pointer }
.case-view-switch button[aria-pressed=true] { border-color:var(--ep-accent); background:var(--ep-accent-soft); color:var(--ep-accent) }
.case-cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr)); gap:12px; padding:0; margin:12px 0; list-style:none }
.case-cards li { display:grid; justify-items:start; align-content:start; gap:8px; min-width:0; padding:14px; border:1px solid var(--ep-line); border-radius:var(--ep-radius); background:var(--ep-subtle) }
.case-cards dl { display:grid; grid-template-columns:auto 1fr; gap:4px 12px; margin:0; font-size:var(--ep-small) }
.case-cards dt { color:var(--ep-muted) }.case-cards dd { margin:0 }
</style>
