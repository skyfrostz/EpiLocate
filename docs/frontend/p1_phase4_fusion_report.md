# P1 Phase 4 — Heatmap–CT coordinate fusion handoff

**Scope:** `feature/p1-heatmap-ct-fusion`, created from local `p0/integration` at `02c8ef9c86d2b4aa338a38142bee25ee2234dc34`. The branch has frontend, frontend test, and documentation changes only. The final commit SHA is in the task handoff. `p0/integration`, FrozenBaseline, model/checkpoint, Worker protocol and Backend API were not changed.

## Acceptance boundaries

| Claim | Evidence and boundary |
| --- | --- |
| **Geometry verified** | Audited the exact frozen resize/occlusion path and API metadata; unit tests cover edge/center mapping, 16/32/64 bounds, 14-cell projection, invalid metadata, and viewport affine. Browser marker checks include non-square 112×80 DICOM, non-equal spacing, rotated orientation, zoom, pan and resize. This is 2D slice pixel geometry only. |
| **Visual rendering verified** | Browser screenshots show separate Cornerstone CT and canvas overlay, response/valid-candidate/comparison layer selection, opacity, hide/show and refresh recovery of scale, layer, opacity, zoom and pan. No permanent CT pixel compositing. |
| **Real integration verified locally** | An isolated HTTPS Backend, PostgreSQL 16, private MinIO, real CPU Worker and Vue browser processed an anonymous synthetic DICOM. Both Jobs completed with `source=LIVE_CASE`; three scales yielded 729/169/36 positions and nine protected PNG assets. The browser used the authorized Result/Case routes. This is local integration, not deployment acceptance. |
| **Clinical validity NOT established** | Model response layers are not lesion annotations; no 3D registration, clinical localization, diagnostic validity or CUDA numerical validation was tested here. |

## Geometry contract and implementation

See [Heatmap–CT Geometry Contract Report](heatmap_ct_geometry_contract.md) for the source audit and the missing future `spatial_transform` fields. The audited preprocessing maps raw DICOM `Columns×Rows` directly to 224×224 with bilinear antialias resize; there is no crop or padding in this version. The overlay gate therefore accepts only the exact audited model, preprocessing and protocol versions, matching raw DICOM SHA-256, Case/Slice dimensions, `LIVE_CASE`, valid layer semantics, matching asset manifest and PNG dimensions. Missing/inconsistent metadata, an invalid candidate, an unsupported future crop/pad version or a non-affine runtime transform leaves the independent authorized heatmap visible while disabling overlay.

The heatmap raster uses continuous pixel **edges**: raw `(x,y)` is `(column,row)`; model `(u,v)=(224x/Columns,224y/Rows)`. Occlusion grid `(x,y)` is the top-left **model-input** pixel; block sizes 16/32/64 are not raw-pixel squares. Response and candidate are separate 224-space rasters; comparison is a separate 14×14 area-average grid. The renderer projects raw edge `(x,y)` with its actual StackViewport `imageData.indexToWorld([x−0.5,y−0.5,0])`, then `worldToCanvas`. Four Cornerstone-projected corners define the canvas affine; a non-affine fourth-corner mismatch above 0.25 CSS px disables drawing. Camera events and `ResizeObserver` recompute the affine. The CT retains Cornerstone window/level handling.

A browser check caught a significant early mismatch: Cornerstone's standalone `imageToWorldCoords` produced corner positions that did not match StackViewport rendering when `PixelSpacing=[0.7,1.2]`. That path was removed before acceptance. The final implementation uses the viewport's rendered `imageData.indexToWorld`, including its spacing/direction. This distinction is essential for non-square images and unequal spacing.

## Quantified spatial validation

`frontend/geometry-qa/create_fixture.py` creates anonymous 112×80 DICOMs with known pixel values, with and without unequal spacing and orientation. `smoke.html` places five red 8×8 markers on a transparent 224×224 raster at four corners and the center; `measure.js` finds red-pixel centroids on the overlay canvas and compares them with Cornerstone's rendered index-to-world → canvas coordinates. Reported errors include CSS pixel raster rounding and thresholding. No manual image offset or stretch was applied.

| Browser condition | Overlay canvas | Max marker-center error |
| --- | ---: | ---: |
| Non-square image, default view | 472×300 | 0.143 CSS px |
| Zoom 0.8 | 472×300 | 0.214 CSS px |
| Drag pan +30,+20 at zoom 0.8 | 472×300 | 0.500 CSS px |
| Resize 520→700 browser width, preserving pan/zoom | 652×300 | 0.214 CSS px |
| Unequal spacing + rotated DICOM, zoom 0.4096 | 472×300 | 0.444 CSS px |
| Same oriented image at 652×300 | 652×300 | 0.424 CSS px |

