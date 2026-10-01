import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiClient, ApiRequestError, type ApiClient } from '../api/client'
import type { JobRecord } from '../api/types'
import { errorText } from './cases'
import { onSessionReset } from '../auth/lifecycle'

export interface PollOptions {
  intervalMs?: number
  timeoutMs?: number
  maxErrors?: number
  now?: () => number
}

export const useJobStore = defineStore('jobs', () => {
  const byId = ref<Record<string, JobRecord>>({})
  const currentId = ref<string | null>(null)
  const loading = ref(false)
  const isPolling = ref(false)
  const timedOut = ref(false)
  const error = ref<string | null>(null)
  const lastUpdatedAt = ref<number | null>(null)
  const current = computed(() => currentId.value ? byId.value[currentId.value] ?? null : null)
  let generation = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let requestAbort: AbortController | undefined

  function upsert(job: JobRecord) {
    byId.value[job.job_id] = job
  }

  function stopPolling() {
    generation++
    requestAbort?.abort()
    requestAbort = undefined
    if (timer) clearTimeout(timer)
    timer = undefined
    isPolling.value = false
    loading.value = false
  }

  function startPolling(jobId: string, client: ApiClient = apiClient, options: PollOptions = {}) {
    stopPolling()
    currentId.value = jobId
    lastUpdatedAt.value = null
    error.value = null
    timedOut.value = false
    const ownGeneration = generation
    const intervalMs = options.intervalMs ?? 3000
    const timeoutMs = options.timeoutMs ?? 10 * 60 * 1000
    const maxErrors = options.maxErrors ?? 3
    const now = options.now ?? Date.now
    const startedAt = now()
    let consecutiveErrors = 0
    isPolling.value = true

    function schedule() {
      if (ownGeneration === generation && isPolling.value) timer = setTimeout(tick, intervalMs)
    }

    async function tick() {
      if (ownGeneration !== generation) return
      if (now() - startedAt >= timeoutMs) {
        timedOut.value = true
        error.value = '等待任务超时。任务可能仍在服务端运行，请稍后重新查询。'
        stopPolling()
        return
      }
      loading.value = true
      const controller = requestAbort = new AbortController()
      try {
        const job = await client.getJob(jobId, controller.signal)
        if (ownGeneration !== generation) return
        if (job.job_id !== jobId) throw new Error('任务响应 ID 与请求不一致。')
        upsert(job)
        lastUpdatedAt.value = now()
        error.value = null
        consecutiveErrors = 0
        if (job.status === 'COMPLETED' || job.status === 'FAILED') {
          stopPolling()
          return
        }
      } catch (cause) {
        if (ownGeneration !== generation) return
        error.value = errorText(cause)
        consecutiveErrors++
        if (cause instanceof ApiRequestError && cause.status === 401 || consecutiveErrors >= maxErrors) {
          stopPolling()
          return
        }
      } finally {
        if (ownGeneration === generation) loading.value = false
      }
      schedule()
    }

    void tick()
  }

  function clear() {
    stopPolling()
    byId.value = {}
    currentId.value = null
    error.value = null
    timedOut.value = false
    lastUpdatedAt.value = null
  }
  onSessionReset(clear)

  return { byId, currentId, current, loading, isPolling, timedOut, error, lastUpdatedAt,
    upsert, startPolling, stopPolling, clear }
})
