# Heatmap–CT Geometry Contract Report

Baseline: `02c8ef9c86d2b4aa338a38142bee25ee2234dc34` on `p0/integration`. Scope: the frozen `baseline_resnet18` / `formal-resnet18-baseline-rule-b-v1` / `stage1-occlusion-instability-v1` implementation in this baseline. This is a **single-slice pixel-space** mapping, not a 3D or clinical registration.

## Phase 0 audit

| Item | Verified implementation | Consequence |
| --- | --- | --- |
| DICOM dimensions | `backend_v2/services/cases.py` reads `Columns` as width and `Rows` as height; the authorized Case API returns `width_px,height_px`. The synthetic fixture is 112 columns × 80 rows. | x is column, y is row. Never exchange the two. |
| Spacing and orientation | `src/preprocessing.py` reads `PixelSpacing` into QC metadata but does not use it in the model resize. The original DICOM remains available through an owner-checked, temporary `/api/v2/cases/{case_id}/dicom` route. The current 112×80 fixture has no `PixelSpacing`, `ImageOrientationPatient`, or `ImagePositionPatient`. | Pixel-space alignment can be tested; patient-space/3D registration cannot be claimed. Cornerstone's actual image-plane mapping, including any synthesized fallback for absent tags, must be queried at runtime. |
| Model input | `src/preprocessing.py` windows to HU, normalizes, then uses `torchvision.transforms.functional.resize([224,224], BILINEAR, antialias=True)`. Its pretrained weight preset's resize/crop is explicitly skipped. `algorithm/service.py` enforces `image_size=224`. | Direct, anisotropic resize of a non-square image; no crop or pad in this exact version. Pixel centers follow the half-pixel resize convention. |
| Occlusion | `scripts/occlusion_runner.py::build_grid` emits `(x,y)` top-left integer positions; `mask_resized` writes `[:, y:y+block_size, x:x+block_size]`. Strides are 8, 16, 32 for 16, 32, 64 px blocks. Expected position counts: 729, 169, 36. | Positions are **model-input** pixel indices, not raw DICOM indices or viewport coordinates. |
| Response/candidate rasters | `rasterize_block_scores` accumulates the selected score over each 224-space occlusion square and divides by coverage count, returning a 224×224 raster. `algorithm/service.py` writes 224×224 PNGs. | Both `CANDIDATE_RESPONSE` and `CANDIDATE_TOP10` are model-input-space rasters. Their values differ in meaning; never blend them into a new interpretation. |
| Comparison raster | `project_area_average` projects the 224×224 response into a 14×14 area-average grid. `worker/inference.py` converts the numeric grid to a 14×14 PNG for Backend v2. Each cell covers a 16×16 model-input region in this version. | `COMPARISON_GRID` is a derived coarse raster, not a 224-pixel image. It must retain a separate semantic label and interpolation warning. |
| Layer metadata | `scale_summaries` provides `asset_id,layer_kind,width,height,coordinate_space,value_min,value_max,origin=TOP_LEFT_PIXEL_EDGE,x_axis=RIGHT,y_axis=DOWN,display_interpolation_only`; `assets` repeats ID/kind/dimensions/space/MIME. Backend validates manifest↔PNG dimensions and SHA-256. | Match both descriptors, Result ID, slice ID, decoded PNG dimensions, and source before display. A null candidate layer must remain absent. |
| Viewport | Installed Cornerstone3D 5.11.0 exposes `StackViewport.getImageData().imageData.indexToWorld(index)` and `worldToCanvas(world)`. The rendered imageData origin is the **center** of pixel (0,0); raw edge (x,y) is continuous index (x−0.5,y−0.5,0). Camera changes produce `CAMERA_MODIFIED`; rendered frames produce `IMAGE_RENDERED`. | Use the rendered StackViewport imageData transform for four raw-edge anchors on every camera/size change. The standalone `imageToWorldCoords` helper produced an unequal-spacing mismatch in the oriented fixture and must not be used here. |
| Result API | `GET /api/v2/results/{id}` provides `slice_id`, `source`, version fields, `provenance.input_sha256`, scale summaries, and asset descriptors; it does **not** expose an explicit raw-to-model affine, crop rectangle, pad offsets, interpolation convention, DICOM spacing/orientation, or a transform-version hash. | This client enables overlay only for the audited exact versions and matching original-DICOM SHA-256. Other or incomplete metadata disables overlay while retaining standalone heatmaps. |

## Explicit coordinate chain for the audited version

Use continuous **pixel-edge** coordinates. Raw DICOM has width `C=Columns`, height `R=Rows`; pixel `(column c,row r)` has center `(c+0.5,r+0.5)`. Model input is 224×224. There is no crop or padding in the audited preprocessing path:

```text
raw edge (x,y) -> model edge (224*x/C, 224*y/R)
model edge (u,v) -> raw edge (u*C/224, v*R/224)
model pixel center (j+0.5,k+0.5) -> raw edge ((j+0.5)*C/224, (k+0.5)*R/224)
16/32/64 grid position (x,y) -> model square [x,x+block) × [y,y+block)
224 heatmap raster pixel edge (u,v) -> model edge (u,v)
14 comparison raster pixel edge (g,h) -> model edge (16*g,16*h)
raw edge (x,y) -> rendered imageData.indexToWorld([x-0.5,y-0.5,0]) -> viewport.worldToCanvas -> display CSS pixels
```

For the 112×80 fixture, raw-to-model edge affine is `diag(2,2.8,1)`, agreeing with `docs/interfaces/fixtures/p0_http_vector.json`. Because the transform uses edges, drawing a 224×224 response raster across the entire raw image rectangle introduces no arbitrary half-pixel translation. The pixel-center convention is tested separately. An additional generated 112×80 fixture sets `PixelSpacing=[0.7,1.2]`, an in-plane rotated orientation, and a nonzero image position. In Cornerstone's rendered imageData, spacing is `[1.2,0.7]` along its image x/y axes. Direct use of `imageToWorldCoords` instead placed the red corner markers outside the CT: the browser check exposed this mismatch and the implementation now uses `indexToWorld` from the rendered viewport.

## Mandatory overlay gate and missing general contract

The current API is **not self-describing for arbitrary future preprocessing**. The frontend gate must verify: exact known `model_id`, `preprocessing_version`, `protocol_id`, `source=LIVE_CASE`, `kind=OCCLUSION`, Result/Case/Slice ownership relation, original DICOM SHA-256 equal to `provenance.input_sha256`, original DICOM dimensions equal to Case metadata, supported layer semantics, matching asset manifest, decoded PNG size, and a finite, invertible Cornerstone image-to-canvas transform. On any failure, display the independent authorized heatmap and a reason; never draw an approximate overlay.

A minimal **future** Backend/Worker contract proposal is an immutable, versioned per-Result `spatial_transform` with raw `{rows,columns,source_sha256}`, model `{width,height}`, `raw_to_model_edge_affine` (nine row-major numbers), preprocessing operations (resize interpolation/antialias, crop rectangle, pad offsets), and a transform implementation/version hash. Each layer would reference the transform ID plus its raster-to-model edge affine. The Backend should validate Worker-submitted metadata and expose only non-sensitive geometry. This proposal does **not** modify the frozen algorithm or current v2 API contract; Integration Lead approval is required before adopting it.

`candidate_status=insufficient_positive_response` means candidate mask/area are absent. None of these response layers is a lesion annotation. Spacing and orientation, when present, describe patient physical space but do not change the audited raw-edge→model-edge resize; when absent, physical coordinate claims remain unavailable.
