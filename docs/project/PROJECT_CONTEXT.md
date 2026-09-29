# EpiLocate Project Context

**Snapshot:** 2026-09-29 (Asia/Shanghai). This is a source-backed navigation page, not a live service monitor. Recheck Git refs, tests, and running services before making a new current-state claim. This repository is an independent sanitized Git root made from an audited internal candidate, with selected parallel documents and Landing source. Internal source SHAs below are provenance references, not ancestors of this Git root. See [Source Provenance](../handoff/SOURCE_PROVENANCE.md) and [Handoff Status](../handoff/HANDOFF_STATUS.md).

## 1. Identity and boundaries

EpiLocate combines a medical imaging research line with an engineering AI product and several distinct web applications. Its Challenge Cup / research context does not convert engineering tests into clinical evidence. Frozen model responses and Occlusion heatmaps are model behavior, not lesions, segmentation truth, or clinical localization. Keep research protocol, product code, and deployment acceptance separate.

## 2. Current milestone and evidence

The internal Phase 5 source branch is `codex/p1-phase5-dual-mode-server-demo`. Its application and deployment implementation was committed at `4d717a3753ef307ab370adeafaf5a00da4dc7af9`; GPU MVP handoff and operations evidence at `352152ce95fc26eb2dc0a4c309521d50486472ba`; and a later runtime incident report at `f80d4cf406689cd031f993090783e281db93c4ef`. That ordering is supported by the preserved internal history. This public snapshot copies audited files and selected documents; it contains none of those internal commits as Git ancestors and is not a full project history.

At the Phase 5 reported acceptance environment, a browser exercised a Vue AI Web at `/mvp/` through Session Gateway and Backend v2 to PostgreSQL/MinIO and an independent RTX 3090 CUDA Worker. Synthetic single-slice DICOM Prediction and 16/32/64 px Occlusion completed with 729/169/36 positions and nine heatmap assets. Stored rows and objects, browser result display, and refresh recovery were checked. See the in-tree [GPU MVP implementation report](../phase5/gpu_full_chain_mvp_report.md) and [final handoff](../phase5/gpu_final_handoff_report.md). These are dated deployment and test reports; they do not prove the services are running now. ECS CPU Worker was outside that MVP runtime path, while Worker source retains `CPU`, `CUDA`, and `AUTO` selection. This is a GPU-only **engineering MVP acceptance**, not a permanent GPU-only architecture or Production Ready claim.

The fixed CPU/GPU numerical consistency gate remains **FAIL / OPEN**: maximum derived deviation `0.0010498762130737305` versus frozen tolerance `0.0001`. Functional CUDA and browser E2E passes do not override it. Do not change the reference, model, or tolerance to make the gate pass.

At `f80d4cf`, a GPU JPEG Lossless DICOM failure was traced to missing decoder packages in the running Python environment. The runtime was repaired with `pylibjpeg==2.1.0` and `pylibjpeg-libjpeg==2.4.0`; subsequently created Prediction and Occlusion jobs completed. The two historical jobs remain `FAILED`. This runtime repair was an operational intervention, not a new application-code commit. The snapshot retains a case-neutral mechanism account in `docs/phase5/gpu_failed_job_incident_20260929.md`; restricted incident evidence and its Git objects are excluded from this root.

## 3. Canonical source map

The table names current source paths, not completed migrations. The full branch and target mapping is in [SOURCE_MAP.md](../consolidation/SOURCE_MAP.md).

| Boundary | Source path and provenance | Current consolidation status |
| --- | --- | --- |
| Landing | `apps/landing/`, React/Vite, imported from `flow-fluidity/` at `research/stage1-validation-backup` @ `f59738a606d15ff7062bbc64fc316ba276035ce4` | Candidate source imported and locally built; not yet deployed. |
| AI Web | `frontend/`, Vue/Vite, Phase 5 implementation @ `4d717a3753ef307ab370adeafaf5a00da4dc7af9` | Still at root; `apps/ai-web/` is a future target. |
| Backend | `backend_v2/`, Phase 5 source | Still at root; `services/backend/` is a future target. |
| Gateway | `session_gateway/`, Phase 5 source | Still at root; `services/gateway/` is a future target. |
| Worker | `worker/`, Phase 5 source | Still at root; `services/worker/` is a future target. |
| Deployment templates | `deploy/mvp/`, Phase 5 source | Still at root; recheck runtime before deployment. |
| Showcase | `aid_site/`, Phase 5 tree | Separate research display app; no app migration yet. |
| Review | `epilocate_review_server/`, Phase 5 tree | Separate historical human review service; no app migration yet. |
| Research runtime | `algorithm/`, `src/`, `scripts/`, `configs/`, `gradio_service/` and runtime dependencies | Retained at root under frozen or active dependency boundaries. |
| Project documentation | `docs/` plus selected files from independent documentation branches | Current candidate contains API, engineering history, and consolidation documents; each retains its source commit in the handoff index. |

## 4. Architecture and product separation

```text
Browser → Vue AI Web → Session Gateway → Backend v2 → PostgreSQL / MinIO
                                              ↕
                                       remote GPU Worker
                                              ↓
                                   FrozenBaseline CUDA runtime
```

The Phase 5 reported deployment used `/mvp/` for the AI Web while the older Review entry remained separate. Landing is a welcome entry; AI Web is the CT AI workspace; `aid_site` is a Showcase; Review Server is the historical human review system. Review accounts, Aid accounts, and AI System sessions must not be described as one login system. Backend handlers do not perform inference; Worker runs the frozen model and submits results.

