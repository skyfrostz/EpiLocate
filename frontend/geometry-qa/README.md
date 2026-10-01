# Single-slice geometry browser check

## First-round local acceptance (2026-10-01)

From `frontend/`, use Node 24 and the locked dependencies:

```sh
npm ci
node geometry-qa/generate-fixtures.mjs
npm run test
npm run build
FRONTEND_DEV_PORT=5183 npm run dev
```

In another terminal, run `node geometry-qa/first-round-browser.mjs`. It needs an available Playwright module and installed Edge (default `msedge`). Set `PLAYWRIGHT_MODULE` to a module file URL if Playwright is supplied by a workspace runtime rather than installed locally. Optional environment settings: `FRONTEND_QA_URL` (default `http://127.0.0.1:5183`), `FRONTEND_QA_BROWSER`, and `FRONTEND_QA_OUTPUT` (default ignored `.local/first-round-browser`). PowerShell uses `$env:FRONTEND_DEV_PORT='5183'` / `$env:PLAYWRIGHT_MODULE='file:///absolute/path/playwright/index.mjs'` rather than the shell prefix syntax above.

The portable fixture generator requires no Python dependency. Both generators create only synthetic DICOMs in ignored `.local/`. Browser acceptance intercepts all auth/business APIs and only permits a loopback target. It executes actual Cornerstone decoding/rendering, 15 scenarios including cross-tab identity synchronization and owned image/naturalized metadata cache release, desktop/mobile screenshots and six five-marker geometry measurements. These results do not constitute real account, live API or GPU inference verification. The implementation run passed all scenarios, reported zero page errors and maximum marker error 0.3031 CSS px.

## Manual geometry harness

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
