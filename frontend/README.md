# EpiLocate Clinical Canvas

Vue 3 + TypeScript + Vite + Pinia + Vue Router + Ant Design Vue. This is the formal web UI. The old Gradio page remains a research/debug interface.

## Phase 2 scope

The app reads Case, Job and Result records from the frozen Backend v2 `/api/v2` routes. Case creation and single de-identified DICOM upload are separate operations. From a READY Case, the user can create a slice-level Baseline prediction Job or a 16/32/64 px occlusion Job. The Job page polls by its public ID, survives a page refresh, stops at `COMPLETED` or `FAILED`, and reports network, 401 and timeout errors. Only a completed `LIVE_CASE` Result can be displayed. Positive-class probability and predicted-class confidence are shown separately. Response PNGs come from the Result-owned asset endpoint and are labelled as model decision response, never as lesion annotation.

The `CornerstoneSliceViewer` component loads a DICOM `File` through Cornerstone3D's local file manager after upload or a retained `GET /api/v2/cases/{case_id}/dicom` read on refresh. CT/heatmap overlay is enabled only when the existing slice, hash and audited pixel geometry contract matches; otherwise the independent heatmap remains available with the reason overlay was disabled.

## Local commands

Use a Node version compatible with the locked Vite and jsdom dependencies; Node 24 was validated for the mainline integration. The current Clinical Canvas regression and local/Mock browser scope are recorded in the [mainline integration report](../docs/consolidation/MAINLINE_INTEGRATION_20261007.md). Earlier first-round evidence is preserved in [its audit](docs/FIRST_ROUND_AUDIT.md).

```sh
cd frontend
npm ci
npm run test
VITE_PUBLIC_BASE=/mvp/ npm run build
npm run dev
```

The Vite server binds to loopback and refuses an occupied port. For session gateway integration, place Vite behind a local HTTPS origin and configure ignored `frontend/.env.local`:

```sh
VITE_API_BASE_URL=/api/v2
API_PROXY_TARGET=<local HTTPS browser session gateway>
```

Phase 5 browser access uses `session_gateway` for personal password login, a protected session cookie, CSRF, and per-member server-side Backend Bearer injection. Vite proxies both `/auth` and `/api/v2` to that gateway; it no longer injects a single development user token. Do not commit `.env.local`. The browser receives no Backend credential. Without an authenticated Backend v2, the UI shows an error and does not fall back to a Mock result.

## Contract boundaries

- Backend v2 Job states are `CREATED`, `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`. There is no v2 cancellation route.
- `READY` means input is eligible to queue; it does not mean a model ran.
- Result `source` must be `LIVE_CASE`; `/api/v1` Mock data is never queried by this UI.
- The Result viewer selects only authorized assets and overlays them on CT only when the audited single-slice pixel geometry contract matches.
- The model ID input defaults to the currently documented `baseline_resnet18` and can be edited if a deployment provisions another active model.
- `npm audit` currently reports 9 transitive Cornerstone-related advisories (3 moderate, 6 high) with no automatic fix available. Review upstream updates before production deployment.

See [Phase 2 contract notes](docs/phase2_contract_notes.md) for implementation limits and test evidence.