## 5. Meaningful branches and document provenance

| Branch | Verified commit at this snapshot | Meaning and relationship |
| --- | --- | --- |
| `codex/p1-phase5-dual-mode-server-demo` | `f80d4cf406689cd031f993090783e281db93c4ef` | Phase 5 source plus later incident documents. Its implementation commit `4d717a3` is an ancestor. |
| `docs/backend-api-phase5-gpu-mvp` | `4ae2e59ae144e273441884fa676e628a1944a689` | Four Phase 5 contracts and the API integration guide were selectively imported. |
| `docs/project-history-engineering-journal` | `c312d3933f7fe83772542773ae1419a7af44d63c` | History, journal, guide, checker, and tests were selectively imported. |
| `codex/repository-consolidation-v1` | `f5438fe90dfa4895e0d49a1f688b7d2cd9df36a0` | Project context, rules, skill, source map, and plans were selectively imported; only Landing source has moved into `apps/`. |

The table above records internal source references. Those commits are not reachable from this sanitized Git root. Documentation integration does not create a new Phase 5 API capability; do not infer service deployment from document integration.

## 6. Open issues and next gates

| Item | Evidence or required check |
| --- | --- |
| CPU/GPU fixed numerical consistency | FAIL / OPEN at frozen tolerance; see [GPU MVP report](../phase5/gpu_full_chain_mvp_report.md). |
| Failed Job user experience | Phase 5 incident reports the page displayed only `Job failed.`; safe failure guidance has not been implemented there. |
| Worker observability | Incident logs lacked a useful sanitized exception type or traceback; improve without logging signed URLs or patient metadata. |
| GPU runtime reproducibility | Decoder packages existed in requirements but were missing from the runtime; verify packaging and preflight for supported Transfer Syntax values. |
| Worker lifecycle | GPU Worker was run in `tmux`; automatic restart and release persistence were not demonstrated in the cited report. |
| Storage and recovery | Independent off-host backup/restore, limited MinIO credentials, and KMS-supported at-rest encryption remained open production gates in the final handoff. |
| Production hardening | Recheck capacity, supervision, observability, secret handling, current service health, and rollback before any broader release. |

## 7. Frozen boundaries and evidence language

Do not casually edit FrozenBaseline code, checkpoint, preprocessing, mathematical definitions, Stage 1 split/protocol/hash evidence, Worker protocol, CPU reference, or numerical tolerance. A source file existing means **implemented**; a named test run means **tested**; ancestry and merge history establish **integrated**; host/runtime evidence establishes **deployed**. Each has its own branch, commit, environment, and time. Engineering validation is not clinical validation. `MOCK`, `LIVE_CASE`, and `FROZEN_VALIDATION` are distinct evidence types.

## 8. Frontend handoff

The stated frontend ownership for Chen Yibing (B) is `frontend/` and a future reviewed migration to `apps/ai-web/`. Backend, Worker, deployment, Landing, Showcase, Review, and FrozenBaseline are separate ownership boundaries. Start with the branch-qualified Frontend Integration Guide below; verify its contract against the exact source revision before UI work.

## 9. Reading and dispatch

| Need | Read next |
| --- | --- |
| Source migration and branch boundaries | [Consolidation Source Map](../consolidation/SOURCE_MAP.md), [Migration Plan](../consolidation/MIGRATION_PLAN.md) |
| Phase 5 GPU implementation and acceptance | [GPU MVP report](../phase5/gpu_full_chain_mvp_report.md), [final handoff](../phase5/gpu_final_handoff_report.md), [Worker operations](../phase5/gpu_worker_mvp_operations.md) |
| Incident and runtime decoder repair | `docs/phase5/gpu_failed_job_incident_20260929.md`, Phase 5 @ `f80d4cf406689cd031f993090783e281db93c4ef` |
| Frontend integration | `docs/backend/frontend_integration_guide_phase5.md`, Backend docs @ `4ae2e59ae144e273441884fa676e628a1944a689` |
| API, Gateway, Worker lifecycle contracts | `docs/backend/backend_api_contract_phase5.md`, `session_gateway_contract_phase5.md`, `worker_api_job_lifecycle_phase5.md`, same Backend docs commit |
| Stage history and engineering activity | `docs/project/ITERATION_HISTORY.md`, `ENGINEERING_JOURNAL.md`, `DOCUMENTATION_GUIDE.md`, Engineering docs @ `c312d3933f7fe83772542773ae1419a7af44d63c` |

For Frontend, Backend, Worker, Deployment, QA, Documentation, and Repository/Git tasks, use a suitable available agent for a bounded independent scope. These are dispatch roles, not preinstalled named agents. The main agent owns planning, conflict resolution, integration, validation, and reporting; when no suitable agent exists, it performs the work. The root [AGENTS.md](../../AGENTS.md) gives operating rules. Conversation memory is a lead; code, Git, tests, and stored reports decide factual claims.

## 10. Context gaps

The snapshot contains the case-neutral incident summary, Backend API docs, engineering history text, and documentation checker. The included historical documents point to internal commits for provenance; `git log` here starts at the sanitized root. Current ECS and GPU source commit markers are absent, `/welcome/` has not been deployed, and no clean-node GPU rebuild or new end-to-end acceptance has been completed. The numerical consistency and production recovery gates remain open.
