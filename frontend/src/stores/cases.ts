import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { CaseDetail, CaseSummary } from '../api/types'

export const useCaseStore = defineStore('cases', () => {
  const items = ref<CaseSummary[]>([])
  const selected = ref<CaseDetail | null>(null)
  const nextCursor = ref<string | null>(null)
  const hasLoaded = ref(false)

  function setPage(cases: CaseSummary[], cursor: string | null) {
    items.value = cases
    nextCursor.value = cursor
    hasLoaded.value = true
  }

  function select(value: CaseDetail | null) {
    selected.value = value
  }

  function reset() {
    items.value = []
    selected.value = null
    nextCursor.value = null
    hasLoaded.value = false
  }

  return { items, selected, nextCursor, hasLoaded, setPage, select, reset }
})
