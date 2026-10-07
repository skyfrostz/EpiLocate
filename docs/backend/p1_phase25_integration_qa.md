# P1 Phase 2.5 Security Integration & Regression QA

Date: 2026-09-27. Scope: local integration QA on the isolated
`codex/p1-phase25-integration-qa` worktree. This is not public deployment or
OIDC acceptance.

## Baseline and merge

- Baseline: `p0/integration` at `91528fc07617d753d3582ab7d93ad617dbc7ad94`.
- Auth source: `feature/p1-auth-security` at `df50656237e2ed63f7b6f7612dc290fdd395bde0`.
- Merge-base: `91528fc07617d753d3582ab7d93ad617dbc7ad94`; the auth branch is
  one commit ahead. The isolated merge commit is `740e77c98e87ec3f81278116815195313a3678c5`
  with those two commits as parents. There were no merge conflicts.
- The merge touched Backend v2 authentication, credential model and migration,
  provisioning scripts, tests, and the Frontend deployment instructions. The
  Worker, Vue API client, FrozenBaseline, training code, checkpoint, and frozen
  validation outputs were not edited. The checkpoint still hashes to
  `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`.
- `feature/worker-v1` at `1f90321b7b6af9e2a69992c4259fd2dcf32944ed`
  descends from pinned Worker SHA `24d4fbf8674ce4f34070daebe006ea31ab13f647`.
  The Vue API client still targets the same `/api/v2` Case, Job, Result,
  DICOM, Positions, and Asset routes; the local server-side proxy supplied
  the new DB-backed User bearer without a client contract change.

## Migration compatibility

The auth commit changes the historical `0001_initial_schema.py` exclusion to
leave `user_credentials` for `0003`; `0002` remains the Result metadata and
Asset migration. Both paths reached `0003_user_credentials`:

1. Fresh PostgreSQL: empty database, `base -> head`.
2. Existing PostgreSQL: an isolated worktree at the *original* `91528fc`
   created `0002`, then stored one Case, Job, Result, and Asset; the integrated
   code upgraded `0002 -> 0003` without dropping those rows.

The resulting 15 business tables were identical across the two paths when
comparing columns, types, nullability, defaults, foreign keys, indexes, unique
constraints, and checks. `user_credentials` has its User FK and four indexes.
The existing Case/Job/Result/Asset counts remained one each. See
[`migration_compatibility.json`](../../qa/evidence/p1_phase25/migration_compatibility.json).
No corrective migration was required for the tested upgrade paths. The
historical migration's dynamic metadata dependency remains a maintenance risk;
schema changes must keep the exclusions aligned or move to explicit frozen DDL.

## Authentication and authorization

Two distinct users were provisioned from the database with one-time opaque
tokens in `0600` local files. The local Vite proxy held only User A's token in
an ignored `0600` file. No token value or token hash appears in the committed
evidence, browser output, or Vue bundle; the old environment-token bootstrap
was not enabled.

The real HTTP probe passed 29 checks. Owner reads returned 200. User B's
reads of Case and DICOM returned `404 CASE_NOT_FOUND`; Job and Prediction
returned `404 JOB_NOT_FOUND`; Result, Positions, and Heatmap Asset returned
`404 RESULT_NOT_FOUND`. A cross-user Prediction creation returned
`404 CASE_NOT_FOUND`. Missing, invalid, expired, and revoked credentials, plus
an inactive User, returned `401 UNAUTHENTICATED`. User bearer on Worker API
returned `401 WORKER_UNAUTHENTICATED`; Worker bearer on User API returned
`401 UNAUTHENTICATED`. Exact per-request statuses and codes are in
[`security_http_matrix.json`](../../qa/evidence/p1_phase25/security_http_matrix.json);
the executable probe is [`p1_phase25_security_probe.py`](../../qa/p1_phase25_security_probe.py).

## Real Worker and storage

The production-like stack used PostgreSQL 16 and a private MinIO bucket with
an enabled seven-day `input/` lifecycle. Storage upload/read/delete/signing
passed. The local MinIO image needed a root-run test container due to volume
permissions, and SSE was disabled because that image lacked KMS; these are
local QA settings, not production security acceptance.

The final Worker E2E used a loopback TLS Backend, TLS MinIO proxy, trusted
test certificate, the unchanged `WorkerAgent` and `FrozenRunner`, and the real
frozen checkpoint. User A created a Case and uploaded the synthetic DICOM;
the Agent registered, heartbeated, claimed each Job, downloaded the signed
input over TLS, inferred, and submitted Prediction and 16/32/64 px Occlusion.
Both Jobs were `COMPLETED`, both Results were `LIVE_CASE`, the frozen model SHA
matched, and all nine PNG assets were read through authorized Backend routes.
The temporary Agent work root was outside frozen research data. See
[`tls_worker_agent_e2e.json`](../../qa/evidence/p1_phase25/tls_worker_agent_e2e.json).
An earlier direct HTTP exercise also checked all three scale position pages,
asset bytes, Case DICOM, and Result metadata against PostgreSQL/MinIO; see
[`real_worker_postgres_minio.json`](../../qa/evidence/p1_phase25/real_worker_postgres_minio.json).

## Browser acceptance

Chrome displayed User A's READY Case and synthetic DICOM upload, the actual
WorkerAgent Prediction Result (2.56% positive probability and 97.44%
predicted-class confidence), the Occlusion Result and selectable 16/32/64 px
response heatmaps, and the DICOM after a fresh Case navigation. The response
image was requested through the Backend Result Asset route. With proxy token
injection removed, the Case page showed the Backend 401 state and no data.
Screenshots of the Prediction, Heatmap, refreshed DICOM, and 401 state were
captured in the QA conversation; they contain no credential. This run did not
export image files into Git.

An initial browser DICOM decode timeout came from the QA worktree's symlinked
`node_modules`: Vite refused to serve the Cornerstone Worker from another
worktree. A local `npm ci` and Vite restart resolved it. No application source
change was needed. The server-held User token is local proxy bootstrap only;
there is no production OIDC login or session flow.

## Regression

- Full Python repository suite: **119 passed, 0 skipped**. The first run had
  one environment-only failure because `pyarrow` was missing; installing it
  in the isolated QA virtual environment and rerunning cleared the failure.
- Backend v2 plus Worker suite: **37 passed, 0 skipped** with PostgreSQL/MinIO
  and frozen Worker environment configured.
- Frontend: **21 passed**, production build passed. Vite emitted existing
  Cornerstone codec externalization and large-chunk warnings.
- No core security test was skipped. FastAPI/Starlette and JSON Schema
  deprecation warnings remain. `npm ci` reported nine transitive dependency
  advisories (three moderate, six high) already documented by Frontend v1.

## Remaining limits

This proves a local synthetic, single-slice integration path. It does not
establish public HTTPS deployment, production KMS/encryption, OIDC login,
clinical validity, GPU deployment, or heatmap coordinate fusion. The local
Vite proxy represents one provisioned user and must be replaced by a proper
server-side per-user authentication boundary before production use.
