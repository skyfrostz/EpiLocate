import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiClient, ApiRequestError, type ApiClient } from '../api/client'
import type { CaseDetail, CaseSummary } from '../api/types'

export const useCaseStore = defineStore('cases', () => {
  const items = ref<CaseSummary[]>([])
  const selected = ref<CaseDetail | null>(null)
  const nextCursor = ref<string | null>(null)
  const hasLoaded = ref(false)
  const loading = ref(false)
  const detailLoading = ref(false)
  const error = ref<string | null>(null)
  const detailError = ref<string | null>(null)
  let listEpoch = 0
  let detailEpoch = 0

  function setPage(cases: CaseSummary[], cursor: string | null) {
    items.value = cases
    nextCursor.value = cursor
    hasLoaded.value = true
  }

  function select(value: CaseDetail | null) {
    selected.value = value
  }

  async function loadCases(client: ApiClient = apiClient, append = false) {
    const epoch = ++listEpoch
    loading.value = true
    error.value = null
    try {
      const page = await client.listCases(append ? nextCursor.value ?? undefined : undefined)
      if (epoch !== listEpoch) return
      items.value = append ? [...items.value, ...page.items] : page.items
      nextCursor.value = page.next_cursor
      hasLoaded.value = true
    } catch (cause) {
      if (epoch !== listEpoch) return
      error.value = errorText(cause)
    } finally {
      if (epoch === listEpoch) loading.value = false
    }
  }

  async function loadCase(caseId: string, client: ApiClient = apiClient) {
    const epoch = ++detailEpoch
    selected.value = null
    detailLoading.value = true
    detailError.value = null
    try {
      const detail = await client.getCase(caseId)
      if (epoch !== detailEpoch) return
      if (detail.case_id !== caseId) throw new Error('病例响应 ID 与请求不一致。')
      selected.value = detail
    } catch (cause) {
      if (epoch === detailEpoch) detailError.value = errorText(cause)
    } finally {
      if (epoch === detailEpoch) detailLoading.value = false
    }
  }

  function reset() {
    listEpoch++
    detailEpoch++
    items.value = []
    selected.value = null
    nextCursor.value = null
    hasLoaded.value = false
    loading.value = false
    detailLoading.value = false
    error.value = null
    detailError.value = null
  }

  return { items, selected, nextCursor, hasLoaded, loading, detailLoading, error, detailError,
    setPage, select, loadCases, loadCase, reset }
})

export function errorText(cause: unknown): string {
  if (cause instanceof ApiRequestError) return cause.message
  return '响应无法读取，请重试。'
}
