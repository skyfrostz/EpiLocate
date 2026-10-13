import type { HeatmapLayer, ResultRecord } from './types'
export type AlgorithmTerminal = 'SUCCESS' | 'NO_RELIABLE_RESPONSE' | 'PARTIAL_BUDGET' | 'FAILED' | 'BLOCKED' | 'NOT RUN'
export interface ApplicationRequest {
  schema_version: 'EPI_NEXT_APPLICATION_REQUEST_V1'
  algorithm_mode: 'E2' | 'CTFM'
  method_mode: 'E2-CT' | 'CTFM-VOLUME-HEAD'
  algorithm_version: string
  config_sha256: string
  execution_mode: 'LIVE' | 'PRECOMPUTED' | 'SYNTHETIC'
  input: { case_id: string; study_id: string; series_id: string; slice_id: string; input_sha256: string; display_sha256: string; scope: 'SINGLE_SLICE' | 'VOLUME'; display_kind: 'DICOM' | 'RESEARCH_ARRAY'; source_identity_status: string; native_shape_zyx: [number,number,number]; model_shape: number[]; native_slice_index: number; affine_lps: number[][]; geometry_ledger_sha256: string; mapping_qa_sha256: string; mapping_verified: boolean }
  model: { model_id: string; checkpoint_sha256: string; preprocessing_version: string; protocol_id: string; preprocessing_sha256: string; encoder_sha256?: string | null; head_sha256?: string | null }
  task: { definition_id: string; unit: 'SLICE' | 'SOURCE_CASE_SELECTED_SERIES'; class_labels: string[]; target_class: number }
  budget: { forward: number; backward: number; updates: number; seconds: number; output_bytes: number }
}
export interface ApplicationLayer extends HeatmapLayer {
  display_sha256: string
  geometry_ledger_sha256: string
  mapping_qa_sha256: string
  native_slice_index: number
  evidence_type: string
  raw_values?: number[][] | null
}
export interface ApplicationResult {
  execution_status: AlgorithmTerminal
  algorithm_status: string
  reason: string | null
  prediction: { logits: number[]; predicted_class: number; class_label: string; probabilities: number[] | null } | null
  candidates: unknown[]
  layers: ApplicationLayer[]
  actual_forward: number
  actual_backward: number
  actual_updates: number
  runtime_seconds: number
  stop_events: unknown[]
  source_artifacts: Record<string,string>
  diagnostics: Record<string,unknown>
}
export function applicationIdentityValid(r: ResultRecord): boolean {
  const q=r.application_request, a=r.application
  return Boolean(q && a && r.kind==='ALGORITHM' && r.contract_version==='next-1' &&
    r.source===({LIVE:'LIVE_CASE',PRECOMPUTED:'PRECOMPUTED',SYNTHETIC:'SYNTHETIC'} as const)[q.execution_mode] &&
    q.input.case_id===r.case_id && q.input.slice_id===r.slice_id && q.model.model_id===r.model_id &&
    q.model.checkpoint_sha256===r.model_version && q.model.preprocessing_version===r.preprocessing_version &&
    q.model.protocol_id===r.protocol_id && ['SUCCESS','NO_RELIABLE_RESPONSE','PARTIAL_BUDGET','FAILED','BLOCKED','NOT RUN'].includes(a.execution_status))
}
