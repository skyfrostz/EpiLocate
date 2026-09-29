# EpiLocate Phase 5 — remote GPU full-chain MVP acceptance

**Execution date:** 2026-09-28 (Asia/Shanghai). **Development worktree:** `LOCAL_WORKTREE/EpiLocate-p1-phase5-dual-mode-server-demo`, branch `codex/p1-phase5-dual-mode-server-demo`. Starting HEAD was `15d7b67b019df0dbf16afa93e447bde7b6d58b29`. This report and the implementation are submitted together; the final commit SHA is in the handoff. No merge or push was performed.

## Acceptance decision

| Gate | Result | Evidence and limit |
| --- | --- | --- |
| P0: FrozenBaseline CUDA Prediction and three-scale Occlusion on the GPU node | **PASS for functional CUDA execution** | RTX 3090, actual device `CUDA`, frozen model hash matched; negative Prediction, 729/169/36 positions and nine PNG assets. The separate fixed CPU/GPU numerical comparison **FAILED** as recorded below. |
| P1: remote GPU Worker through ECS protocol with durable results | **PASS** | The specified Worker completed two `LIVE_CASE` Jobs on attempt 1. PostgreSQL Result/Asset rows and MinIO DICOM plus 9/9 PNG objects were reread and SHA-256 checked. Worker log proves CUDA; database alone does not store `hardware.accelerator`. |
| P2: Vue browser upload, inference, result display and refresh | **PASS** | Playwright Chromium on macOS drove the public TLS origin under `/mvp/`, including login, synthetic DICOM upload, Prediction, Occlusion, three scales, three layers, CT Overlay, 70% opacity, refresh recovery and logout. Screenshots are linked below. |

These are engineering MVP results with a synthetic single-slice DICOM. They do not establish clinical validity, GPU numerical equivalence, multi-user throughput, or production recovery readiness.

## Architecture actually running

```text
https://project.xbstu.com/mvp/  → Nginx → Vue static build
/auth/ and browser /api/v2/     → Session Gateway (127.0.0.1:8891)
/api/v2/workers/                → Backend v2 (127.0.0.1:8890)
Backend                         → PostgreSQL (127.0.0.1:5432)
Backend and signed object GET   → private MinIO (127.0.0.1:59000)
Matrixcloud RTX 3090 Worker    → public HTTPS Worker API, signed HTTPS DICOM GET
Worker                          → FrozenBaseline CUDA → Backend Submit → PostgreSQL/MinIO
```

The old Review Server remains the site's root entry and `/healthz`; Gradio and Aid remain active. PostgreSQL, MinIO, Backend, Gateway and Sweeper run as systemd services using loopback listeners. The new UI uses the isolated `/mvp/` path. ECS has no CPU Worker unit or process. Source code retains the `CPU`, `CUDA` and `AUTO` device choices and the frozen Register, Heartbeat, Claim and Submit protocol. The MVP claim window had only the specified GPU Worker. Backend request handlers did not run model inference.

The MinIO signed URL used the public HTTPS origin and path-style bucket. A GPU-side SigV4 object GET returned HTTP 200, downloaded 4096 bytes, and matched the expected SHA-256. The object proxy now disables access logging so the `X-Amz-*` query is not written to a standard request log. No private PostgreSQL or raw MinIO listener was exposed publicly.

## Frozen GPU environment and local PoC

- GPU: NVIDIA GeForce RTX 3090, 24 GiB; driver `535.216.01`; driver CUDA support `12.2`.
- Python: `/root/miniconda3/envs/myconda/bin/python3.12`; PyTorch `2.4.0+cu121`, CUDA runtime `12.1`; actual inference device `CUDA`.
- Frozen checkpoint and `MODEL_HASH` SHA-256: `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`.
- Input: repository synthetic CT DICOM, SHA-256 `8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee`. No patient imaging was used.
- Prediction: class 0 / `negative`, positive probability `0.025690102949738503`.
- Occlusion: 16 px `729`, 32 px `169`, 64 px `36`; nine assets across candidate, comparison and response layers.
- Measured local GPU PoC timing: model initialization 1562.003 ms; cold/warm Prediction 539.116/256.614 ms; cold/warm Occlusion 22492.836/682.239 ms. Peak PyTorch allocated CUDA memory was 278,073,344 bytes. These figures are from this GPU node and synthetic input, not an ECS capacity estimate.

