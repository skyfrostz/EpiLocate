# P1 Phase 3 — GPU Worker Deployment & Inference Consistency

Date: 2026-09-27. Development branch: `feature/p1-gpu-worker`, created from `p0/integration` at `c9a5cc6373ffc889725971e3cae5bc09252790bd` in an independent worktree. The integration branch, frozen algorithm, checkpoint, training code, Stage 1 artifacts, and API contract were not changed.

## Status

| Status | Result |
| --- | --- |
| Implemented | Worker CPU/CUDA/AUTO selection, actual-device registration, explicit CUDA failure, CUDA OOM failure reporting, CUDA cache release, benchmark and comparison tools |
| CPU validated | Frozen synthetic reference, 29 Worker tests, Backend/Frontend regression, PostgreSQL/MinIO checks, and a real CPU Worker HTTPS stack smoke test |
| GPU validated | **No** — this Apple Silicon host has no NVIDIA GPU and its PyTorch build has no CUDA runtime |
| Production deployment validated | **No** — the stack smoke test used isolated local containers and a temporary self-signed TLS setup |

The detailed pre-change audit is [p1_gpu_capability_compatibility_report.md](p1_gpu_capability_compatibility_report.md).

## CPU reference and numerical gate

The machine-readable [CPU reference](p1_cpu_reference.json) contains the full 934-position numeric response and nine synthetic PNG assets. The [benchmark data](p1_cpu_benchmark.json) records the environment and timings.

| Field | CPU result |
| --- | --- |
| Checkpoint SHA-256 | `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734` |
| Synthetic input SHA-256 | `8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee` |
| Preprocessing version | `formal-resnet18-baseline-rule-b-v1` |
| Class | negative (`0`) |
| Positive probability | `0.025618407875299454` |
| Predicted-class confidence | `0.9743815921247005` |
| Occlusion positions | 16 px: 729; 32 px: 169; 64 px: 36 |
| Heatmap metadata | Nine PNG assets; `ALGORITHM_224` and `COMPARISON_14` coordinate spaces, pixel-edge origin and per-layer value ranges retained |

The tolerance was defined before any GPU execution: absolute probability and derived-value difference `<= 1e-4`, decoded response/comparison PNG difference `<= 2` gray levels, exact candidate masks, model/input hashes, result schema, scale and position indexing, and heatmap geometry. PNG file hashes may differ, but each bundle's own byte hash and geometry must verify. The comparison command exits nonzero on failure. Self-comparison of the CPU bundle passed with zero differences. **There is no GPU candidate bundle or CPU–GPU comparison result.**

Rationale: the frozen path uses float32 ResNet18 inference with no mixed precision; logits move back to CPU before softmax. Small forward-pass differences can propagate through the continuous probability and response values, so the numeric bound is absolute `1e-4`. An 8-bit normalized heatmap can add quantization differences, hence the two-level decoded-pixel bound. Class, top-candidate mask, geometry, and indexing are discrete decisions and must match exactly. These bounds are fixed for the future GPU run, even if that run fails.

## Performance benchmark

One synthetic local run on Apple M5 Pro CPU, PyTorch `2.14.0`; milliseconds. Model initialization measures verified checkpoint loading and model setup after Python import. CUDA timing code synchronizes the device before and after each operation and records peak allocated bytes, but was not executed on CUDA here.

| Operation | CPU ms | GPU ms |
| --- | ---: | --- |
| Model initialization | 171.001 | Not measured |
| Prediction, first call | 22.350 | Not measured |
| Prediction, warm call | 7.027 | Not measured |
| 16/32/64 occlusion, first call | 9055.194 | Not measured |
| 16/32/64 occlusion, warm call | 8795.295 | Not measured |
| Peak GPU allocation | Not applicable | Not measured |

These are single-run local observations, not a speedup claim. Reproduce with the commands in [worker/README.md](../../worker/README.md).

## Runtime and integration regression

- Worker tests: **29 passed, 0 skipped**. They cover device choice, unavailable CUDA, simulated capability reporting and CUDA OOM during model load and inference with failure manifest and cleanup, long-running inference with background lease heartbeat, reconnect/re-register, retries, failure reporting, and result upload. The simulated hardware test and accelerated heartbeat unit test are structural evidence only; they are not CUDA execution tests.
- Backend v2 tests: **16 passed, 0 skipped**, including auth security and frozen Worker integration. This suite used the actual frozen CPU model for its Worker integration test; its TestClient storage is in-memory.
- Frontend tests: **21 passed, 0 skipped**. Production build passed with existing Cornerstone codec externalization and large-chunk warnings. A browser Result view was not rerun in this phase.
- Isolated PostgreSQL 16 migration validation: Alembic head reached; all 14 required tables present among 16 actual tables.
- Isolated private MinIO: create bucket, upload/read/SHA-256 check, signed URL generation, and delete passed. Local test server-side encryption was disabled because this temporary MinIO instance had no KMS.
- [CPU stack E2E record](p1_cpu_stack_e2e.json): HTTPS Backend, PostgreSQL, MinIO, an actual WorkerAgent and FrozenBaseline completed authenticated Case creation, synthetic DICOM upload, Prediction Job and 16/32/64 Occlusion Job. Both results were `LIVE_CASE`, all nine assets were readable through Backend routes, and position pages held 729/169/36 entries. The local test used a temporary self-signed TLS certificate and scoped services that were stopped after verification. This is **CPU regression**, not GPU E2E.

## Remaining work for GPU acceptance

1. Run on an NVIDIA host with a CUDA-enabled PyTorch build and compatible driver. Record hardware, driver, CUDA runtime, GPU memory, and actual Worker registration.
2. Generate a CUDA bundle from the same synthetic input and frozen checkpoint. Run the committed comparison gate without changing its tolerance. Report every mismatch, including class, probabilities, position indexing, decoded heatmaps, and schema.
3. Exercise a sustained CUDA occlusion attempt with real 15-second heartbeats, lease renewal, GPU memory monitoring, actual OOM failure recovery, Backend reconnect and Worker re-register.
4. Complete authenticated GPU Worker E2E through PostgreSQL/MinIO and a Frontend Result view. Only then consider GPU validated. Public production deployment remains a separate acceptance stage.
