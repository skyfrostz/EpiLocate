/** Public fields fixed by Backend API Contract v2.0 Freeze. */
export type CaseStatus = 'CREATED' | 'READY' | 'EXPIRED' | 'DELETING'
export type JobStatus = 'CREATED' | 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'
export type JobKind = 'PREDICTION' | 'OCCLUSION'

export interface ApiErrorBody {
  code: string
  message: string
  retryable: boolean
  request_id: string
  details: Record<string, unknown>
}

export interface CaseSummary {
  case_id: string
  patient_id: string
  status: CaseStatus
  created_at: string
  input_expires_at: string | null
}

export interface SliceRecord {
  slice_id: string
  ordinal: number
  width_px: number
  height_px: number
}

export interface SeriesRecord {
  series_id: string
  slices: SliceRecord[]
}

export interface StudyRecord {
  study_id: string
  series: SeriesRecord[]
}

export interface CaseDetail extends CaseSummary {
  studies: StudyRecord[]
}

export interface CaseListResponse {
  items: CaseSummary[]
  next_cursor: string | null
}

export interface CreatedCase {
  case_id: string
  patient_id: string
  status: 'CREATED'
  created_at: string
}

export interface UploadedCase {
  case_id: string
  study_id: string
  series_id: string
  slice_id: string
  status: 'READY'
  input_expires_at: string
}

export interface JobError {
  code: string
  message: string
}

export interface JobRecord {
  job_id: string
  kind: JobKind
  case_id: string
  status: JobStatus
  attempt_no: number
  retry_count: number
  lease_expire_time: string | null
  last_heartbeat: string | null
  failure_reason: string | null
  progress: number | null
  estimated_remaining_time_ms: number | null
  result_id: string | null
  error: JobError | null
  created_at: string
  finished_at: string | null
}

export interface AcceptedJob {
  job_id: string
  case_id: string
  status: 'CREATED'
  status_url: string
  prediction_id?: string
}

export interface PredictionValues {
  predicted_class: 0 | 1
  class_label: string
  positive_probability: number
  predicted_class_confidence: number
  inference_time_ms: number
}

export interface Prediction extends PredictionValues {
  model_version: string
  preprocessing_version: string
  source: 'LIVE_CASE'
}

export interface PredictionJob {
  prediction_id: string
  job_id: string
  status: JobStatus
  result_id: string | null
  prediction: Prediction | null
  error: JobError | null
}

export interface HeatmapLayer {
  asset_id: string
  layer_kind: 'CANDIDATE_RESPONSE' | 'CANDIDATE_TOP10' | 'COMPARISON_GRID'
  width: number
  height: number
  coordinate_space: 'ALGORITHM_224' | 'COMPARISON_14' | 'RAW_PIXEL_EDGE'
  value_min: number
  value_max: number
  origin: 'TOP_LEFT_PIXEL_EDGE'
  x_axis: 'RIGHT'
  y_axis: 'DOWN'
  display_interpolation_only: boolean
}

export interface ScaleSummary {
  block_size: 16 | 32 | 64
  stride: 8 | 16 | 32
  fill: 0.5
  baseline_positive_probability: number
  median_absolute_probability_change: number
  flip_rate: number
  candidate_status: 'valid' | 'insufficient_positive_response'
  candidate_area_fraction: number | null
  response_layer: HeatmapLayer | null
  candidate_layer: HeatmapLayer | null
  comparison_grid_layer: HeatmapLayer | null
}

export interface ResultAsset {
  asset_id: string
  layer_kind: string
  width: number
  height: number
  coordinate_space: string
  media_type: string
}

export interface ResultRecord {
  result_id: string
  job_id: string
  case_id: string
  slice_id: string
  kind: JobKind
  contract_version: '2.0'
  source: 'LIVE_CASE'
  status: 'COMPLETED'
  model_id: string
  model_version: string
  preprocessing_version: string
  protocol_id: string
  prediction: PredictionValues | null
  scale_summaries: ScaleSummary[]
  cross_scale: unknown[]
  provenance: Record<string, unknown>
  assets: ResultAsset[]
  created_at: string
}

export interface PositionsPage {
  result_id: string
  scale: 16 | 32 | 64
  positions: unknown[]
  next_cursor: string | null
}
