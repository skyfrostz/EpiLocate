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
}

export class ApiClient {
  private readonly baseUrl: string
  private readonly fetcher: typeof fetch

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE).replace(/\/$/, '')
    this.fetcher = options.fetcher ?? fetch
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response: Response
    try {
      response = await this.fetcher(`${this.baseUrl}${path}`, {
        credentials: 'include',
        ...init,
        headers: { Accept: 'application/json', ...init.headers },
      })
    } catch {
      throw new ApiRequestError(0, 'NETWORK_UNAVAILABLE', '无法连接 API，请检查网络或服务状态。', true, null)
    }
    if (!response.ok) {
      let body: Partial<ApiErrorBody> = {}
      try {
        body = (await response.json()) as Partial<ApiErrorBody>
      } catch {
        // A gateway error may not have a JSON body.
      }
      throw new ApiRequestError(
        response.status,
        typeof body.code === 'string' ? body.code : `HTTP_${response.status}`,
        typeof body.message === 'string' ? body.message : '请求失败，请稍后重试。',
        body.retryable === true,
        typeof body.request_id === 'string' ? body.request_id : null,
      )
    }
    if (response.status === 204) return undefined as T
    const contentType = response.headers.get('content-type') ?? ''
    if (!contentType.includes('application/json')) {
      throw new ApiRequestError(response.status, 'INVALID_RESPONSE', 'API 返回了非 JSON 数据。', false, null)
    }
    return (await response.json()) as T
  }

  listCases(cursor?: string, limit = 30): Promise<CaseListResponse> {
    const query = new URLSearchParams({ limit: String(limit) })
    if (cursor) query.set('cursor', cursor)
    return this.request(`/cases?${query}`)
  }

  getCase(caseId: string): Promise<CaseDetail> {
    return this.request(`/cases/${encodeURIComponent(caseId)}`)
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

  getPrediction(predictionId: string): Promise<PredictionJob> {
    return this.request(`/predictions/${encodeURIComponent(predictionId)}`)
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

  getJob(jobId: string): Promise<JobRecord> {
    return this.request(`/jobs/${encodeURIComponent(jobId)}`)
  }

  getResult(resultId: string): Promise<ResultRecord> {
    return this.request(`/results/${encodeURIComponent(resultId)}`)
  }

  getPositions(resultId: string, scale: 16 | 32 | 64, cursor?: string, limit = 100): Promise<PositionsPage> {
    const query = new URLSearchParams({ scale: String(scale), limit: String(limit) })
    if (cursor) query.set('cursor', cursor)
    return this.request(`/results/${encodeURIComponent(resultId)}/positions?${query}`)
  }

  async getResultAsset(resultId: string, assetId: string): Promise<Blob> {
    let response: Response
    try {
      response = await this.fetcher(
        `${this.baseUrl}/results/${encodeURIComponent(resultId)}/assets/${encodeURIComponent(assetId)}`,
        { credentials: 'include' },
      )
    } catch {
      throw new ApiRequestError(0, 'NETWORK_UNAVAILABLE', '无法连接 API，请检查网络或服务状态。', true, null)
    }
    if (!response.ok) throw new ApiRequestError(response.status, `HTTP_${response.status}`, '影像资产读取失败。', false, null)
    return response.blob()
  }
}

export const apiClient = new ApiClient()
