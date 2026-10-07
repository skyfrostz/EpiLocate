# EpiLocate P1 Phase 4.5 — Integration Acceptance

**Role:** Integration Lead
**Integration worktree:** `LOCAL_WORKTREE/EpiLocate-p1-phase45-integration`
**Branch:** `integration/p1-phase45-heatmap-ct`
**Base:** `02c8ef9c86d2b4aa338a38142bee25ee2234dc34` (`p0/integration`)
**Integrated frontend commit:** `77ef944ec88db6992a16b395a13434d7065f4186`
**Merge commit before this report:** `580b58ed2b5933c32198165e71be91198e2224de`

## Acceptance result

The Phase 4 frontend was merged in an isolated worktree with no conflicts. The frozen model, Worker protocol, Backend API and algorithm code were not changed by this integration. The integrated result is accepted for local P1 Phase 4.5 handoff and can advance `p0/integration` after this report commit.

## Real local stack

- Frontend Vite: `127.0.0.1:5188`
- Backend HTTPS: `127.0.0.1:8898`
- PostgreSQL: `127.0.0.1:55453`
- MinIO private endpoint: `127.0.0.1:59110`; protected HTTPS proxy: `127.0.0.1:59112`
- Worker: pinned Worker v1 code with the frozen baseline, `CPU` device only
- Synthetic DICOM SHA-256: `8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee`

## Evidence

- Real upload created an anonymous case and slice; DICOM retrieval matched the uploaded bytes.
- Prediction and Occlusion jobs both reached `COMPLETED`.
- Both results were `LIVE_CASE` with model hash `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734` and positive probability `0.025618407875299454`.
- Occlusion position counts were 729 / 169 / 36 for 16 / 32 / 64 px; the result exposed nine protected assets.
- Browser result page displayed `LIVE_CASE`, model/protocol metadata, `PIXEL CONTRACT MATCHED`, CT and overlay canvases, layer selection, opacity, and 16 / 32 / 64 px switching.
- Browser refresh restored the selected 64 px scale, candidate layer, overlay visibility and the authorized heatmap/CT view.
- Owner requests returned 200; a second database user received 404; unauthenticated requests received 401 for Case/DICOM/Result/Asset routes.
- Browser screenshots and raw E2E JSON are retained in ignored `.local/integration45/` task evidence.

## Regression gates

| Gate | Result |
| --- | --- |
| Frontend tests | 32 passed; existing jsdom `scrollTo` notice only |
| Frontend build | Passed; existing Cornerstone codec externalization and chunk-size warnings |
| Backend tests | 16 passed; one Starlette/httpx deprecation warning |
| PostgreSQL/MinIO production-like test | 1 passed with the isolated private bucket |
| Worker tests | 29 passed |
| Real CPU Worker E2E | Passed: two completed jobs, nine assets, 729/169/36 positions |
| Auth and ownership | Owner 200, other user 404, anonymous 401 |

## Boundaries

- Geometry is verified for the audited single-slice pixel-space contract only; it is not 3D registration.
- Visual rendering and local real integration are verified. Clinical validity, lesion localization, CUDA execution and public production deployment are not established.
- The current API does not expose a general immutable raw-to-model transform. The Phase 4 exact-version/source-hash gate remains required for overlay safety; future preprocessing variants must keep overlay disabled until the contract is extended and reviewed.