The [sanitized benchmark summary](evidence/gpu_mvp/gpu-benchmark-summary.json) records the exact metrics without task credentials or object URLs. Full raw benchmark evidence remains in the private local `/tmp/epilocate-gpu-evidence/` directory and is not committed.

### Fixed CPU/GPU numerical comparison

`comparison.passed=false` is preserved. Base probability maximum absolute delta was `0.00007169507443904877` against tolerance `0.0001`; decoded PNG pixel maximum delta was `1` against tolerance `2`. Derived numeric maximum delta was `0.0010498762130737305` against tolerance `0.0001`, with 502 failed derived paths across 224 positions. The maximum was `positions[691].masked_positive_probability`. Class, prediction flip, candidate-mask pixels, geometry, position counts and nine asset names matched. All nine PNG byte hashes differed, so only the decoded pixel contract passed. The frozen model, checkpoint, CPU reference, algorithm and tolerances were not changed. This numerical gate remains **FAILED** for any future CPU/GPU interchangeability claim; the owner directed this GPU-only engineering MVP to proceed and retain the evidence.

## Remote Worker and persistence proof

Worker ID: `node_1db0cbcf325be5669472ebde94cb20a3`. The GPU node runs the Worker as a separate `python -m worker` process in a `tmux` session. Its log recorded `Worker execution device: CUDA`. The Worker used HTTPS with certificate verification and a server-held Worker Bearer credential. No Worker token or signed URL is in this report. The GPU-side persistent root is `/mnt/epilocate-mvp`.

| Item | Identifier | Verified outcome |
| --- | --- | --- |
| Case | `case_a6f2c293244b16a2c678a21f9d86806d` | Synthetic DICOM uploaded; Slice `slice_e57d1c52c31d86a8ecd7a2485aac1368`. |
| Prediction | Job `job_e27a29fde87b7e51407c41ea1eb7f75f`; Result `result_daaf01c961544e35a8cfd6dee8f73d6d` | `COMPLETED`, attempt 1 `SUCCEEDED`, `LIVE_CASE`, specified GPU Worker. |
| Occlusion | Job `job_4467674e5311865f5921c04336e3655f`; Result `result_e991ac1b18494e33a3f7259a718f2012` | `COMPLETED`, attempt 1 `SUCCEEDED`, `LIVE_CASE`, specified GPU Worker; 729/169/36 positions and nine assets. |

A post-service-account-migration read-only check found both Jobs and Results persisted in PostgreSQL, with the same model hash and Worker assignment. MinIO contained one synthetic DICOM and nine heatmaps. A separate read of every object recomputed bytes and SHA-256: DICOM matched its Slice source hash and all 9/9 heatmaps matched their PostgreSQL Asset records. The public anonymous Case, Result and Heatmap routes returned 401. The browser account and asset ownership checks from Stage 2 remain in application code; this round did not repeat a new two-account authorization matrix on ECS.

A subsequent GPU-node check found the Worker still running. It observed a short Worker API/heartbeat error window at 21:24:39–21:24:42 CST, followed by a successful empty claim cycle and no further warnings through 21:32:52. The completed P1 Jobs are the positive Submit evidence; the later empty claim is only a liveness check.

## Browser evidence

Browser: Playwright Chromium headless on the operator's macOS host. Address: `https://project.xbstu.com/mvp/`, using the existing trusted public TLS origin. Screenshots contain only the synthetic checkerboard DICOM:

