<template>
  <div class="view">
    <div class="page-eyebrow"><span class="eyebrow-line" /> JOB MONITOR / 任务监控</div>
    <div class="page-heading"><div><h1>任务详情</h1><p class="page-intro">状态由 Backend Job API 确认；尚未读取时不推断进度。</p></div><span class="heading-subtle">/jobs/:id</span></div>
    <div class="record-identity"><span>JOB ID</span><code>{{ jobId }}</code><a-tag>未读取</a-tag></div>
    <div class="content-card"><div class="card-heading"><div><h2>任务状态</h2><p>CREATED → QUEUED → RUNNING → COMPLETED；失败可进入 FAILED。</p></div></div><div class="status-track" aria-label="支持的任务状态"><span v-for="status in statuses" :key="status">{{ status }}</span></div><div class="empty-state compact"><h3>尚未查询任务状态</h3><p>任务详情会按 Job ID 从 API 获取；空进度和空 ETA 不会填入估计值。</p></div></div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import type { JobStatus } from '../api/types'
const route = useRoute()
const jobId = computed(() => String(route.params.id ?? ''))
const statuses: JobStatus[] = ['CREATED', 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED']
</script>
