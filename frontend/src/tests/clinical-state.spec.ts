import { describe, expect, it } from 'vitest'
import { inputStatus, jobStatus, safeProgress, telemetryState, canSeeSystemDetails } from '../domain/clinical'
describe('truthful Clinical Canvas state', () => {
  it('READY means input availability only', () => expect(inputStatus('READY').label).toBe('输入可用'))
  it('unknown cases/jobs stay unknown', () => { expect(inputStatus('new').tone).toBe('neutral'); expect(jobStatus('new').label).toBe('状态未知') })
  it('completed job wording does not assert full case analysis', () => expect(jobStatus('COMPLETED').label).toBe('任务已完成'))
  it.each([null, undefined, NaN, Infinity, -1, 1.1, '0.5'])('rejects unknown or invalid progress %s', value => expect(safeProgress(value)).toBeNull())
  it('uses only valid measured progress', () => { expect(safeProgress(0)).toBe(0); expect(safeProgress(.52)).toBe(52); expect(safeProgress(1)).toBe(100) })
  it('missing telemetry is not integrated', () => expect(telemetryState(null)).toBe('not_integrated'))
  it('stale or malformed samples cannot report healthy', () => { expect(telemetryState({state:'healthy',observedAt:1,ttlMs:10},100)).toBe('stale'); expect(telemetryState({state:'healthy',observedAt:NaN,ttlMs:10},100)).toBe('unknown'); expect(telemetryState({state:'healthy',observedAt:10000,ttlMs:10},100)).toBe('unknown') })
  it('usernames do not authorize details', () => { expect(canSeeSystemDetails('admin')).toBe(false); expect(canSeeSystemDetails(undefined)).toBe(false); expect(canSeeSystemDetails(['system:read'])).toBe(true) })
})
