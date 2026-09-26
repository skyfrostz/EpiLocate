import type {
  AcceptedJob,
  ApiErrorBody,
  CaseDetail,
  CaseListResponse,
  CreatedCase,
  JobRecord,
  PositionsPage,
  PredictionJob,
  ResultRecord,
  UploadedCase,
} from './types'

const DEFAULT_BASE = '/api/v2'

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

export interface ApiClientOptions {
  baseUrl?: string
  fetcher?: typeof fetch
  timeoutMs?: number
}

export class ApiClient {
  private readonly baseUrl: string
  private readonly fetcher: typeof fetch
  private readonly timeoutMs: number

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE).replace(/\/$/, '')
    this.fetcher = options.fetcher ?? ((input, init) => fetch(input, init))
    this.timeoutMs = options.timeoutMs ?? 15000
  }

  private async send(path: string, init: RequestInit = {}): Promise<Response> {
    const timeout = AbortSignal.timeout(this.timeoutMs)
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout
    try {
      return await this.fetcher(`${this.baseUrl}${path}`, {
        credentials: 'include',
        ...init,
        signal,
        headers: { Accept: 'application/json', ...init.headers },
      })
    } catch (error) {
      if (init.signal?.aborted) throw error
      if (timeout.aborted) {
        throw new ApiRequestError(0, 'REQUEST_TIMEOUT', 'API 请求超时，请重试。', true, null)
      }
      throw new ApiRequestError(0, 'NETWORK_UNAVAILABLE', '无法连接 API，请检查网络或服务状态。', true, null)
    }
  }

  private async assertOk(response: Response): Promise<void> {
    if (response.ok) return
    let body: Partial<ApiErrorBody> = {}
    try {
      body = (await response.json()) as Partial<ApiErrorBody>
    } catch {
      // Reverse proxies can return non-JSON errors.
    }
    throw new ApiRequestError(
      response.status,
      typeof body.code === 'string' ? body.code : `HTTP_${response.status}`,
      response.status === 401 ? '未认证或登录已失效，请联系部署管理员。' :
        typeof body.message === 'string' ? body.message : '请求失败，请稍后重试。',
      body.retryable === true,
      typeof body.request_id === 'string' ? body.request_id : null,
    )
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.send(path, init)
    await this.assertOk(response)
    if (response.status === 204) return undefined as T
    if (!(response.headers.get('content-type') ?? '').includes('application/json')) {
      throw new ApiRequestError(response.status, 'INVALID_RESPONSE', 'API 返回了非 JSON 数据。', false, null)
    }
    try {
      return (await response.json()) as T
    } catch {
      throw new ApiRequestError(response.status, 'INVALID_RESPONSE', 'API 返回了无效 JSON。', false, null)
    }
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
    const response = await this.send(`/cases/${encodeURIComponent(caseId)}/dicom`, { signal })
    await this.assertOk(response)
    if (!(response.headers.get('content-type') ?? '').includes('application/dicom')) {
      throw new ApiRequestError(response.status, 'INVALID_DICOM', 'API 返回的影像格式无效。', false, null)
    }
    return response.blob()
  }

  createCase(patientId: string | null, idempotencyKey: string): Promise<CreatedCase> {
    return this.request('/cases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({ patient_id: patientId }),
    })
  }

  uploadCase(caseId: string, file: File, idempotencyKey: string): Promise<UploadedCase> {
    const body = new FormData()
    body.set('input_kind', 'dicom_series')
    body.set('file', file, 'slice.dcm')
    return this.request(`/cases/${encodeURIComponent(caseId)}/upload`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body,
    })
  }

  createPrediction(caseId: string, sliceId: string, modelId: string, idempotencyKey: string): Promise<AcceptedJob> {
    return this.request('/predictions', {
      method: 'POST',
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
  ): Promise<AcceptedJob> {
    return this.request('/jobs/occlusion', {
      method: 'POST',
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
    const response = await this.send(`/results/${encodeURIComponent(resultId)}/assets/${encodeURIComponent(assetId)}`, { signal })
    await this.assertOk(response)
    if (!(response.headers.get('content-type') ?? '').includes('image/png')) {
      throw new ApiRequestError(response.status, 'INVALID_ASSET', '响应图资产格式无效。', false, null)
    }
    return response.blob()
  }
}

export const apiClient = new ApiClient()