- [Case and CT ready](evidence/gpu_mvp/case-ct-ready.png)
- [Prediction completed](evidence/gpu_mvp/prediction-completed.png) and [Prediction result](evidence/gpu_mvp/prediction-result.png)
- [Occlusion completed](evidence/gpu_mvp/occlusion-completed.png)
- [16 px Overlay](evidence/gpu_mvp/occlusion-overlay-16.png)
- [64 px comparison layer and 70% Overlay](evidence/gpu_mvp/occlusion-overlay-64-comparison-70.png)
- [The same view after refresh](evidence/gpu_mvp/refresh-recovered-overlay-64.png)

The final two screenshots have identical file SHA-256 (`36264024...03c6aef8`), supporting restoration of the selected 64 px comparison layer, enabled Overlay and 70% opacity. The browser session was closed after capture. This is a real browser flow, distinct from API and unit tests.

## Resource and deployment observations

- ECS at the last check: 2 vCPU; 3627 MiB RAM total, 2263 MiB available; 4 GiB swap unused; root disk 49 GiB, 38 GiB available. Sampled systemd `MemoryCurrent`: MinIO 234,704,896 B, Backend 96,706,560 B, Gateway 34,844,672 B, Sweeper 76,177,408 B. These are point samples, not peaks.
- GPU Worker idle sample: RSS 1,737,024 KiB (about 1.66 GiB), process GPU memory 374 MiB (device total used 380 MiB); GPU utilization 0% while idle. GPU `/mnt` filesystem: 5.0 GiB total, 3.8 GiB free at the sample. The provider's instance-release persistence and automatic restart behavior remain unverified.
- ECS service-account migration completed: MinIO=`epilocate-minio`, Backend/Sweeper=`epilocate-backend`, Gateway=`epilocate-gateway`; all four services active. Nginx `nginx -t` passed before reload. Old Review, Gradio, Aid and Nginx stayed active; old Review login and `/healthz` returned 200. `/mvp/` returned 200, and deployed `index.html` matched the local `/mvp/` build SHA-256 `aa579e153e31972b99980b69ba37f08a4a1c98618f1582919d847fe2d64fc539`.
- The GPU Worker launcher was updated on disk after a private backup; the running Worker was intentionally not restarted. Its next launch requires a current-owner regular credential file with mode 0600 and forces `WORKER_DEVICE=CUDA` after loading it.

## Changes and checks

Changed files in this submission: `frontend/src/App.vue`, `frontend/src/layout/AppShell.vue`, `frontend/src/router/index.ts`, `frontend/src/views/LoginView.vue`, `frontend/vite.config.ts`; `deploy/mvp/bootstrap_control_plane.sh`, `deploy/mvp/run_gpu_worker.sh`, `deploy/mvp/nginx-locations.conf`, and four MVP systemd units; this report and `docs/phase5/evidence/gpu_mvp/`.

The Vue changes make navigation respect the Vite base path and make `VITE_PUBLIC_BASE=/mvp/ npm run build` reproducible. The deployment files describe the actual loopback ports, distinct service users, Gateway startup, private MinIO, Worker CUDA launch and Nginx route. The standalone Worker, FrozenBaseline, checkpoint, training code, Stage 1, Backend protocol and CPU/CUDA/AUTO selection code were not modified.

| Executed check | Result |
| --- | --- |
| `cd frontend && npm test -- --run` | 36 passed; jsdom `scrollTo` notice. |
| `cd frontend && VITE_PUBLIC_BASE=/mvp/ npm run build` | Passed; existing codec externalization and large-chunk warnings. |
| `PYTHONPATH="$PWD" .venv/bin/python -m pytest -q session_gateway/tests backend_v2/tests` | 19 passed, 2 skipped, one Starlette/httpx deprecation warning. The skipped production-like storage and local Worker integration cases are not counted as passed here; actual ECS storage and remote GPU E2E were separately verified. |
| `PYTHONPATH="$PWD" <frozen Python 3.11> -m pytest -q tests/test_worker` | 29 passed. This is protocol/device regression, not another real GPU inference. |
| `PYTHONPATH="$PWD" .venv/bin/python -m pytest -q qa/tests/test_remote_gpu_preflight.py` | 4 passed. |
| `bash -n deploy/mvp/*.sh`, `shellcheck deploy/mvp/*.sh`, `git diff --check` | Passed. |
| ECS `bootstrap_control_plane.sh` rerun, `nginx -t`, service and HTTPS checks | Passed; four new services active, old services active, `/healthz` 200, `/mvp/` 200, anonymous Case 401. |
| GPU local PoC, live GPU Worker protocol, PostgreSQL/MinIO reread, Playwright Chromium | P0/P1/P2 functional gates passed as detailed above; numerical comparison failed. |

