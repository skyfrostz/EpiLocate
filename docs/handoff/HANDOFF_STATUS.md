# EpiLocate Handoff Status

**Public branch:** `handoff/pre-b-transfer-20260929`
**Repository model:** independent sanitized Git root from an audited file tree; it does not contain the complete internal development history. See [SOURCE_PROVENANCE](SOURCE_PROVENANCE.md).
**Evidence date:** 2026-09-29. This is an Engineering MVP, **Not Production · Not Clinical**.

## Release gates

| Gate | Status | Evidence or remaining work |
| --- | --- | --- |
| Source-tree reconciliation | PASS | The original 434 candidate payload files were compared byte for byte before documented snapshot changes. Final reconciliation: 416 unchanged, 17 intentionally changed, one excluded image-object manifest, one added provenance file. |
| Word documents | PASS | All pages of three sanitized copies were visually reviewed in native Word print-quality PDFs: Handoff 8, Redesign 7, API 16. Package metadata, relationships, hidden text, media, and linkable patterns were checked. |
| Secret / PHI and DICOM | PASS for published candidate | All reachable objects through application commit `649b0c665971cfefcc67509849947b2d3f7e49c7` were scanned: one root, 529 objects, 429 unique blobs, three expanded Word files, one byte-reproduced synthetic DICOM, 55 other images, zero blocking findings. The final commit's complete pre-push scan is recorded as external release evidence. Every later commit requires another scan **before** push. |
| GitHub sanitized Handoff branch | PASS | Only `handoff/pre-b-transfer-20260929` was ordinary-pushed; no internal refs or sensitive ancestors were published through this branch. |
| Fresh GitHub clone | PASS | The application commit `649b0c6` passed Landing `npm ci`/build, Vue 36 tests/build, Backend/Gateway/Worker/docs 51 passed and 2 skipped, 148 local Markdown links, and matching `SOURCE_COMMIT`. The final published SHA requires and receives a separate clean-clone record outside this self-referential Git document. |
| ECS `/welcome/` and Git-based candidate release | PASS | ECS exported from GitHub and built Landing/Vue. `SOURCE_COMMIT` and Backend/Gateway/Sweeper process working directories matched the deployed release SHA; `/welcome/`, `/mvp/`, Review root, and health endpoint responded. Desktop and mobile browser review passed after the Welcome CSP fix. The final published SHA is checked against runtime `SOURCE_COMMIT` in external release evidence. |
| GPU AI Node | **TEMPORARILY OFFLINE / INTENTIONALLY RELEASED** | The owner released the instance on purpose. This is not a new system failure. Do not retry its old SSH endpoint. |
| GPU architecture | **PREVIOUSLY VALIDATED** | Earlier GPU-only functional E2E PASS remains historical evidence. It does not establish current availability or CPU/GPU numerical equivalence. |
| Final Git-based GPU E2E | **PENDING GPU RE-PROVISION** | Pause GPU Worker deployment, GPU `SOURCE_COMMIT` validation, synthetic GPU E2E, and CUDA runtime revalidation until the owner supplies a new SSH host and port. Rebuild from the final Handoff Git SHA and then run synthetic E2E. |
| Frontend redesign branch | LOCAL PREPARATION; REMOTE PENDING GPU | Point the local `feature/frontend-redesign-phase5` ref to the final sanitized Handoff commit. Ordinary-push only after the remaining final GPU gate passes. |

## GPU rebuild requirements retained

- RTX 3090-class CUDA node; PyTorch `2.4.0+cu121` and pinned Worker dependencies.
- `pylibjpeg==2.1.0` and `pylibjpeg-libjpeg==2.4.0`.
- Verified FrozenBaseline checkpoint SHA-256: `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`.
- Do not substitute an ECS CPU Worker for final GPU acceptance. Do not rewrite historical GPU E2E PASS, FrozenBaseline, or CPU/GPU tolerance.

## Known open issues

- CPU/GPU numerical consistency: **FAIL / OPEN**. Observed maximum derived difference `0.0010498762130737305` exceeds fixed `0.0001` tolerance.
- Frontend failed-job UX and safe Worker traceback context: **OPEN**.
- Production hardening and independent backup/restore exercise: **INCOMPLETE**.
- External Landing media usage rights and long-term availability: **OPEN**.
- Vue dependency audit reported nine advisories (three moderate, six high); triage remains **OPEN**.

## Public snapshot boundary

Restricted medical images and incident evidence, object-level image download manifests, research data, model weights, databases and object-store contents, credentials, logs, caches, virtual environments, and uncommitted research outputs are outside this repository. The complete internal Git history remains local for internal evidence. This public branch begins at a new root and must not be described as the complete development history.
