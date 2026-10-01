import type { JobRecord } from './types'

/** Only stable error codes and HTTP status determine user-facing text. */
const messages: Record<string, string> = {
  INVALID_CREDENTIALS: '用户名或密码不正确，请重新输入。',
  LOGIN_RATE_LIMITED: '尝试次数过多，请稍后再试。',
  ACCOUNT_UNAVAILABLE: '当前账号暂不可用，请联系管理员确认。',
  UNAUTHENTICATED: '未认证或登录已失效，请重新登录。',
  CSRF_REJECTED: '请求被安全校验拒绝，请刷新页面后重试。',
  ORIGIN_REJECTED: '请求来源被拒绝，请从正确的站点入口访问。',
  INVALID_REQUEST: '请求内容不符合要求，请检查填写内容。',
  INPUT_EXPIRED: '原始影像已到期，请新建病例并重新上传。',
  ASSET_EXPIRED: '图层资产已到期，无法重新加载。',
  INPUT_TOO_LARGE: '影像文件过大，请上传不超过 20 MiB 的单切片 DICOM。',
  UNSUPPORTED_INPUT_KIND: '当前仅支持单切片 CT DICOM 文件。',
  UNSUPPORTED_DICOM: '该 DICOM 格式暂不受支持，请检查影像格式。',
  INVALID_DICOM: '影像文件无效，请选择有效的单切片 CT DICOM。',
  INVALID_DICOM_DIMENSIONS: '影像尺寸不符合要求，请选择符合要求的单切片 CT DICOM。',
  DICOM_NOT_DEIDENTIFIED: '影像未通过去标识检查，请先完成去标识。',
  CASE_ALREADY_HAS_INPUT: '该病例已有影像，请使用现有影像或新建病例。',
  IDEMPOTENCY_CONFLICT: '请求与之前的提交冲突，请先确认已有病例或任务。',
  BACKEND_UNAVAILABLE: '服务暂时不可用，请稍后重新查询。',
  MODEL_UNAVAILABLE: '模型暂时不可用，请联系维护者确认服务状态。',
  REQUEST_TIMEOUT: '请求超时，请重新查询；已提交的任务可能仍在运行。',
  NETWORK_UNAVAILABLE: '无法连接服务，请检查网络后重新查询。',
  INVALID_RESPONSE: '服务响应格式异常，请稍后重试或联系维护者。',
  INVALID_DICOM_RESPONSE: '服务返回的影像格式无效，请重新加载或联系维护者。',
  INVALID_ASSET: '服务返回的图层格式无效，请重新加载或联系维护者。',
  CASE_NOT_FOUND: '病例不存在或当前账号不可访问，请确认链接和账号。',
  JOB_NOT_FOUND: '任务不存在或当前账号不可访问，请确认链接和账号。',
  RESULT_NOT_FOUND: '结果不存在或当前账号不可访问，请确认链接和账号。',
  SESSION_CHANGED: '登录状态已改变，请重新操作。',
}

function messageFor(status: number, code: string): string {
  // Authentication and visibility semantics take precedence over body fields.
  if (status === 401) return code === 'INVALID_CREDENTIALS' ? messages.INVALID_CREDENTIALS! : messages.UNAUTHENTICATED!
  if (status === 403) return code === 'CSRF_REJECTED' ? messages.CSRF_REJECTED!
    : code === 'ORIGIN_REJECTED' ? messages.ORIGIN_REJECTED! : '请求被拒绝，请刷新页面或联系维护者检查访问权限。'
  if (status === 404) return '资源不存在或当前账号不可访问，请确认链接和账号。'
  if (status === 410) return code === 'INPUT_EXPIRED' ? messages.INPUT_EXPIRED! : '原图或资产已到期，无法重新加载。'
  if (messages[code]) return messages[code]!
  if (status === 422 || status === 400) return messages.INVALID_REQUEST!
  if (status === 409) return '请求与当前资源状态冲突，请刷新并确认已有病例或任务。'
  if (status === 413) return messages.INPUT_TOO_LARGE!
  if (status === 415) return messages.UNSUPPORTED_INPUT_KIND!
  if (status === 408) return messages.REQUEST_TIMEOUT!
  if (status === 429) return '请求过于频繁，请稍后重试。'
  if (status >= 500) return messages.BACKEND_UNAVAILABLE!
  return '请求失败，请稍后重试或联系维护者。'
}

export class ApiRequestError extends Error {
  readonly status: number
  readonly code: string
  readonly retryable: boolean
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, retryable: boolean, requestId: string | null) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.code = code
    this.retryable = retryable
    this.requestId = requestId
  }
}

function safeRequestId(value: unknown): string | null {
  return typeof value === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(value) ? value : null
}

export async function normalizeApiError(response: Response): Promise<ApiRequestError> {
  let body: Record<string, unknown> = {}
  try {
    const parsed: unknown = await response.json()
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) body = parsed as Record<string, unknown>
  } catch { /* Proxies may return HTML, empty responses, or malformed JSON. */ }
  const code = typeof body.code === 'string' && /^[A-Z][A-Z0-9_]{0,63}$/.test(body.code)
    ? body.code : response.status === 422 ? 'INVALID_REQUEST' : `HTTP_${response.status}`
  const transient = response.status === 408 || response.status === 429 || response.status >= 500
  return new ApiRequestError(response.status, code, messageFor(response.status, code),
    transient && body.retryable !== false, safeRequestId(body.request_id))
}

export function errorText(cause: unknown): string {
  if (cause instanceof ApiRequestError) {
    const text = messageFor(cause.status, cause.code)
    const requestId = safeRequestId(cause.requestId)
    return requestId ? `${text} 请求编号：${requestId}` : text
  }
  return '操作未完成，请重试或联系维护者。'
}

export interface JobFailureDescription {
  code: string
  title: string
  message: string
  action: 'new-case' | 'case' | 'support'
  actionLabel: string
}

/** A failed Job is a recorded terminal state, never a transport retry instruction. */
export function describeJobFailure(job: JobRecord): JobFailureDescription {
  const code = job.error?.code || job.failure_reason
  if (code === 'INPUT_EXPIRED') return {
    code: 'INPUT_EXPIRED', title: '任务失败：原始影像已到期',
    message: '请新建病例并重新上传影像，再创建新任务。此失败记录会保留。',
    action: 'new-case', actionLabel: '新建病例',
  }
  if (code === 'INFERENCE_FAILED') return {
    code: 'INFERENCE_FAILED', title: '任务失败：推理未完成',
    message: '请将下方 Job ID 提供给维护者核查。服务恢复后，可返回病例页显式创建新任务；当前失败记录会保留，不会自动重试。',
    action: 'support', actionLabel: '返回病例页',
  }
  if (code === 'LEASE_EXPIRED') return {
    code: 'LEASE_EXPIRED', title: '任务失败：处理节点未及时响应',
    message: '本次任务已结束，请将下方 Job ID 提供给维护者核查。服务恢复后，可返回病例页创建新任务；当前失败记录会保留，不会自动重试。',
    action: 'support', actionLabel: '返回病例页',
  }
  return {
    code: 'UNKNOWN_JOB_FAILURE', title: '任务失败',
    message: '任务未完成，请将下方 Job ID 提供给维护者确认原因和后续处理。此失败记录会保留，不会自动重试。',
    action: 'support', actionLabel: '返回病例页',
  }
}
