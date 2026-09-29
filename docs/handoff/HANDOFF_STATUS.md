# EpiLocate Handoff Status

**Public branch:** `handoff/pre-b-transfer-20260929`

**Repository model:** independent sanitized Git root from an audited file tree; not the full internal project history. See [SOURCE_PROVENANCE](SOURCE_PROVENANCE.md).
**Current stage:** local snapshot candidate; GitHub clone and deployment acceptance are recorded only after they actually pass.

## Release gates

| Gate | Status | Evidence or remaining work |
| --- | --- | --- |
| Source-tree reconciliation | PASS local | The new root's initial 434 payload files matched the audited internal candidate byte for byte before documented snapshot-only changes. |
| Landing | PASS local | `npm ci` and `npm run build` passed. External media availability was checked; usage rights remain OPEN for online deployment. |
| AI Web / Backend / Gateway / Worker | PASS local | Vue: 36 tests and build. Python Backend/Gateway/Worker/docs: 51 passed, 2 skipped. Clean GitHub clone verification remains pending. |
| Word documents | PASS local | Three sanitized copies passed native Word print-quality PDF full-page review: Handoff 8 pages, Redesign 7, API 16. Metadata, embedded media, relationships, hidden text, and linkable-pattern checks passed. |
| Secret / PHI | PENDING root objects | Audited candidate-tip scan passed. A new scan of every Git object reachable from the sanitized root commit is required before push. |
| DICOM | PASS candidate | The only tracked DICOM is byte-reproduced from the synthetic fixture generator and structurally checked; no source-uncertain image is included. |
| GPU reproducibility | PARTIAL | Direct runtime dependencies are pinned; a fresh GPU environment install and approved synthetic JPEG Lossless fixture test remain open. |
| GitHub Handoff branch | PENDING | Push only this sanitized branch after all pre-push gates pass. Do not push internal refs. |
| GitHub clone validation | PENDING | Fresh clone must pass Landing, Vue, Backend/Gateway/Worker, docs links, and `SOURCE_COMMIT` generation. |
| ECS `/welcome/` and candidate release | PENDING | Current `/welcome/` was 404 before deployment. Release must derive from the fixed GitHub commit and preserve `/mvp/` and legacy routes. |
| Frontend redesign branch | PENDING | Create and ordinary-push `feature/frontend-redesign-phase5` only from the final sanitized handoff commit after acceptance. |

## Known open issues

- CPU/GPU numerical consistency: **FAIL / OPEN**. The observed maximum derived difference was `0.0010498762130737305`, above the fixed `0.0001` tolerance. No model, reference, or tolerance change is included.
- Frontend failed-job UX and safe Worker traceback context: **OPEN**.
- Production hardening and independent backup/restore exercise: **INCOMPLETE**.
- External Landing media usage rights and long-term availability: **OPEN**.

## Assets excluded from the public snapshot

Restricted medical-image and incident evidence, object-level image download manifests, research data, model weights, databases and object-store contents, credentials, logs, caches, virtual environments, and uncommitted research worktree outputs remain outside this repository. The complete internal Git history is preserved locally for internal evidence. This branch contains a new root commit and must not be described as the complete development history.
