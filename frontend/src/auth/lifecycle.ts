import { onScopeDispose, ref } from 'vue'

/** Invalidates every request and local cache from the previous browser identity. */
export const sessionEpoch = ref(0)
const resetHandlers = new Set<() => void>()

export function onSessionReset(reset: () => void) {
  resetHandlers.add(reset)
  const dispose = () => { resetHandlers.delete(reset) }
  onScopeDispose(dispose)
  return dispose
}

export function invalidateSessionData() {
  sessionEpoch.value++
  for (const reset of resetHandlers) reset()
}

export function isSessionCurrent(epoch: number) {
  return epoch === sessionEpoch.value
}
