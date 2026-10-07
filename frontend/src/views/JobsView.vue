<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useJobStore } from '../stores/jobs'
import { jobStatus, safeProgress, shortId } from '../domain/clinical'
import { formatDate } from '../format'
import EpStatus from '../components/EpStatus.vue'
const jobs = useJobStore(), filter = ref('all')
const known = computed(() => Object.values(jobs.byId).slice(-30).reverse())
const filtered = computed(() => known.value.filter(j => filter.value === 'all' || j.status === filter.value))
const statusOptions = ['CREATED','QUEUED','RUNNING','COMPLETED','FAILED']
onMounted(() => { void jobs.refreshKnown() })
onBeforeUnmount(() => jobs.stopCollectionReads())
</script>
<template>
  <div class="view"><div class="page-heading"><div><h1>任务记录</h1><p class="page-intro">本会话已知任务 · 最近 {{ known.length }} 条</p></div><a-button :loading="jobs.collectionLoading" :disabled="!known.length" @click="jobs.refreshKnown()">重新读取状态</a-button></div>
    <p class="notice">仅显示本会话打开并查询过的任务，最多 30 条。刷新页面或登录状态重新验证后集合会清空；原任务可通过链接恢复。</p>
    <section class="content-card"><div class="filter-toolbar"><label>任务状态<select v-model="filter"><option value="all">全部已知状态</option><option v-for="status in statusOptions" :key="status" :value="status">{{ jobStatus(status).label }}</option></select></label><span class="muted">历史范围不完整 · 打开任务核对结果</span></div>
      <div v-if="filtered.length" class="table-scroll" tabindex="0" role="region" aria-label="已知任务表"><table class="clinical-table"><thead><tr><th scope="col">任务 / 病例</th><th scope="col">状态</th><th scope="col">进度</th><th scope="col" class="optional-column">最近查询</th><th scope="col">操作</th></tr></thead><tbody>
        <tr v-for="job in filtered" :key="job.job_id"><td><RouterLink :to="`/jobs/${encodeURIComponent(job.job_id)}`">{{ job.kind === 'PREDICTION' ? '分类任务' : '遮挡分析' }}</RouterLink><code class="cell-sub">{{ shortId(job.job_id) }}</code><RouterLink class="cell-sub" :to="`/cases/${encodeURIComponent(job.case_id)}`">{{ shortId(job.case_id) }}</RouterLink></td><td><EpStatus v-bind="jobStatus(job.status)" /><span v-if="jobs.collectionErrors[job.job_id]" class="cell-sub">读取失败 · 上次状态</span></td><td>{{ safeProgress(job.progress) === null ? '未提供' : `${safeProgress(job.progress)}%` }}</td><td class="optional-column">{{ jobs.observedAtById[job.job_id] ? formatDate(new Date(jobs.observedAtById[job.job_id]!).toISOString()) : '未记录' }}</td><td><RouterLink :to="`/jobs/${encodeURIComponent(job.job_id)}`">查看 →</RouterLink></td></tr>
      </tbody></table></div>
      <div v-else class="empty-state"><h2>{{ known.length ? '没有符合筛选条件的任务' : '暂无已确认任务' }}</h2><p>{{ known.length ? '切换状态筛选，查看其他已知任务。' : '从病例发起分析，或打开已有任务链接。这里不会推断全局队列。' }}</p><RouterLink to="/cases">进入病例中心 →</RouterLink></div>
    </section>
  </div>
</template>
