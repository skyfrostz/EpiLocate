# EpiLocate Vue Frontend v1

Vue 3 + TypeScript + Vite + Pinia + Vue Router + Ant Design Vue. This directory is the formal web UI; the existing Gradio page remains a research/debug interface.

## Phase 1 scope

The app shell, `/`, `/cases`, `/cases/:id`, `/jobs/:id` and `/results/:id` routes, Pinia stores, and an API v2 client are implemented. Screens intentionally distinguish “not loaded” from an empty server result. Case list/detail data, Job polling, Result display and Cornerstone3D viewer belong to the next phases. No clinical result is fabricated.

The API client follows the supplied Backend API Contract v2.0 Freeze: prefix `/api/v2`, Case/Prediction/Job/Result paths, idempotency headers for writes, and error fields. It uses same-origin credentials and does not define a login route because authentication/refresh is a separate deployment contract. Only the Backend can decide owner access. The SPA never contains a Worker token.

## Local commands

```sh
cd frontend
npm ci
npm run dev
npm run test
npm run build
```

Open `http://127.0.0.1:5183/`. For a separate local Backend v2, set `API_PROXY_TARGET` to its loopback origin in `frontend/.env.local`; see `.env.example`. The development server binds to loopback on 5183 and refuses to take another process's port. The UI does not need a running Backend for Phase 1 route/layout review.

## Contract boundaries

- Case creation and upload are separate operations. Upload is single de-identified DICOM and returns `READY`, which does not imply inference success.
- Job states are `CREATED`, `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`. There is no v2 cancellation route.
- Result data and image assets must come from owner-authorized `/api/v2/results/...` routes. The Phase 1 UI does not show placeholder probability, heatmap, model version or patient identity as real data.
- Viewer integration is reserved for Phase 3; this scaffold does not load DICOM pixels or instantiate Cornerstone3D.
