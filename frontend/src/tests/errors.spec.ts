import { describe, expect, it } from 'vitest'
import { ApiRequestError, describeJobFailure, errorText, normalizeApiError } from '../api/errors'
import type { JobRecord } from '../api/types'

const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status })

describe('safe error normalization', () => {
  it('handles code-only Gateway and full Backend errors without exposing internal message or details', async () => {
    const gateway = await normalizeApiError(json({ code: 'CSRF_REJECTED' }, 403))
    expect(gateway.message).toContain('安全校验')
    const backend = await normalizeApiError(json({ code: 'INPUT_EXPIRED', message: '/private/patient.dcm',
      details: { secret: 'token' }, request_id: 'req-123', retryable: true }, 410))
    expect(errorText(backend)).toContain('新建病例')
    expect(errorText(backend)).toContain('req-123')
    expect(errorText(backend)).not.toContain('private')
    expect(backend.retryable).toBe(false)
  })

  it('accepts FastAPI detail, missing fields, scalar JSON, invalid JSON and HTML safely', async () => {
    const invalid = await normalizeApiError(json({ detail: [{ input: 'secret-password', msg: 'raw exception' }] }, 422))
    expect(invalid.code).toBe('INVALID_REQUEST')
    expect(invalid.message).toContain('检查填写')
    expect(invalid.message).not.toContain('password')
    for (const response of [json({}, 503), json(null, 503), json('private', 503), new Response('<h1>internal</h1>', { status: 503 })]) {
      const error = await normalizeApiError(response)
      expect(error.message).toContain('服务暂时不可用')
      expect(error.retryable).toBe(true)
    }
  })

  it('prioritizes HTTP authorization and visibility semantics over inconsistent codes', async () => {
    expect((await normalizeApiError(json({ code: 'MODEL_UNAVAILABLE' }, 401))).message).toContain('重新登录')
    expect((await normalizeApiError(json({ code: 'INPUT_EXPIRED' }, 404))).message).toContain('不可访问')
    expect((await normalizeApiError(json({ code: 'INVALID_CREDENTIALS' }, 401))).message).toContain('用户名或密码')
    expect((await normalizeApiError(json({}, 410))).message).toContain('到期')
  })

  it('bounds request identifiers and never forwards arbitrary thrown error messages', async () => {
    for (const request_id of ['https://private/path?token=secret', 'x'.repeat(101), 'patient\nsecret', 123]) {
      expect((await normalizeApiError(json({ request_id }, 500))).requestId).toBeNull()
    }
    expect(errorText(new Error('/private/token'))).not.toContain('token')
    expect(errorText(new ApiRequestError(500, 'UNKNOWN_CODE', '/private/token', true, 'req-ok'))).toContain('req-ok')
    expect(errorText(new ApiRequestError(0, 'REQUEST_TIMEOUT', 'private', true, null))).toContain('仍在运行')
  })

  it('keeps Job failure guidance independent from HTTP retry flags and unsafe error strings', () => {
    const job = { error: { code: 'INPUT_EXPIRED', message: 'private' }, failure_reason: 'private' } as JobRecord
    expect(describeJobFailure(job).action).toBe('new-case')
    job.error!.code = 'INFERENCE_FAILED'
    expect(describeJobFailure(job).action).toBe('support')
    expect(describeJobFailure(job).message).toContain('不会自动重试')
    job.error!.code = 'RAW_PRIVATE_EXCEPTION'
    expect(describeJobFailure(job).code).toBe('UNKNOWN_JOB_FAILURE')
    expect(describeJobFailure(job).message).not.toContain('private')
    job.error = null
    job.failure_reason = 'INPUT_EXPIRED'
    expect(describeJobFailure(job).action).toBe('new-case')
  })
})
