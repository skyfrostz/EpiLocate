# EpiLocate mainline integration, 2026-10-07

## Scope and provenance

The integration branch `codex/epilocate-main-consolidation` starts at public `origin/main` `14c114ab26226561615315f7d3d25e42fcec64cc`. The audited Clinical Canvas snapshot `feature/clinical-canvas-v1` `117ce7a61c6bd8ba6893ecb83445d8647c9965a1` was imported by file content, initially matching its tree `6cc89f8295735610f45e0c686c3dfd88a86a6050`. The resulting commit keeps the original public `main` ancestry; internal application and research branch histories are not merged as ancestors.

The integration then adapts the session validation, request timeout, accepted-Job idempotency and navigation focus behaviors from `origin/dot/mobile-navigation-focus-20261002` `8a5928fcdabfb0326e1f76182f6f54f4278eb022` to the Clinical Canvas UI, plus closed-set Worker diagnostics from `origin/codex/cloud-worker-safe-diagnostics` `f548a624588deb922131c0c07b83336e2bc0ff15`. It adds the four public D10 offline tools and tests from frozen `d88cc36a5d557e7330787d93b096a60a6cfe7d21`, and focused Stage 1 runner tests. The [source map](SOURCE_MAP.md) names the preserved paths and application boundaries; the [research status](../research/REPOSITORY_STATUS_20261007.md) separates D10's bounded pass, Stage B v1's inconclusive result, and the first-seed A/B/C non-evaluable stop.

No API version, database migration, FrozenBaseline, model checkpoint, real medical image, patient-level research output, server deployment, or GPU execution was added by this integration. The sole DICOM in the imported tree is the previously audited synthetic fixture. The former `MIDRC-RICORD-01.s5cmd` is removed from the current tree, but remains reachable in the original public `main` history; see [source provenance](../handoff/SOURCE_PROVENANCE.md). A final all-reachable-object publication audit is required before pushing.

## Candidate acceptance

| Check | This integration's evidence | Boundary |
| --- | --- | --- |
| Vue tests and typecheck/build | 155 tests in 18 files passed; `VITE_PUBLIC_BASE=/mvp/ npm run build` passed | Existing Cornerstone browser-externalization and large-bundle warnings remain. |
| Backend/Gateway | 51 targeted idempotency, Gateway and integration tests passed | SQLite/test storage and test client, not PostgreSQL/MinIO acceptance. |
| Worker diagnostics | 28 protocol tests passed in a dependency-complete local test environment | No live Worker or GPU execution. |
| D10 and Stage 1 tools | D10: 53 tests and 25 subtests; Stage 1: 8 focused tests passed | Synthetic/mocked tool tests do not repeat frozen CUDA or clinical validation. |
| Real local browser | 14 scenarios passed at isolated HTTPS `127.0.0.1:5298`, real Gateway/Backend, SQLite/TEST_STORAGE | The accepted Job remained `CREATED`; zero Workers/results. |
| Mock API browser | 10 scenarios passed against the production build, including Result refresh and six Cornerstone CT-overlay geometry groups | Positive Result and assets were predefined Mock API fixtures. |

Browser evidence is in the ignored local directory `frontend/.local/consolidation-20261007/` and is intentionally not published with credentials or generated synthetic images. The failed first browser attempt used a build without `/mvp/` base and loaded no application assets; rebuilding with the expected base and a complete rerun passed. Existing 5197-5200 services were left untouched; the harness accepts `--port-base` to isolate subsequent runs.

## Publication and recovery

The private pre-change manifest and verified bundle are stored outside this repository under `EpiLocate-private/manifests/`. They include distinct local and remote refs, all 27 registered worktrees, and ignored/untracked state indicators. The bundle was verified and all 41 actual branch refs were recovered in an independent bare repository. After PR review and merge, record the exact mainline SHA, audit every reachable object, create separate local and remote archive tags only for retired branch tips, and record each branch's final disposition. Do not push internal-history tags. If the public mainline needs rollback, revert the integration commit; do not rewrite `main` history.