For the 652×300 oriented view, the **CT-only** grayscale bounding box from the browser screenshot is `[192,94]–[459,205]` inclusive. The four transformed raw-image edges predict `[192.47,94.36]–[459.53,205.64]` in CSS pixels. The largest edge difference is 0.64 CSS px, consistent with integer-pixel raster bounds. Hiding the overlay changed nontransparent overlay pixels from 608 to 0; re-enabling returned to 608. The Layer and Result gates also reject missing source SHA, wrong slice, mismatched dimensions, invalid candidate, unknown axes and future preprocessing versions in unit tests.

## Real browser and security checks

The browser read the completed real occlusion Result, original DICOM and all nine protected assets. Each scale selected a 224×224 response and candidate layer plus a distinct 14×14 comparison layer, with no viewer error. The result page showed `LIVE_CASE`, model/protocol versions, single-slice prediction and the “model decision response, not lesion annotation” warning. At 32 px, overlay visibility, 75% opacity and layer selection survived page reload; the redraw contained 126,000 nontransparent canvas pixels. In a separate refresh test at 64 px, zoom 0.8 and pan approximately (+20,+10) CSS px were saved and restored along with layer and opacity; 614×301 before/after viewer screenshots had **zero differing RGB pixels**. The local Vite dev proxy injected the test user's Bearer token **server-side**; the browser did not receive S3 credentials, private object keys or a public MinIO URL.

For both the protected Result asset route and DICOM route, the owning test user received HTTP 200, a second database user received 404 and an unauthenticated request received 401. The MinIO bucket remained private. Authentication was exercised through API credentials and a development proxy, not a production login flow.

### Browser captures

- [Real Result, 16 px](screenshots/real-cpu-result-16.png), [32 px](screenshots/real-cpu-result-32.png), [64 px](screenshots/real-cpu-result-64.png)
- [Scale comparison, 64 px](screenshots/real-cpu-comparison-64.png)
- [CT overlay crops, 16](screenshots/real-cpu-overlay-16.png), [32](screenshots/real-cpu-overlay-32.png), [64](screenshots/real-cpu-overlay-64.png)
- [Non-square spatial markers](screenshots/geometry-markers-default.png), [pan](screenshots/geometry-markers-pan.png), [resize](screenshots/geometry-markers-resize.png), [oriented](screenshots/geometry-markers-oriented.png)
- [Oriented CT only](screenshots/geometry-oriented-ct-only.png) and [same view with markers](screenshots/geometry-oriented-overlay.png)
- [Real CPU viewer before refresh](screenshots/real-cpu-camera-before.png) and [after refresh](screenshots/real-cpu-camera-after.png)

All captures use synthetic DICOM or an anonymous synthetic upload. Local access tokens, private cert/key, PostgreSQL data, MinIO data and generated DICOM files remain in ignored `frontend/.local` or task-scoped Docker volumes.

## Regression results

| Gate | Result |
| --- | --- |
| Frontend unit/integration tests | 32 passed, including geometry gate and rotated unequal-spacing transform. Existing jsdom `scrollTo` notice only. |
| Frontend TypeScript/build | Passed; Cornerstone codec browser-externalization and large chunk warnings remain from installed dependency bundle. |
| Backend suite | 16 passed, including the pinned real frozen Worker integration with the optional Worker environment supplied; one Starlette/httpx deprecation warning. |
| Backend PostgreSQL migration | Alembic head applied; `validate_migrations` passed with 14 required tables and 16 actual tables. |
| MinIO storage | Private bucket created; production-like schema/object round trip passed (1 test). |
| Worker tests | 29 passed. |
| Real CPU Worker E2E | Passed: Prediction + Occlusion `COMPLETED`, `LIVE_CASE`, nine assets, three position counts 729/169/36. |
| Auth/ownership | Owner 200, other user 404, anonymous 401 for asset and DICOM routes. |

## Remaining risks

1. Backend v2 does not yet return an explicit immutable raw→model transform, crop/pad history or transform hash. This branch uses an exact audited version allowlist plus source SHA and disables overlay for future/unknown preprocessing. The proposed minimal contract extension is in the geometry report and needs Integration Lead review; no API field was added here.
2. The browser check covers synthetic single-slice CTs and the current frozen DICOM path. Additional transfer syntaxes, photometric modes, patient orientations and real de-identified cases need independent QA. The oriented fixture establishes in-plane pixel alignment, not 3D registration.
3. Build warnings for codec browser externalization and the large Cornerstone bundle warrant a separate packaging/performance review. The tested fixture loaded and rendered in the browser; that does not prove every codec path.
4. This local isolated stack is not public production deployment; CUDA device execution and clinical validity remain outside Phase 4.
