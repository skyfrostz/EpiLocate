# EPI-NEXT public source snapshot

This package contains the current DATA-EVAL, ENCODER, LOCALIZATION and INTEGRATION source selected on 2026-10-14. The [import record](../../docs/consolidation/EPI_NEXT_SOURCE_IMPORT_20261014.md) identifies the exact source commits, file selection, sanitization changes and verification scope. Internal commits were not merged into the public ancestry.

The source includes bounded import and HU diagnostics, geometry and weak-label contracts, CT-FM and R18 pipelines, localization and readout implementations, supervision and state tools, application adapters, and the 64-only candidate/acceptance drivers. Backend, frontend and Worker integration lives at the existing repository root paths. FrozenBaseline files and checkpoints were not changed.

## External bindings and exclusions

Images, native arrays, weights, databases, actual allowlists, saved results, execution/approval receipts, frozen release inventories, runtime captures, and private source histories are excluded. No execution authorization or active queue is delivered by this snapshot. Code that consumes those objects still requires exact hashes, valid authority and its existing admission/dispatch checks.

Site-specific paths now resolve from the public repository root. Historical private references resolve under ignored `.local/private-bindings/` or the original ignored task-local directories. The owner identity in source fixtures and guards is the neutral `project-owner` placeholder. Bound configuration templates are marked `public_template_only`; zero SHA values denote missing private bindings, including compiled legacy input/approval/Mask guard constants. Generic scientific contracts and R18/CT-FM mathematical settings retain their source values. Public source, runtime and request hashes must be rebound before any separately authorized real run; old private approvals do not authorize the published snapshot.

Historical private-fixture tests remain as source, but their public test collection marks the unavailable receipt/bundle-dependent modules as skipped. Generated cases are built afresh. DATA tests run in a separate process because their no-Torch and low-RSS checks are incompatible with collecting Torch-based tests into the same process. The latest R18 diagnostic, exact E2 invocation and browser-readiness regressions use production entry logic and generated inputs.

## Generated verification

Use Python 3.11 with the root project research dependencies and `backend_v2/requirements.txt`, plus `argon2-cffi` and `playwright`. Frontend dependencies use its existing lockfile. The public checks refuse private evidence and non-generated image/weight reads and block external network connections from the Python test process.

```sh
python research/next-hospital-20261014/run_public_checks.py --log-dir .local/public-checks
```

Optional `--browser` runs the generated DICOM regression in a local headless Chrome with an isolated loopback port. Optional `--frontend` runs the frontend unit suite and build. Browser binaries and installed dependencies must already be available; this command does not download models.

These checks establish only the stated source/engineering behavior. The [research status](../../docs/research/EPI_NEXT_STATUS_20261014.md) retains the poor fixed CT-FM validation result, incomplete R18 evaluation, localization limits and unfinished real display acceptance.
