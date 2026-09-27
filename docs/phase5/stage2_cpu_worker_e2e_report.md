# EpiLocate P1 Phase 5 — Stage 2 CPU Worker and local real E2E

## Scope and Git baseline

- Development worktree: `/Users/skyfrost/Documents/Techniques/EpiLocate-p1-phase5-dual-mode-server-demo`.
- Branch: `codex/p1-phase5-dual-mode-server-demo`.
- Starting HEAD, clean before Stage 2: `639bfec38283728b54b0b6ce7961df10ea9ec535` (approved Stage 1).
- Tested implementation HEAD: `b07cfaefdeec4b382f530a8a22751b0ad8bafcfa`. This report is committed separately so it can name the tested implementation commit. Its own final commit SHA is given in the handoff.
- No other worktree, FrozenBaseline source/checkpoint, frozen Worker/API protocol, GPU device path, ECS, Nginx, or production domain was changed. The parallel `AGENTS.md`, engineering journal, and iteration history were not present in this worktree; no Documentation Codex worktree was edited.

## Changes

| Area | Files | Reason |
| --- | --- | --- |
| Worker startup | `backend_v2/workers/provision.py`, `backend_v2/tests/test_worker_v1_integration.py`, `deploy/run_server_cpu_worker.sh` | Provisioning now emits required `MODEL_HASH`; the generic launcher forces `WORKER_DEVICE=CPU` and executes the existing independent `python -m worker`. |
| Logging | `worker/__main__.py` | Suppress `httpx` INFO request logs, which otherwise can include signed MinIO query parameters. Worker device and error logs remain. |
| Browser account boundary | `frontend/src/auth/session.ts`, `frontend/src/tests/auth.spec.ts` | Clear per-Result fusion preference keys on logout, expiry, or account switch. Keep same-user refresh restoration. This removes previous-account Result IDs from shared-browser session storage. CT rendering code was not changed. |
| Local acceptance tooling | `qa/phase5_local_https.py`, `qa/phase5_verify_gateway_live.py`, `.gitignore` | Loopback-only test TLS edges for browser, Backend Worker API, and private MinIO; live two-account authorization, CSRF, cookie, expiry and revocation checks; ignore generated browser files. These are QA tools, not production reverse proxy configuration. |
| Documentation and evidence | `docs/phase5/server_cpu_worker_runbook.md`, screenshots and sanitized JSON in `docs/phase5/evidence/stage2/` | Reproducible generic startup contract, browser and machine-readable evidence. |

## Real CPU environment and input

- Host: macOS 26.5.2, Apple M5 Pro (`arm64`, 18 logical CPUs), 24 GiB RAM. This is **local CPU** evidence, not an ECS or GPU measurement.
- Worker: separate Python 3.11.15 process, `python -m worker`, PyTorch 2.14.0, explicit `WORKER_DEVICE=CPU`. `FrozenRunner` reported actual accelerator `CPU`; Register, idle/active Heartbeat, Claim, signed private DICOM download, frozen inference, and Submit were observed. Single Worker, one active task at a time. Backend and sweeper ran in separate Python 3.14 processes.
- PostgreSQL: isolated Docker `postgres:16-alpine`; MinIO: isolated Docker `minio/minio:latest` local image, private bucket, 7-day `input/` lifecycle. The local MinIO image resolved to a Bitnami-rootless build and required a test-only UID override for its fresh volume. The tag is not pinned for deployment.
- Local endpoints: browser `https://127.0.0.1:8943`; separate Worker/QA Backend HTTPS `https://127.0.0.1:8944`; signed MinIO HTTPS `https://127.0.0.1:5943`. Internal Backend, gateway, PostgreSQL, and MinIO ports bound to loopback. Local self-signed certificate; browser automation used `ignoreHTTPSErrors=true` for that certificate only. `Secure` cookie was retained. Trusted public TLS and production HTTPS routing were **not** validated.
- Input: repository synthetic single-slice CT DICOM, `docs/interfaces/fixtures/p0_synthetic_ct.dcm`, SHA-256 `8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee`. No patient DICOM was used.
- Frozen checkpoint: read-only `outputs/experiments/FORMAL-BL-R18-V1/training/best_model.pth` in the research worktree, measured SHA-256 `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`. Worker `MODEL_HASH`, Backend model version, persisted Result version and the measured file hash matched. The research worktree was only read.

## Inference and persistence results

`qa/p1_gpu_worker_stack_smoke.py --device CPU` first completed a separate real CPU Prediction and three-scale Occlusion through HTTPS Backend, PostgreSQL, MinIO and an independent Worker subprocess. It accepted both results, read both back through Backend API, verified 9 PNG assets, and counted 729/169/36 positions. Despite this legacy script name, the requested and actual device were **CPU**. The subsequent browser run used the **persistent** `python -m worker` process, not that subprocess harness.

