import { reactive } from 'vue'

interface SessionPayload { username: string; csrf_token: string }
const FUSION_KEY_PREFIX = 'epilocate:fusion:'
const SESSION_ACCOUNT_KEY = 'epilocate:session-account'

function clearFusionPreferences() {
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index--) {
      const key = sessionStorage.key(index)
      if (key?.startsWith(FUSION_KEY_PREFIX)) sessionStorage.removeItem(key)
    }
  } catch { /* Session storage may be unavailable; server authorization still applies. */ }
}

export const auth = reactive<{ username: string | null; csrfToken: string | null; loaded: boolean; error: string | null }>({
  username: null, csrfToken: null, loaded: false, error: null,
})

export function clearSession() {
  clearFusionPreferences()
  try { sessionStorage.removeItem(SESSION_ACCOUNT_KEY) } catch { /* Storage may be unavailable. */ }
  auth.username = null
  auth.csrfToken = null
  auth.loaded = true
  auth.error = null
}

function accept(payload: SessionPayload) {
  try {
    if (sessionStorage.getItem(SESSION_ACCOUNT_KEY) !== payload.username) clearFusionPreferences()
    sessionStorage.setItem(SESSION_ACCOUNT_KEY, payload.username)
  } catch { /* Storage may be unavailable. */ }
  auth.username = payload.username
  auth.csrfToken = payload.csrf_token
  auth.loaded = true
  auth.error = null
}

export async function loadSession(force = false): Promise<boolean> {
  if (auth.loaded && !force) return auth.username !== null
  try {
    const response = await fetch('/auth/session', { credentials: 'include', cache: 'no-store' })
    if (!response.ok) {
      clearSession()
      if (response.status !== 401) auth.error = '登录状态检查失败，请稍后重试。'
      return false
    }
    accept(await response.json() as SessionPayload)
    return true
  } catch {
    clearSession()
    auth.error = '无法连接登录服务，请检查网络后重试。'
    return false
  }
}

export async function login(username: string, password: string): Promise<void> {
  let response: Response
  try {
    response = await fetch('/auth/login', {
      method: 'POST', credentials: 'include', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
  } catch {
    throw new Error('无法连接登录服务，请检查网络后重试。')
  }
  if (!response.ok) {
    if (response.status === 429) throw new Error('尝试次数过多，请稍后再试。')
    if (response.status === 401) throw new Error('账号或密码不正确。')
    throw new Error('登录暂时不可用，请稍后再试。')
  }
  accept(await response.json() as SessionPayload)
}

export async function logout(): Promise<void> {
  if (!auth.csrfToken) return
  const response = await fetch('/auth/logout', {
    method: 'POST', credentials: 'include', cache: 'no-store',
    headers: { 'X-CSRF-Token': auth.csrfToken },
  })
  if (!response.ok && response.status !== 401) throw new Error('退出失败，请重试。')
  clearSession()
}
