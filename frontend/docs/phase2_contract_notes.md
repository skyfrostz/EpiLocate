# Phase 2 API and Viewer integration notes

Scope: Vue branch `feature/frontend-v1`, based on Phase 1 commit `8a7952a1b0819e3db1630c3c486cf5544ef6a99a`.

## Frozen v2 paths used

- `GET /api/v2/cases`, `GET /api/v2/cases/{case_id}`, `GET /api/v2/cases/{case_id}/dicom`, `POST /api/v2/cases`, `POST /api/v2/cases/{case_id}/upload`
- `POST /api/v2/predictions`, `POST /api/v2/jobs/occlusion`, `GET /api/v2/jobs/{job_id}`
- `GET /api/v2/results/{result_id}`, `GET /api/v2/results/{result_id}/assets/{asset_id}`

Writes use an `Idempotency-Key` per user action and retain it across a retry after an uncertain transport failure. The UI does not call Worker routes, `/api/v1` or a cancellation route. Result assets are fetched as private PNG blobs via the API client and revoked when the page changes.

## Actual Backend v2 behavior checked read-only

Backend commit `5df1e05635bccbc872e7b697baf73957e96b4842` uses `Authorization: Bearer` for user routes. The deployment authentication/refresh contract is not present; a loopback Vite proxy can inject a locally provisioned user token without sending it to the browser. 401 stops Job polling and is shown to the user. Job `progress` and ETA can be null. A `COMPLETED` Job provides `result_id`; only then does the UI navigate to Result.

The Result's nested `prediction` contains prediction numbers; top-level Result fields contain `model_version`, `preprocessing_version`, `protocol_id`, and `source`. The front-end types follow this actual v2 response. Heatmap references are in `scale_summaries[].response_layer`; each displayed asset must match the Result's asset descriptor by ID, layer kind, coordinate space, width, height, and PNG media type. The browser also checks decoded image dimensions. `candidate_status=insufficient_positive_response` is displayed as such, with no candidate region drawn.

## Current limits

- Backend v2 exposes an authorized, read-only original-DICOM endpoint. Case refresh retrieves the retained object as a private `application/dicom` Blob and Cornerstone reconstructs its local File; expired inputs remain unavailable.
- Raw DICOM coordinates and `ALGORITHM_224` response coordinates cannot be overlaid without approved spatial metadata and viewport mapping. The Viewer overlay interface rejects mismatched slice IDs, coordinate space, dimensions or axes and does not paint an unverified overlay.
- A local HTTPS Backend v2 instance with SQLite, S3-compatible object storage, locally provisioned tokens and the frozen Worker accepted the synthetic 112×80 DICOM and completed both PREDICTION and OCCLUSION Jobs. Browser evidence covers READY, COMPLETED, LIVE_CASE prediction, LIVE_CASE heatmap and refresh recovery. No deployed authentication or token-refresh flow was used.
- Cornerstone 5.11.0 adds 9 npm audit advisories with no automatic fix available. The heavy viewer code is loaded only when a local DICOM `File` is present.

## Phase 2 verification evidence

- Browser against the isolated Backend v2 instance: `screenshots/phase2-case-real-api.png` shows the READY Case and Cornerstone rendering of the accepted synthetic 112×80 DICOM. `screenshots/phase2-job-real-api.png` shows a PREDICTION Job after a page reload; `screenshots/phase2-occlusion-job-real-api.png` shows an OCCLUSION Job. The isolated database confirmed its requested scales `[16, 32, 64]`. Both Jobs remained CREATED because no Worker was attached.
- `screenshots/phase2-cornerstone-synthetic.png` documents the standalone Cornerstone browser smoke. `screenshots/phase2-cases-api-unavailable.png`, `phase2-job-api-unavailable.png`, and `phase2-result-api-unavailable.png` document unavailable API states with no Mock fallback.
- Frontend tests cover Case API/loading/401, browser fetch invocation, Job polling/terminal/401/timeout, LIVE_CASE Result rendering and asset lifecycle, and provenance/overlay rejection. The contract-shaped Result in tests is a deterministic test fixture only; it is never served by the running app.
- The integration evidence is local-only and uses temporary tokens, SQLite, Moto S3-compatible storage and a self-signed HTTPS CA. It is not production deployment evidence.
