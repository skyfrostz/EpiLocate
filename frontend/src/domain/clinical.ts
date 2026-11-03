import type { CaseStatus, JobStatus } from '../api/types'
export type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'
export interface StatusLabel { label: string; tone: Tone }
export function inputStatus(status: CaseStatus | string): StatusLabel {
  const values: Record<string, StatusLabel> = { CREATED: { label:'待上传', tone:'neutral' }, READY:{ label:'输入可用', tone:'success' }, EXPIRED:{ label:'输入已到期', tone:'warning' }, DELETING:{ label:'删除中', tone:'neutral' } }
  return (Object.hasOwn(values, status) ? values[status] : undefined) ?? { label:'状态未知', tone:'neutral' }
}
export function jobStatus(status: JobStatus | string): StatusLabel {
  const values: Record<string, StatusLabel> = { CREATED:{label:'已创建',tone:'neutral'},QUEUED:{label:'排队中',tone:'warning'},RUNNING:{label:'分析中',tone:'info'},COMPLETED:{label:'任务已完成',tone:'success'},FAILED:{label:'分析未完成',tone:'danger'} }
  return (Object.hasOwn(values, status) ? values[status] : undefined) ?? {label:'状态未知',tone:'neutral'}
}
export function safeProgress(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1 ? Math.round(value * 100) : null
}
export function shortId(value: string) { return value.length > 28 ? `${value.slice(0,15)}…${value.slice(-8)}` : value }
// Reserved integration boundary: only a future server-authorized capability payload may enable details.
export function canSeeSystemDetails(capabilities: unknown) { return Array.isArray(capabilities) && capabilities.includes('system:read') }
export function telemetryState(sample: {state:string;observedAt:number;ttlMs:number} | null, now = Date.now()) {
  if (!sample) return 'not_integrated'
  if (!Number.isFinite(sample.observedAt) || !Number.isFinite(sample.ttlMs) || sample.ttlMs <= 0 || sample.observedAt > now + 5000) return 'unknown'
  if (now - sample.observedAt > sample.ttlMs) return 'stale'
  return ['healthy','degraded','offline','unknown','not_integrated'].includes(sample.state) ? sample.state : 'unknown'
}
