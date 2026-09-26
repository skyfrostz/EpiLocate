# EpiLocate AI Worker v1

The Worker polls Backend API v2 over HTTPS. It runs one frozen Baseline task at a time, sends a heartbeat every 15 seconds, and uploads a result only while its Attempt lease is valid. It does not serve user requests or write to frozen validation outputs.

## Configuration

Set these variables in the Worker process environment:

| Variable | Meaning |
| --- | --- |
| `WORKER_ID` | Pre-provisioned anonymous `node_...` identifier |
| `BACKEND_URL` | HTTPS origin for Backend API v2, without `/api/v2` |
| `TOKEN` | Pre-provisioned Worker Bearer token; never use a user token |
| `MODEL_VERSION` | Full SHA-256 of the frozen Baseline checkpoint (`548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`) |
| `EPILOCATE_FROZEN_ROOT` | Read-only experiment root containing the checkpoint and frozen protocol/configuration |
| `WORKER_DATA_ROOT` | Private writable directory outside the frozen root, unique to this Worker |
| `WORKER_POLL_SECONDS` | Optional polling interval, default 5 seconds |

Run from this repository with an environment that has root `requirements.txt` and `gradio_service/requirements-gradio.txt` installed:

```sh
PYTHONPATH=. python -m worker
```

The existing `FrozenBaseline` currently executes on CPU. The Worker registers `accelerator=CPU` and does not advertise CUDA until the frozen service itself supports and verifies it. A missing or mismatched checkpoint prevents startup; it never falls back to Mock.

## Protocol and storage boundaries

- The Worker uses `POST /api/v2/workers/register`, `/heartbeat`, and `/jobs/claim`. It submits to `POST /api/v2/workers/jobs/{job_id}/result`, the Backend v2 alias explicitly requested for Phase 1. The frozen protocol also defines `/workers/results`; the payload is identical.
- A Claim key is written with mode `0600` before its request. If the response is lost, the same UUID is replayed with capacity zero. No token, signed URL, DICOM, or lease token is written to this state file.
- The first active Heartbeat must confirm the server-time lease before inference starts. Heartbeats continue on a separate thread during classification or occlusion. A stale or expired Attempt is never submitted. An uncertain result response is retried with identical manifest and assets.
- Signed input downloads require HTTPS and a matching SHA-256. DICOM and generated assets live only in a private temporary attempt directory and are removed after success, failure, or lease loss. A startup sweep removes this Worker's crash remnants older than 24 hours.
- Result JSON carries exact occlusion position values. Backend v2 currently accepts PNG assets only, so the frozen 14×14 comparison JSON is converted into a display PNG while the exact per-position values remain in the result. Quantitative 14×14 asset retrieval would require a Backend contract extension; the Worker does not change Backend code.
- The Worker sends only stable error codes in failure manifests. It does not determine final Job state or retry count. Backend v2 owns those transitions.

## Local verification

`tests/test_worker/` uses an in-memory HTTPS Backend and a mock inference runner. The repository's synthetic DICOM can also be run through `FrozenRunner` against a read-only frozen root. No formal test pixels or Stage 1 validation results are used.