| Browser task | Job ID | Result | Persisted evidence |
| --- | --- | --- | --- |
| Alice Prediction | `job_a8a1679bbc0245b735fe4d7ac0d6a2f4` | COMPLETED, `LIVE_CASE`, negative, positive probability 2.56% | PostgreSQL Result and Backend API reread; 0 heatmap assets as expected for Prediction. |
| Alice Occlusion | `job_161f6ab93e2ff06b724fa3a1539e036b` | COMPLETED, `LIVE_CASE`; 16/32/64 px = 729/169/36 positions | 9 Asset rows and 9 MinIO PNG bytes independently matched stored size and SHA-256; all 9 available through authorized Backend asset routes. |
| Bob Prediction | `job_28a92c2e360aeb65c3271c05e812bbf3` | QUEUED while Worker stopped, then COMPLETED after restart | PostgreSQL/Backend result persisted; source `LIVE_CASE`. |
| Bob Occlusion | `job_6d4a87b99db0c4dda6c3c90a62a885d6` | COMPLETED, `LIVE_CASE`; 729/169/36 | 9 PostgreSQL Asset rows and 9 MinIO PNG objects hash-verified. |

Both users' staged synthetic DICOM bytes were reread directly from MinIO and matched their stored input SHA-256. An unsigned anonymous MinIO asset GET returned 403. The user-facing API returned assets only after Result ownership checks. Alice/Bob three-scale Occlusion task times from first claim to finish were 9.68 s and 9.43 s; these include local process transfer/submission overhead and are **not** ECS capacity estimates. A sampled Worker RSS was about 1,380,352 KiB during the local run; this is not a peak-memory measurement. No CPU concurrency above one Worker/one attempt was tested.

## HTTPS browser and authorization

- Browser: Playwright Chromium headless, Chrome for Testing 154.0.8037.0, on the same macOS host at `https://127.0.0.1:8943`. The local TLS certificate was self-signed; see TLS limitation above.
- Alice and Bob each logged in via the Stage 1 gateway, reached Dashboard, created separate Cases, uploaded the synthetic DICOM and ran real Prediction/Occlusion. Alice opened Prediction and Occlusion results; Bob opened his own Occlusion result. CT DICOM loaded through the authorized API and Cornerstone; Occlusion showed `PIXEL CONTRACT MATCHED`. Alice switched 16→32→64 px and response/candidate/comparison layers, enabled Overlay, set opacity to 70%, and refreshed the Result URL successfully. Bob's Case list showed no Alice Case.
- Live gateway checks: Alice's own Case/Result/Asset 200; Bob's own Case 200; Alice→Bob Case/DICOM/Result 404; Bob→Alice Case/DICOM/Result/Asset/positions 404, including a browser-supplied Alice Bearer header that the gateway ignored. Anonymous session/Case/Result 401; browser Worker route 404; missing CSRF on a write 403. Login Set-Cookie had `HttpOnly; Secure; SameSite=Strict`; the browser's `document.cookie` was empty, and browser LocalStorage contained no Backend token. Logout returned 204 followed by session 401; forced expiry and administrative revocation each returned 401. Browser reload after revocation returned to login.
- The original browser run exposed per-Result preference keys from Alice after Bob logged in; no result data or Bearer token was stored there, and Backend access remained 404. Stage 2 cleared those keys on logout/account switch. A rebuilt-browser check showed only Bob's current preference key after refresh and no fusion keys/account marker after logout. The same-user refresh preservation and account-switch cleanup also have a Frontend test.

Screenshots (synthetic input only): [Alice Dashboard](evidence/stage2/alice-dashboard.png), [Alice Case/CT](evidence/stage2/alice-case-ct.png), [Alice Prediction](evidence/stage2/alice-prediction.png), [Alice Occlusion with Overlay at 70%](evidence/stage2/alice-occlusion-overlay.png), [Bob Occlusion](evidence/stage2/bob-occlusion.png). The raw Playwright captures were made under ignored `output/playwright/phase5-stage2/`; the copies linked here are committed. Screenshots precede the preference-key cleanup, which was separately verified in the rebuilt browser.

Sanitized machine-readable evidence: [CPU smoke](evidence/stage2/cpu-smoke.json), [PostgreSQL/MinIO audit](evidence/stage2/db-object-evidence.json), [Backend API reread](evidence/stage2/api-reread.json), [two-user gateway checks](evidence/stage2/auth-e2e.json), [lease recovery](evidence/stage2/crash-recovery.json), [two-user queue](evidence/stage2/multi-user-queue.json), and [failure state](evidence/stage2/failed-job.json). No credential or signed URL is in these files.

## Worker interruption, timeouts, failure and queue

