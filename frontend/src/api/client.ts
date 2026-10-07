import type {
  AcceptedJob,
  CaseDetail,
  CaseListResponse,
  CreatedCase,
  JobRecord,
  PositionsPage,
  PredictionJob,
  ResultRecord,
  UploadedCase,
} from './types'
import { auth, clearSession, waitForSessionVerification } from '../auth/session'
import { isSessionCurrent, sessionEpoch } from '../auth/lifecycle'
import { ApiRequestError, normalizeApiError } from './errors'
export { ApiRequestError } from './errors'

const DEFAULT_BASE = '/api/v2'

export interface ApiClientOptions {
  baseUrl?: string
  fetcher?: typeof fetch
  timeoutMs?: number
}

interface ResponseContext {
  timeout: AbortSignal
  callerSignal?: AbortSignal | null
}

export class ApiClient {
  private readonly baseUrl: string
  private readonly fetcher: typeof fetch
  private readonly timeoutMs: number
  private readonly responseContexts = new WeakMap<Response, ResponseContext>()

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE).replace(/\/$/, '')
    this.fetcher = options.fetcher ?? ((input, init) => fetch(input, init))
    this.timeoutMs = options.timeoutMs ?? 15000
  }

  private async send(path: string, init: RequestInit = {}): Promise<Response> {
    if (!auth.loaded) throw new ApiRequestError(0, 'SESSION_CHANGED', '正在确认登录状态，请稍后重新操作。', false, null)
    const epoch = sessionEpoch.value
    await this.assertVerifiedSession(epoch)
    init.signal?.throwIfAborted()
    const timeout = AbortSignal.timeout(this.timeoutMs)
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout
    try {
      const response = await this.fetcher(`${this.baseUrl}${path}`, {
        credentials: 'include',
        ...init,
        signal,
        headers: {
          Accept: 'application/json', ...init.headers,
          ...(init.method && init.method !== 'GET' && auth.csrfToken ? { 'X-CSRF-Token': auth.csrfToken } : {}),
        },
      })
      this.responseContexts.set(response, { timeout, callerSignal: init.signal })
      await this.assertVerifiedSession(epoch)
      return response
    } catch (error) {
      await this.assertVerifiedSession(epoch)
      throw this.transportError(error, { timeout, callerSignal: init.signal })
    }
  }

  private transportError(error: unknown, context?: ResponseContext): unknown {
    if (error instanceof ApiRequestError) return error
    if (context?.callerSignal?.aborted) return error
    if (context?.timeout.aborted) {
      return new ApiRequestError(0, 'REQUEST_TIMEOUT', 'API 请求超时，请重试。', true, null)
    }
    return new ApiRequestError(0, 'NETWORK_UNAVAILABLE', '无法连接 API，请检查网络或服务状态。', true, null)
  }

  private async assertVerifiedSession(epoch: number) {
    await waitForSessionVerification()
    this.assertSession(epoch)
  }

  private async readBody<T>(response: Response, epoch: number, read: () => Promise<T>): Promise<T> {
    try {
      const value = await read()
      await this.assertVerifiedSession(epoch)
      return value
    } catch (error) {
      await this.assertVerifiedSession(epoch)
      const context = this.responseContexts.get(response)
      if (!context?.timeout.aborted && !context?.callerSignal?.aborted && error instanceof SyntaxError) {
        throw new ApiRequestError(response.status, 'INVALID_RESPONSE', 'API 返回了无效 JSON。', false, null)
      }
      throw this.transportError(error, context)
    }
  }

  private assertSession(epoch: number) {
    if (!isSessionCurrent(epoch)) {
      throw new ApiRequestError(0, 'SESSION_CHANGED', '登录状态已改变，请重新操作。', false, null)
    }
  }

  private async assertOk(response: Response, epoch: number): Promise<void> {
    await this.assertVerifiedSession(epoch)
    if (response.ok) return
    if (response.status === 401) {
      clearSession()
      auth.error = '未认证或登录已失效，请重新登录。'
    }
    const errorEpoch = sessionEpoch.value
    const error = await normalizeApiError(response)
    await this.assertVerifiedSession(errorEpoch)
    const context = this.responseContexts.get(response)
    if (response.status !== 401 && (context?.timeout.aborted || context?.callerSignal?.aborted)) {
      throw this.transportError(context.callerSignal?.reason ?? context.timeout.reason, context)
    }
    throw error
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const epoch = sessionEpoch.value
    const response = await this.send(path, init)
    await this.assertOk(response, epoch)
    if (response.status === 204) return undefined as T
    if (!(response.headers.get('content-type') ?? '').includes('application/json')) {
      throw new ApiRequestError(response.status, 'INVALID_RESPONSE', 'API 返回了非 JSON 数据。', false, null)
    }
    return this.readBody(response, epoch, () => response.json() as Promise<T>)
  }

  listCases(cursor?: string, limit = 30, signal?: AbortSignal): Promise<CaseListResponse> {
    const query = new URLSearchParams({ limit: String(limit) })
    if (cursor) query.set('cursor', cursor)
    return this.request(`/cases?${query}`, { signal })
  }

  getCase(caseId: string, signal?: AbortSignal): Promise<CaseDetail> {
    return this.request(`/cases/${encodeURIComponent(caseId)}`, { signal })
  }

  async getCaseDicom(caseId: string, signal?: AbortSignal): Promise<Blob> {
    const epoch = sessionEpoch.value
    const response = await this.send(`/cases/${encodeURIComponent(caseId)}/dicom`, { signal })
    await this.assertOk(response, epoch)
    if (!(response.headers.get('content-type') ?? '').includes('application/dicom')) {
      throw new ApiRequestError(response.status, 'INVALID_DICOM', 'API 返回的影像格式无效。', false, null)
    }
    return this.readBody(response, epoch, () => response.blob())
  }

  createCase(patientId: string | null, idempotencyKey: string): Promise<CreatedCase> {
    return this.request('/cases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({ patient_id: patientId }),
    })
  }

  uploadCase(caseId: string, file: File, idempotencyKey: string, signal?: AbortSignal): Promise<UploadedCase> {
    const body = new FormData()
    body.set('input_kind', 'dicom_series')
    body.set('file', file, 'slice.dcm')
    return this.request(`/cases/${encodeURIComponent(caseId)}/upload`, {
      method: 'POST', signal,
      headers: { 'Idempotency-Key': idempotencyKey },
      body,
    })
  }

  createPrediction(caseId: string, sliceId: string, modelId: string, idempotencyKey: string, signal?: AbortSignal): Promise<AcceptedJob> {
    return this.request('/predictions', {
      method: 'POST', signal,
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({ case_id: caseId, slice_id: sliceId, model_id: modelId }),
    })
  }

  getPrediction(predictionId: string, signal?: AbortSignal): Promise<PredictionJob> {
    return this.request(`/predictions/${encodeURIComponent(predictionId)}`, { signal })
  }

  createOcclusion(
    caseId: string,
    sliceId: string,
    modelId: string,
    protocolId: string,
    scales: Array<16 | 32 | 64>,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<AcceptedJob> {
    return this.request('/jobs/occlusion', {
      method: 'POST', signal,
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({ case_id: caseId, slice_id: sliceId, model_id: modelId, protocol_id: protocolId, scales }),
    })
  }

  getJob(jobId: string, signal?: AbortSignal): Promise<JobRecord> {
    return this.request(`/jobs/${encodeURIComponent(jobId)}`, { signal })
  }

  getResult(resultId: string, signal?: AbortSignal): Promise<ResultRecord> {
    return this.request(`/results/${encodeURIComponent(resultId)}`, { signal })
  }

  getPositions(resultId: string, scale: 16 | 32 | 64, cursor?: string, limit = 100, signal?: AbortSignal): Promise<PositionsPage> {
    const query = new URLSearchParams({ scale: String(scale), limit: String(limit) })
    if (cursor) query.set('cursor', cursor)
    return this.request(`/results/${encodeURIComponent(resultId)}/positions?${query}`, { signal })
  }

  async getResultAsset(resultId: string, assetId: string, signal?: AbortSignal): Promise<Blob> {
    const epoch = sessionEpoch.value
    const response = await this.send(`/results/${encodeURIComponent(resultId)}/assets/${encodeURIComponent(assetId)}`, { signal })
    await this.assertOk(response, epoch)
    if (!(response.headers.get('content-type') ?? '').includes('image/png')) {
      throw new ApiRequestError(response.status, 'INVALID_ASSET', '响应图资产格式无效。', false, null)
    }
    return this.readBody(response, epoch, () => response.blob())
  }
}

export const apiClient = new ApiClient()
