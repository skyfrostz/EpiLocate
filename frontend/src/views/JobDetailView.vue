<template>
  <div class="view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> JOB MONITOR / 任务监控</div>
    <nav class="context-nav" aria-label="任务上下文"><RouterLink to="/cases">病例中心</RouterLink><template v-if="job"><span aria-hidden="true"> / </span><RouterLink :to="`/cases/${encodeURIComponent(job.case_id)}`">关联病例</RouterLink></template><span aria-hidden="true"> / </span><span>任务详情</span></nav>
    <div class="page-heading"><div><h1>任务详情</h1><p class="page-intro">页面按 Job ID 自动查询；刷新页面后仍可恢复。</p></div><a-button :loading="jobs.loading" @click="jobs.startPolling(jobId)">重新查询</a-button></div>
    <div class="record-identity"><span>JOB ID</span><code style="overflow-wrap: anywhere">{{ jobId }}</code><a-tag :color="statusColor">{{ job ? labels[job.status] : '查询中' }}</a-tag></div>
    <p v-if="jobs.error" class="notice notice-error" role="alert">{{ jobs.error }}</p>
    <p v-if="jobs.error && job" class="notice" role="status">保留下方最近一次查询到的状态。查询中断不代表任务失败，点击“重新查询”可恢复。</p>
    <div class="content-card">
      <div class="card-heading"><div><h2>任务状态</h2><p>显示服务端确认的状态；查询暂停后可按原 Job ID 恢复。</p></div><span v-if="jobs.isPolling" class="live-indicator">自动刷新中</span></div>
      <div v-if="job?.status !== 'FAILED'" class="status-track" aria-label="任务状态"><span v-for="status in statuses" :key="status" :class="{ 'status-current': job?.status === status }" :aria-current="job?.status === status ? 'step' : undefined">{{ labels[status] }}</span></div>
      <div v-if="job" class="job-facts">
        <div><span>任务类型</span><strong>{{ job.kind === 'PREDICTION' ? '分类预测' : '遮挡分析' }}</strong></div>
        <div><span>病例 ID</span><RouterLink :to="`/cases/${encodeURIComponent(job.case_id)}`">{{ job.case_id }}</RouterLink></div>
        <div><span>已证实进度</span><strong>{{ job.progress == null ? '服务端未提供' : formatPercent(job.progress) }}</strong></div>
        <div><span>预计剩余</span><strong>{{ job.estimated_remaining_time_ms == null ? '服务端未提供' : `${Math.ceil(job.estimated_remaining_time_ms / 1000)} 秒` }}</strong></div>
        <div><span>创建时间</span><strong>{{ formatDate(job.created_at) }}</strong></div>
        <div><span>最近查询</span><strong>{{ jobs.lastUpdatedAt ? formatDate(new Date(jobs.lastUpdatedAt).toISOString()) : '—' }}</strong></div>
      </div>
      <div v-else class="empty-state compact" role="status"><h3>{{ jobs.error ? '任务无法读取' : '正在查询任务' }}</h3><p>请确认 Job ID、网络及认证状态。</p></div>
      <div v-if="failure && job" class="notice notice-error" role="alert">
        <h3>{{ failure.title }}</h3><p>{{ failure.message }}</p>
        <p v-if="failure.code !== 'UNKNOWN_JOB_FAILURE'">错误类型：<code>{{ failure.code }}</code></p>
        <p>Job ID：<code style="overflow-wrap: anywhere">{{ job.job_id }}</code></p>
        <RouterLink :to="failure.action === 'new-case' ? '/cases' : `/cases/${encodeURIComponent(job.case_id)}`">{{ failure.actionLabel }}</RouterLink>
      </div>
      <div v-if="job?.status === 'COMPLETED' && job.result_id" class="job-result-link"><RouterLink :to="`/results/${encodeURIComponent(job.result_id)}`">查看已完成结果 →</RouterLink></div>
      <p v-else-if="job?.status === 'COMPLETED'" class="notice notice-error">任务已完成，但服务端未提供 Result ID。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import type { JobStatus } from '../api/types'
import { describeJobFailure } from '../api/errors'
import { sessionEpoch } from '../auth/lifecycle'
import { auth } from '../auth/session'
import { formatDate, formatPercent } from '../format'
import { useJobStore } from '../stores/jobs'

const route = useRoute()
const jobs = useJobStore()
const jobId = computed(() => String(route.params.id ?? ''))
const job = computed(() => jobs.byId[jobId.value] ?? null)
const statuses: JobStatus[] = ['CREATED', 'QUEUED', 'RUNNING', 'COMPLETED']
const labels: Record<JobStatus, string> = { CREATED: '已创建', QUEUED: '排队中', RUNNING: '运行中', COMPLETED: '已完成', FAILED: '失败' }
const failure = computed(() => job.value?.status === 'FAILED' ? describeJobFailure(job.value) : null)
const statusColor = computed(() => job.value?.status === 'COMPLETED' ? 'green' : job.value?.status === 'FAILED' ? 'red' : 'blue')
watch([jobId, sessionEpoch], ([id]) => {
  if (auth.username && id) jobs.startPolling(id)
  else jobs.stopPolling()
}, { immediate: true })
onBeforeUnmount(() => jobs.stopPolling())
</script>
