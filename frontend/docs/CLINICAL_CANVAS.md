# Clinical Canvas v1 frontend

Local implementation from `2be89143a8abccb3c3896a8f53633e490cf79b28`; branch `feature/clinical-canvas-v1`. Product remains EpiLocate.

- Overview stays `/`; existing safe login destinations remain supported.
- `/jobs` is a bounded, in-memory collection of GET-confirmed jobs. Refresh/session revalidation clears it.
- `/system` only checks the existing Case API on explicit request. GPU/Worker/Storage/Queue and privileged capabilities are not integrated.
- `/preferences` stores only theme/density/reducedMotion. `/settings` redirects here.
- Cases search is local to loaded pages. READY means input availability, not completed analysis.
- Viewer, API, auth and lockfile remain at baseline; see SHA-256 evidence in the delivery report.

## Validate locally

From `frontend/`:

```sh
npm ci --no-audit --no-fund
npm test
npx vue-tsc -b
VITE_PUBLIC_BASE=/mvp/ npm run build
node geometry-qa/generate-fixtures.mjs
npm run dev -- --host 127.0.0.1 --port 5198 --strictPort
```

In another terminal, with an installed Playwright module and Chrome:

```sh
PLAYWRIGHT_MODULE=file:///absolute/path/to/playwright/index.mjs FRONTEND_QA_BROWSER=chrome node geometry-qa/clinical-canvas-browser.mjs --phase final --url http://127.0.0.1:5198 --out .local/clinical-canvas
```

The updated harness preserves prior browser scenarios with current accessible labels; `first-round-browser.mjs` remains historical. `--phase regression` runs the original workflow/geometry scenarios, `--phase extra` runs new interaction/privacy/contrast/renderer checks. `--phase final` also creates the viewport/theme matrix. All business APIs are intercepted with synthetic fixtures, and non-loopback requests are blocked. It is not a deployed API or GPU test.

## Delivery

[Implementation report](../../docs/frontend/CLINICAL_CANVAS_IMPLEMENTATION_REPORT_V1.md), [capability matrix](../../docs/frontend/FRONTEND_CAPABILITY_MATRIX_V1.md), [backend proposals](../../docs/frontend/BACKEND_CAPABILITY_REQUEST_V1.md). No push, merge or deployment was performed.