Two earlier local test attempts under the lightweight Python 3.14 environment and a stale Python path failed for missing model dependencies/path; the Worker tests passed under the frozen Python 3.11 environment. One ad hoc read-only SQL query in the final verification used an incorrect plural table name (`jobs`) and failed with `relation does not exist`; the separate correct-schema PostgreSQL/MinIO audit succeeded. These attempts are not counted as passing tests.

## Remaining risks and follow-up

1. **CPU/GPU consistency:** derived values exceed the frozen `1e-4` tolerance. Resolve through a separately reviewed analysis; do not adjust model, reference or tolerance to hide the discrepancy.
2. **MinIO at-rest encryption:** this installed MinIO build rejected SSE-S3 without an external KMS. The private bucket and TLS route are active, but `EPILOCATE_V2_S3_SERVER_SIDE_ENCRYPTION=false`; KMS or equivalent storage encryption remains a production gate.
3. **Privilege and recovery:** Backend still uses a MinIO root credential. Replace it with a bucket-scoped credential before broader use. The GPU `tmux` Worker has no automatic crash restart. There is no demonstrated independent off-host backup or isolated restore. The ECS copies under `/var/backups/epilocate-mvp/` are same-disk rollback aids only.
4. **Capacity:** one synthetic Case and one active Worker do not establish multi-user queue throughput, GPU instance release persistence, peak ECS resource use or long-term disk growth.
5. **Access:** `/mvp/` is a test entry under the existing domain; the old Review root entry was not replaced. Test accounts and the private Worker credential must be managed and revoked by the owner after the demonstration window.

## Stop and rollback

For a controlled stop, first record any active lease, then stop the GPU Worker process and confirm it is no longer claiming Jobs. Detaching the tmux session does not stop the Worker. On ECS, stop new MVP requests, then `epilocate-gateway`, `epilocate-sweeper`, `epilocate-backend` and `epilocate-minio` in dependency order. Do not delete PostgreSQL, MinIO or Gateway state.

The old Nginx site backup and SQLite online backup are under `/var/backups/epilocate-mvp/pre-mvp-20260928/`; their recorded SHA-256 values are `63d13098b1ce8e78ce139ef2cb5ed2d52f9087747c46c7787be7032f858fbe7a` (site config) and `2d15437ce660cf82d4955958bb2cffcf1516b4fce8c8da9b1eea888457c4e13d` (SQLite backup). The subsequent MVP configuration and previous web build are preserved under `/var/backups/epilocate-mvp/pre-final-20260928T2130/`. To remove only the MVP route, restore the saved old site configuration, run `nginx -t`, reload Nginx, and verify the old `/healthz` and login. Preserve all new data for diagnosis. A full disaster recovery claim requires an independent backup and restore rehearsal, which has not been completed.

## Engineering log for later documentation integration

On 2026-09-28 the isolated Phase 5 branch deployed a GPU-only test stack while retaining the Review Server, completed FrozenBaseline CUDA inference, remote Worker P1 persistence, and a Vue browser P2 flow. A security review led to signed-object access-log suppression, distinct service accounts, atomic env writes, a repeatable database role password update, Gateway startup, and stricter GPU credential checks. The final local and remote rechecks above were completed after those changes. The parallel Documentation Codex `AGENTS.md` and project journal files were not present in this development baseline, so this record is supplied here for later integration; no other Worktree was modified.
