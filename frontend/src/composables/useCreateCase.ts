import { onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiClient } from '../api/client'
import { errorText } from '../api/errors'
import { isSessionCurrent, sessionEpoch } from '../auth/lifecycle'
export function useCreateCase() {
  const router = useRouter(), creating = ref(false), createError = ref<string | null>(null)
  let generation = 0, key: string | null = null, acceptedId: string | null = null
  function reset() { generation++; creating.value = false; createError.value = null; key = null; acceptedId = null }
  watch(sessionEpoch, reset, { flush:'sync' }); onBeforeUnmount(reset)
  async function createCase() {
    if (creating.value) return
    const ownGeneration = generation, epoch = sessionEpoch.value
    creating.value = true; createError.value = null
    try {
      if (!acceptedId) {
        key ??= crypto.randomUUID()
        const created = await apiClient.createCase(null, key)
        if (ownGeneration !== generation || !isSessionCurrent(epoch)) return
        acceptedId = created.case_id
      }
      const target = `/cases/${encodeURIComponent(acceptedId)}`
      const failure = await router.push(target)
      if (failure && ownGeneration === generation && isSessionCurrent(epoch)) createError.value = '病例已创建，页面未能打开。重试会打开同一病例。'
    } catch (cause) { if (ownGeneration === generation && isSessionCurrent(epoch)) createError.value = acceptedId ? '病例已创建，页面未能打开。重试会打开同一病例。' : errorText(cause) }
    finally { if (ownGeneration === generation && isSessionCurrent(epoch)) creating.value = false }
  }
  return { creating, createError, createCase }
}
