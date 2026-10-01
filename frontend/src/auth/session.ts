import { reactive } from 'vue'
import { ApiRequestError, normalizeApiError } from '../api/errors'
import { invalidateSessionData, isSessionCurrent, sessionEpoch } from './lifecycle'

interface SessionPayload { username: string; csrf_token: string }
const FUSION_KEY_PREFIX = 'epilocate:fusion:'
const SESSION_ACCOUNT_KEY = 'epilocate:session-account'
let requestGeneration = 0

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
  requestGeneration++
  clearFusionPreferences()
  try { sessionStorage.removeItem(SESSION_ACCOUNT_KEY) } catch { /* Storage may be unavailable. */ }
  auth.username = null
  auth.csrfToken = null
  auth.loaded = true
  auth.error = null
  invalidateSessionData()
}

function accept(payload: SessionPayload) {
  const identityChanged = auth.username !== payload.username
  try {
    if (sessionStorage.getItem(SESSION_ACCOUNT_KEY) !== payload.username) clearFusionPreferences()
    sessionStorage.setItem(SESSION_ACCOUNT_KEY, payload.username)
  } catch { /* Storage may be unavailable. */ }
  auth.username = payload.username
  auth.csrfToken = payload.csrf_token
  auth.loaded = true
  auth.error = null
  if (identityChanged) invalidateSessionData()
}

async function sessionPayload(response: Response): Promise<SessionPayload> {
  try {
    const value = await response.json() as Partial<SessionPayload>
    if (typeof value.username !== 'string' || !value.username || typeof value.csrf_token !== 'string' || !value.csrf_token) {
      throw new Error('Invalid session')
    }
    return value as SessionPayload
  } catch {
    throw new ApiRequestError(response.status, 'INVALID_RESPONSE', '登录服务返回了无效数据，请稍后重试。', false, null)
  }
}

function sessionChanged() {
  return new ApiRequestError(0, 'SESSION_CHANGED', '登录状态已改变，请重新操作。', false, null)
}

export async function loadSession(force = false): Promise<boolean> {
  if (auth.loaded && !force) return auth.username !== null
  const ownRequest = ++requestGeneration
  const epoch = sessionEpoch.value
  try {
    const response = await fetch('/auth/session', { credentials: 'include', cache: 'no-store' })
    if (ownRequest !== requestGeneration || !isSessionCurrent(epoch)) return auth.username !== null
    if (!response.ok) {
      clearSession()
      if (response.status !== 401) auth.error = '登录状态检查失败，请稍后重试。'
      return false
    }
    const payload = await sessionPayload(response)
    if (ownRequest !== requestGeneration || !isSessionCurrent(epoch)) return auth.username !== null
    accept(payload)
    return true
  } catch {
    if (ownRequest !== requestGeneration || !isSessionCurrent(epoch)) return auth.username !== null
    clearSession()
    auth.error = '无法连接登录服务，请检查网络后重试。'
    return false
  }
}

export async function login(username: string, password: string): Promise<void> {
  const ownRequest = ++requestGeneration
  const epoch = sessionEpoch.value
  let response: Response
  try {
    response = await fetch('/auth/login', {
      method: 'POST', credentials: 'include', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
  } catch {
    if (ownRequest !== requestGeneration || !isSessionCurrent(epoch)) throw sessionChanged()
    throw new ApiRequestError(0, 'NETWORK_UNAVAILABLE', '无法连接登录服务，请检查网络后重试。', true, null)
  }
  if (ownRequest !== requestGeneration || !isSessionCurrent(epoch)) throw sessionChanged()
  if (!response.ok) {
    throw await normalizeApiError(response)
  }
  const payload = await sessionPayload(response)
  if (ownRequest !== requestGeneration || !isSessionCurrent(epoch)) throw sessionChanged()
  accept(payload)
}

export async function logout(): Promise<void> {
  if (!auth.csrfToken) { clearSession(); return }
  const epoch = sessionEpoch.value
  const ownRequest = ++requestGeneration
  try {
    const response = await fetch('/auth/logout', {
      method: 'POST', credentials: 'include', cache: 'no-store',
      headers: { 'X-CSRF-Token': auth.csrfToken },
    })
    if (!isSessionCurrent(epoch) || ownRequest !== requestGeneration) return
    if (!response.ok && response.status !== 401) {
      const error = await normalizeApiError(response)
      if (!isSessionCurrent(epoch) || ownRequest !== requestGeneration) return
      throw error
    }
    clearSession()
  } catch (cause) {
    if (!isSessionCurrent(epoch) || ownRequest !== requestGeneration) return
    if (cause instanceof ApiRequestError) throw cause
    throw new ApiRequestError(0, 'NETWORK_UNAVAILABLE', '无法连接登录服务，请检查网络后重试。', true, null)
  }
}