- Graceful stop: Bob's Prediction stayed QUEUED with no Worker, then completed after restarting the independent Worker. The browser showed the queue and terminal result.
- Abrupt stop: a real Bob Occlusion was killed while RUNNING on attempt 1. Its active heartbeat and 90-second lease were present. After expiry, the unchanged sweeper marked attempt 1 `EXPIRED / LEASE_EXPIRED`, applied the frozen 30-second first retry delay, and requeued the Job. Restarted Worker took attempt 2; it `SUCCEEDED`, leaving one durable `LIVE_CASE` Result with 9 verified assets and 729/169/36 positions. Total first-start-to-finish was 156.25 s, dominated by the fixed lease/retry wait. No protocol timeout was shortened.
- Failure path: a separate local QA Case's staged synthetic object was deliberately corrupted **after** accepted upload. Worker verified the downloaded SHA-256 and submitted `INPUT_HASH_MISMATCH`; Backend Job became `FAILED` on attempt 1, with no false success Result. This intentionally corrupted object is isolated to the local disposable stack.
- Two-user queue: with Worker stopped, Alice and Bob Prediction jobs were simultaneously QUEUED. After starting the CPU launcher, both COMPLETED; PostgreSQL attempt intervals did not overlap (Alice finished at 19:50:05.435 UTC, Bob leased at 19:50:10.463 UTC). This confirms single-task serial behavior in this local configuration, not multi-Worker fairness or ECS throughput.

## Executed checks and boundaries

| Check / command | Outcome | Evidence type |
| --- | --- | --- |
| `PYTHONPATH="$PWD" EPILOCATE_WORKER_ROOT="$PWD" EPILOCATE_WORKER_PYTHON=<frozen-python> EPILOCATE_FROZEN_ROOT=<read-only-root> .venv/bin/pytest -q session_gateway/tests backend_v2/tests` with local production-like DB/S3 env | **21 passed, 0 skipped, 1 Starlette/httpx deprecation warning**. The previously skipped real Worker integration and PostgreSQL/MinIO production-like tests both ran. | Unit/integration; some tests use Mock/SQLite, Worker integration invokes real CPU FrozenBaseline; production-like test uses PostgreSQL/MinIO. |
| `PYTHONPATH="$PWD" <frozen-python> -m pytest -q tests/test_worker` | **29 passed** | Worker regression; no GPU hardware. |
| `cd frontend && npm test -- --run` | **36 passed**; jsdom `scrollTo` notice | Frontend component/unit tests, not real browser inference. |
| `cd frontend && npm run build` | **passed**; existing codec externalization and large chunk warnings | Production Frontend build. |
| `PYTHONPATH="$PWD" .venv/bin/python qa/p1_gpu_worker_stack_smoke.py --device CPU ...` | **passed**; actual CPU, Prediction/Occlusion COMPLETED, 9 PNG, 729/169/36 | Real CPU HTTPS/PostgreSQL/MinIO stack, separate Worker subprocess. |
| Persistent `deploy/run_server_cpu_worker.sh ...` plus Chromium browser workflow | **passed**; real CPU and `LIVE_CASE` as detailed above | Local HTTPS browser E2E, not Mock. |
| `PYTHONPATH="$PWD" .venv/bin/python qa/phase5_verify_gateway_live.py ...` | **passed**; 200/401/403/404 cases above | Live two-user gateway/Backend/asset authorization. |
| Direct SQLAlchemy PostgreSQL rows and boto3 MinIO object bytes/hash audit; unsigned MinIO GET | **passed**; 9/9 assets per Occlusion, private bucket 403 | Direct persistence audit, distinct from API reread. |
| Graceful stop, SIGKILL mid-Job, lease expiry/retry, corrupt input, two-user queue | **passed** | Real Worker process/Backend state transitions. |
| `git diff --check`, Python `py_compile`, `sh -n` | **passed** | Whitespace and syntax. |

No tests failed in the final regression. The initial local test setup encountered a MinIO volume permission error from the available rootless image and was corrected with a local-only UID override. An early direct-Bearer smoke request to the browser gateway correctly returned 401; the smoke was rerun through the separate Worker/Backend HTTPS edge. These setup attempts are not counted as passing tests. No CUDA/GPU machine was used. Browser HTTPS used a self-signed local certificate and disabled browser certificate verification; it does not prove production TLS configuration. ECS CPU/RAM/disk, backup, Nginx/TLS, old Review Server coexistence, and rollback remain **unassessed** until separately authorized read-only ECS audit. No Stage 3, ECS access, merge, push, or domain switch was performed.

After evidence capture, the task-scoped Playwright session and all local test processes/containers were closed. The disposable synthetic PostgreSQL/MinIO volumes, generated test credentials, gateway sessions, TLS private key, and Worker scratch were removed. The committed sanitized JSON and screenshots remain as the acceptance record; rerunning requires new local credentials and test volumes.

Remaining deployment gates: confirm target ECS architecture and measured CPU/RAM headroom for the model, pin container images and dependencies, provide a trusted TLS and private MinIO route, arrange service supervision/secret storage/backups, and audit the existing Review Server before designing cutover and rollback. The local M5 Pro timing and sampled RSS are not evidence that the unknown ECS can host CPU Occlusion.
