# Single-slice geometry browser check

These fixtures contain generated pixel values only. `create_fixture.py` requires `pydicom` and writes ignored DICOM files into `frontend/.local/`. No patient image is checked in.

```bash
python frontend/geometry-qa/create_fixture.py
FRONTEND_DEV_PORT=5187 npm --prefix frontend run dev
```

Open `http://127.0.0.1:5187/geometry-qa/smoke.html` and `?oriented=1`. The second fixture has 112 columns, 80 rows, `PixelSpacing=[0.7,1.2]`, rotated in-plane direction cosines, and a nonzero image position. Both show five red spatial markers at the four raster corners and center. This page is a test harness, not a diagnostic or production page. The Vite production build uses `frontend/index.html`, so this page is not emitted in `dist`.

With the task-scoped Playwright CLI session on either page, run:

```bash
playwright-cli run-code --filename frontend/geometry-qa/measure.js
```

The script compares the red raster marker centers against **the rendered StackViewport's** `imageData.indexToWorld` and `worldToCanvas` mapping, reporting each CSS-pixel error. Change zoom, drag to pan, and resize the browser, then rerun it. A screenshot alone is insufficient: compare the oriented fixture's CT-only pixel bounds against the four transformed raw-image edges as described in `docs/frontend/p1_phase4_fusion_report.md`.
