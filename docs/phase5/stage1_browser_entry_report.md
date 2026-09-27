# P1 Phase 5 — Stage 1 browser entry record

## Baseline and changes

- Base: local `p0/integration` at `b069a8ce4fdeb33c7b33e2f5c3b109eb5724b6b5`.
- Development branch/worktree: `codex/p1-phase5-dual-mode-server-demo` in `/Users/skyfrost/Documents/Techniques/EpiLocate-p1-phase5-dual-mode-server-demo`.
- Backend v2 already owns users, expiring/revocable database-backed Bearer credentials, and per-object authorization. It has no password login or browser session route. Stage 1 adds a separate browser session gateway and does not alter Backend models, migrations, Worker protocol, FrozenBaseline, checkpoint, or CT Viewer.
- Each browser member has a distinct Gateway password hash and an existing Backend user token stored in an owner-only file. An opaque, revocable SQLite session maps the browser to that token on the server. Browser routes expose only user Case/Prediction/Job/Result APIs, not Worker APIs. Browser Authorization headers are ignored.
- Login, logout, eight-hour expiry, administrative revocation, account disable, Origin/CSRF checks, and account/IP login throttling are implemented. The Frontend has a login view, session restoration, CSRF for writes, logout, and expired-session redirect.

## Local checks

| Command | Result | Evidence boundary |
| --- | --- | --- |
| `PYTHONPATH=. .venv/bin/pytest -q session_gateway/tests backend_v2/tests` | 19 passed, 2 skipped | Gateway tests use both a synthetic Backend and the actual Backend v2 ASGI app for two-user Case/DICOM/Job/Result/Asset ownership. Backend real Worker tests skipped without environment variables. One existing Starlette/httpx warning. |
| `PYTHONPATH=. /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m pytest -q tests/test_worker` | 29 passed | Worker regression; no actual CPU inference in this command. |
| `cd frontend && npm test` | 35 passed | Includes login, CSRF, logout and existing CT/Result component tests; existing jsdom `scrollTo` notice. |
| `cd frontend && npm run build` | Passed | Existing Cornerstone codec externalization and large-chunk warnings. |
| `git diff --check` | Passed | Tracked diff whitespace check. |

No real CPU inference, full browser E2E, PostgreSQL/MinIO production-like test, GPU execution, ECS audit, or server deployment was performed in this stage. The local synthetic Backend used by gateway tests is not a `LIVE_CASE` inference claim. Existing Phase 4.5 local CPU evidence remains at the base commit; it is not a Stage 1 rerun.

## Next gate

After project-owner confirmation, Stage 2 can package the existing Worker with `WORKER_DEVICE=CPU` and measure server-feasible resources locally. Stage 3 must exercise the gateway over an HTTPS browser origin together with the real Backend, Worker, PostgreSQL, MinIO, CT Viewer and two accounts before any ECS access. The ECS and domain remain untouched.
