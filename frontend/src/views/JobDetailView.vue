<template>
  <div class="view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> JOB MONITOR / 任务监控</div>
    <div class="page-heading"><div><h1>任务详情</h1><p class="page-intro">页面按 Job ID 自动查询；刷新页面后仍可恢复。</p></div><a-button :loading="jobs.loading" @click="jobs.startPolling(jobId)">重新查询</a-button></div>
    <div class="record-identity"><span>JOB ID</span><code>{{ jobId }}</code><a-tag :color="statusColor">{{ job?.status ?? '查询中' }}</a-tag></div>
    <p v-if="jobs.error" class="notice notice-error" role="alert">{{ jobs.error }}</p>
    <div class="content-card">
      <div class="card-heading"><div><h2>任务状态</h2><p>状态由 Backend Job API 返回，不推断进度。</p></div><span v-if="jobs.isPolling" class="live-indicator">自动刷新中</span></div>
      <div class="status-track" aria-label="任务状态"><span v-for="status in statuses" :key="status" :class="{ 'status-current': job?.status === status }">{{ status }}</span></div>
      <div v-if="job" class="job-facts">
        <div><span>任务类型</span><strong>{{ job.kind }}</strong></div>
        <div><span>病例 ID</span><RouterLink :to="`/cases/${encodeURIComponent(job.case_id)}`">{{ job.case_id }}</RouterLink></div>
        <div><span>已证实进度</span><strong>{{ job.progress == null ? '服务端未提供' : formatPercent(job.progress) }}</strong></div>
        <div><span>预计剩余</span><strong>{{ job.estimated_remaining_time_ms == null ? '服务端未提供' : `${Math.ceil(job.estimated_remaining_time_ms / 1000)} 秒` }}</strong></div>
        <div><span>创建时间</span><strong>{{ formatDate(job.created_at) }}</strong></div>
        <div><span>最近查询</span><strong>{{ jobs.lastUpdatedAt ? formatDate(new Date(jobs.lastUpdatedAt).toISOString()) : '—' }}</strong></div>
      </div>
      <div v-else class="empty-state compact" role="status"><h3>{{ jobs.error ? '任务无法读取' : '正在查询任务' }}</h3><p>请确认 Job ID、网络及认证状态。</p></div>
      <div v-if="job?.status === 'FAILED'" class="notice notice-error" role="alert">任务失败：{{ job.error?.message ?? job.failure_reason ?? '服务端未提供原因' }}</div>
      <div v-if="job?.status === 'COMPLETED' && job.result_id" class="job-result-link"><RouterLink :to="`/results/${encodeURIComponent(job.result_id)}`">查看已完成结果 →</RouterLink></div>
      <p v-else-if="job?.status === 'COMPLETED'" class="notice notice-error">任务已完成，但服务端未提供 Result ID。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import type { JobStatus } from '../api/types'
import { formatDate, formatPercent } from '../format'
import { useJobStore } from '../stores/jobs'

const route = useRoute()
const jobs = useJobStore()
const jobId = computed(() => String(route.params.id ?? ''))
const job = computed(() => jobs.byId[jobId.value] ?? null)
const statuses: JobStatus[] = ['CREATED', 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED']
const statusColor = computed(() => job.value?.status === 'COMPLETED' ? 'green' : job.value?.status === 'FAILED' ? 'red' : 'blue')
watch(jobId, id => jobs.startPolling(id), { immediate: true })
onBeforeUnmount(() => jobs.stopPolling())
</script>
