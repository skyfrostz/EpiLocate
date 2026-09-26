import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { JobRecord } from '../api/types'

export const useJobStore = defineStore('jobs', () => {
  const byId = ref<Record<string, JobRecord>>({})

  function upsert(job: JobRecord) {
    byId.value[job.job_id] = job
  }

  function clear() {
    byId.value = {}
  }

  return { byId, upsert, clear }
})
