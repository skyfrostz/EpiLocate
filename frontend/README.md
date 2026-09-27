# EpiLocate Vue Frontend v1

Vue 3 + TypeScript + Vite + Pinia + Vue Router + Ant Design Vue. This is the formal web UI. The old Gradio page remains a research/debug interface.

## Phase 2 scope

The app reads Case, Job and Result records from the frozen Backend v2 `/api/v2` routes. Case creation and single de-identified DICOM upload are separate operations. From a READY Case, the user can create a slice-level Baseline prediction Job or a 16/32/64 px occlusion Job. The Job page polls by its public ID, survives a page refresh, stops at `COMPLETED` or `FAILED`, and reports network, 401 and timeout errors. Only a completed `LIVE_CASE` Result can be displayed. Positive-class probability and predicted-class confidence are shown separately. Response PNGs come from the Result-owned asset endpoint and are labelled as model decision response, never as lesion annotation.

The `CornerstoneSliceViewer` component loads a DICOM `File` through Cornerstone3D's local file manager after upload or a retained `GET /api/v2/cases/{case_id}/dicom` read on refresh. Its overlay input is guarded by slice ID, coordinate space, dimensions and axis metadata. Actual CT/heatmap overlay is deferred because raw-to-algorithm transform metadata is not part of this page contract.

## Local commands

```sh
cd frontend
npm ci
npm run test
npm run build
npm run dev
```

Open `http://127.0.0.1:5183/`. The server binds to loopback and refuses an occupied port. For a separately running Backend v2, configure ignored `frontend/.env.local`:

```sh
VITE_API_BASE_URL=/api/v2
API_PROXY_TARGET=http://127.0.0.1:8890
API_PROXY_USER_TOKEN=<locally provisioned user token>
```

`API_PROXY_USER_TOKEN` is read by the local Vite server and added to proxied requests; it is never included in the Vue bundle. Use only a database-backed user token, never a Worker token. Do not commit `.env.local`. Production must provision an expiring/revocable Backend user credential or perform a controlled OIDC-to-bearer mapping at the edge; the browser must not receive the server credential. Without an authenticated Backend v2, the UI shows an API error and does not fall back to a Mock result.

## Contract boundaries

- Backend v2 Job states are `CREATED`, `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`. There is no v2 cancellation route.
- `READY` means input is eligible to queue; it does not mean a model ran.
- Result `source` must be `LIVE_CASE`; `/api/v1` Mock data is never queried by this UI.
- Only the Result's own `CANDIDATE_RESPONSE` image asset is shown. It uses algorithm coordinates and is not overlaid on raw CT pixels.
- The model ID input defaults to the currently documented `baseline_resnet18` and can be edited if a deployment provisions another active model.
- `npm audit` currently reports 9 transitive Cornerstone-related advisories (3 moderate, 6 high) with no automatic fix available. Review upstream updates before production deployment.

See [Phase 2 contract notes](docs/phase2_contract_notes.md) for implementation limits and test evidence.
