# EpiLocate AI Worker v1

The Worker polls Backend API v2 over HTTPS. It runs one frozen Baseline task at a time, sends a heartbeat every 15 seconds, and uploads a result only while its Attempt lease is valid. It does not serve user requests or write to frozen validation outputs.

## Configuration

Set these variables in the Worker process environment:

| Variable | Meaning |
| --- | --- |
| `WORKER_ID` | Pre-provisioned anonymous `node_...` identifier |
| `BACKEND_URL` | HTTPS origin for Backend API v2, without `/api/v2` |
| `TOKEN` | Pre-provisioned Worker Bearer token; never use a user token |
| `MODEL_HASH` | Full SHA-256 of the frozen Baseline checkpoint (`548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`) |
| `MODEL_VERSION` | Set to the same SHA-256 as `MODEL_HASH`; Worker Protocol v1 freezes `model_version` to the checkpoint hash |
| `EPILOCATE_FROZEN_ROOT` | Read-only experiment root containing the checkpoint and frozen protocol/configuration |
| `WORKER_DATA_ROOT` | Private writable directory outside the frozen root, unique to this Worker |
| `WORKER_CA_CERT` | Optional local CA certificate for a self-signed HTTPS integration runtime; omit in production to use normal certificate validation |
| `WORKER_POLL_SECONDS` | Optional polling interval, default 5 seconds |
| `WORKER_DEVICE` | `CPU` (default), `CUDA`, or `AUTO`; `CUDA` fails startup if NVIDIA CUDA is unavailable, while `AUTO` selects CUDA when usable and CPU otherwise |

On a GPU node, mount the frozen experiment root read-only and provision a private Worker data directory on a separate volume. Build a Python 3.12 environment from `deploy/gpu/requirements-gpu-worker.txt`, verify CUDA and JPEG Lossless decoding as described in `docs/phase5/gpu_worker_mvp_operations.md`, and use a source tree carrying the approved full SHA in `SOURCE_COMMIT`. The root and Gradio requirements are not a GPU Worker environment manifest. Load the Backend-provisioned secret environment file outside Git, then run from the prepared release directory:

```sh
set -a
. /private/path/worker.env
set +a
export MODEL_HASH=548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734
export MODEL_VERSION="$MODEL_HASH"
PYTHONPATH=. python -m worker
```

The Worker sets the existing `FrozenBaseline.device` hook before its first checkpoint load. The checkpoint is still verified and loaded on CPU before the frozen model is moved to the selected device. Preprocessing remains on CPU, and the frozen prediction and occlusion math is unchanged. The Worker registers the actual accelerator. An explicit `WORKER_DEVICE=CUDA` never falls back to CPU. `AUTO` selects CUDA if PyTorch reports a usable NVIDIA device, otherwise CPU; it does not select MPS. A missing or mismatched checkpoint prevents startup; it never falls back to Mock.

On a GPU host, install a CUDA-enabled PyTorch build compatible with that host's NVIDIA driver. Before setting `WORKER_DEVICE=CUDA`, verify `nvidia-smi` and that Python reports a non-null `torch.version.cuda` and `torch.cuda.is_available() == True`. Keep `MODEL_HASH` and `MODEL_VERSION` at the frozen checkpoint SHA. The macOS development host used for Phase 3 has no NVIDIA GPU, so its CPU results do not establish CUDA acceptance.

## Synthetic CPU reference and GPU gate

The benchmark synchronizes CUDA before and after every measured operation. It records model initialization, first and warmed prediction/occlusion, and peak CUDA allocation. Run in a clean output directory; the command refuses to overwrite existing evidence:

```sh
PYTHONPATH=. python -m worker.benchmark \
  --frozen-root /READ-ONLY-FROZEN-ROOT \
  --device CPU \
  --benchmark-output /PRIVATE-OUTPUT/cpu-benchmark.json \
  --bundle-output /PRIVATE-OUTPUT/cpu-reference.json

PYTHONPATH=. python -m worker.benchmark \
  --frozen-root /READ-ONLY-FROZEN-ROOT \
  --device CUDA \
  --compare-to /PRIVATE-OUTPUT/cpu-reference.json \
  --benchmark-output /PRIVATE-OUTPUT/gpu-benchmark.json \
  --bundle-output /PRIVATE-OUTPUT/gpu-result.json
```

The comparison gate is fixed in `worker/consistency.py`: absolute probability and derived-value difference at most `1e-4`, decoded response PNG difference at most two 8-bit levels, exact candidate mask, indexing, geometry, schema, and model/input hashes. Encoded PNG hashes may differ. A failed comparison writes both diagnostic files and exits nonzero; do not change the tolerance after examining a GPU result.

## Protocol and storage boundaries

- The Worker uses `POST /api/v2/workers/register`, `/heartbeat`, and `/jobs/claim`. It submits to `POST /api/v2/workers/jobs/{job_id}/result`, the Backend v2 alias explicitly requested for Phase 1. The frozen protocol also defines `/workers/results`; the payload is identical.
- A Claim key is written with mode `0600` before its request. If the response is lost, the same UUID is replayed with capacity zero. No token, signed URL, DICOM, or lease token is written to this state file.
- The first active Heartbeat must confirm the server-time lease before inference starts. Heartbeats continue every 15 seconds on a separate thread during classification or occlusion. On a temporary Backend outage the Agent pauses new claims, retries Heartbeat with backoff, and re-registers if Backend reports `WORKER_NOT_REGISTERED`. A stale or expired Attempt is never submitted as a new result. An uncertain upload is retried with identical manifest and assets, including one replay after local lease loss to retrieve a saved acceptance response.
- Signed input downloads require HTTPS and a matching SHA-256. DICOM and generated assets live only in a private temporary attempt directory and are removed after success, failure, or lease loss. A startup sweep removes this Worker's crash remnants older than 24 hours.
- Result JSON carries the raw numeric occlusion response in `positions` and `scale_summaries`, with model, preprocessing, protocol, Case, Slice, and coordinate-space metadata. Backend v2 currently accepts PNG assets only, so the frozen 14×14 comparison JSON is converted into a display PNG while the exact per-position values remain in the result. Quantitative 14×14 asset retrieval would require a Backend contract extension; the Worker does not change Backend code.
- The Worker sends only stable error codes in failure manifests. It does not determine final Job state or retry count. Backend v2 owns those transitions.

## Local verification

`tests/test_worker/` uses an in-memory HTTPS Backend and a mock inference runner. The repository's synthetic DICOM can also be run through `FrozenRunner` against a read-only frozen root. No formal test pixels or Stage 1 validation results are used.
