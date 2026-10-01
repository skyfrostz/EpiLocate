/** Cross-tab messages contain only an invalidation nonce, never credentials. */
export const SESSION_SYNC_KEY = 'epilocate:session-invalidated'
const ownNotices = new Set<string>()
export function publishSessionInvalidation() {
  const nonce = crypto.randomUUID()
  ownNotices.add(nonce)
  if (ownNotices.size > 32) ownNotices.delete(ownNotices.values().next().value!)
  try { localStorage.setItem(SESSION_SYNC_KEY, nonce) } catch { /* Resume checks cover disabled storage. */ }
}
export function listenForSessionInvalidation(invalidate: () => void, resume: () => void) {
  const storage = (event: StorageEvent) => {
    if (event.key !== SESSION_SYNC_KEY || !event.newValue || ownNotices.has(event.newValue)) return
    if (/^[a-f0-9-]{36}$/i.test(event.newValue)) invalidate()
  }
  const focus = () => resume()
  const pageshow = (event: PageTransitionEvent) => { if (event.persisted) resume() }
  window.addEventListener('storage', storage)
  window.addEventListener('focus', focus)
  window.addEventListener('pageshow', pageshow)
  return () => {
    window.removeEventListener('storage', storage)
    window.removeEventListener('focus', focus)
    window.removeEventListener('pageshow', pageshow)
  }
}
