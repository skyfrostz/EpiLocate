# EPI-NEXT four-line public source candidate — 2026-10-14

## Source selection

This candidate extends public commit `693bebfc9ef091f970ce78aee5bae8b8bd20a036` by file content. It imports 315 source, test, contract and configuration files from the four existing local worktrees. Their internal commits and private history are not ancestors of this candidate. The [per-file inventory](EPI_NEXT_SOURCE_FILES_20261014.json) records source and published SHA256 values, ownership and publication changes; it contains source provenance only, with no execution receipts or asset locators.

| Source line | Branch | Source HEAD |
| --- | --- | --- |
| DATA-EVAL | `codex/epi-next-data-eval-20261009` | `c9d751cf823ca9462741bc04f129512045d50818` |
| ENCODER | `codex/epi-next-encoder-20261009` | `73ede0797016c022968ef239c8101df2da1d91f5` |
| LOCALIZATION | `codex/epi-next-localization-20261009` | `11ac87b91ea863a0f394aa53a9e3db6571691bc6` |
| INTEGRATION | `codex/epi-next-integration-20261009` | `246cdd1884a59bf9c0dcb1f872a26802378488de` |

The DATA snapshot also includes the current uncommitted `ri_receipt_index_v1.py` change and the new `ri_metadata_supplement_v1.py` and its test. Each is separately hash-bound in the inventory. The modified DATA execution report is excluded. Other worktrees' tracked sources were clean at selection; their private/untracked execution artifacts were excluded.

Five differing shared paths were resolved by source ownership: ENCODER supplies `encoder_smoke.py`; LOCALIZATION supplies `hspi.py`, `localization.py`, `localization_smoke.py` and `test_hspi.py`. The other shared source copies were byte-identical at selection. INTEGRATION supplies Backend, Frontend, Worker, `epilocate_next`, QA and shared control/runtime tooling.

## Publication changes and exclusions

- Personal absolute paths become repository-relative references or ignored private-binding paths. The specific owner name becomes `project-owner` in guards and generated fixtures. Direct imaging-archive download access is replaced with an `example.invalid` placeholder.
- Private configuration bindings become explicitly marked public templates. Missing private digests use zero placeholders in both templates and compiled legacy binding guards; permission booleans are disabled. Public model identities and source checksums are retained. Generic mathematical contracts retain their source values. No threshold, loss, split, sampling rule, HU transformation, interpolation rule or frozen model implementation was relaxed.
- Two synthetic smoke entry points now refuse an existing output before doing any work. Two old generated-data fixtures are regenerated locally instead of reading excluded historical receipts. A coordinate test uses explicit synthetic translation values. The browser regression chooses an unused loopback port and the installed Node executable.
- The source-specific metadata verifier under the private final-request report folder and the observed-runtime JSON are excluded. All image/array/weight files, databases, object stores, reports, actual approvals/dispatches/receipts, release inventories, logs, build outputs and private Git histories are excluded. `.gitignore` protects the private research and release directories.

The public source has different binding hashes from the internal execution objects. It needs new exact source/runtime/input binding before any separately authorized real run. Source publication consumes no scientific approval, queue admission, slot or dispatch.

## Verification

Python 3.11, CPU threads 1, isolated dependency directory; no research weights or real images were read. A verification IO guard refused private evidence, non-generated medical assets and external Python network connections. Generated local queues are test fixtures, separate from the existing scientific queue.

| Check | Actual result |
| --- | --- |
| DATA generated suite, isolated from Torch collection | 470 passed |
| Strict encoder bootstrap seam, separate process | 1 passed |
| Remaining research/generated suite | 457 passed, 109 skipped |
| Backend/Gateway, Worker protocol and selected QA | 167 passed, 31 skipped |
| Production viewer/probe with generated DICOM | 1 passed; decode/render, hidden hint, absent/wrong/cleared asset, old render generation and decode-failure cases |
| Frontend unit tests and standard build | 167 tests passed; build passed |
| Isolated 64-only candidate with generated policy/identifiers | Build passed; no real SOP or service was used |

Skipped tests require excluded historical private bindings/bundles or unavailable production-like services. They are explicitly marked; no real clinical or scientific execution is substituted for them. The first combined research invocation failed because it collected Torch before low-RSS/no-Torch DATA tests and because historical fixtures were absent. After process isolation and fresh generated fixtures, the stated groups passed. Initial failed engineering checks remain in ignored local logs.

The repository includes `run_public_checks.py` to reproduce these process-separated groups. Existing bundle-size and test serializer warnings remain. The real three-SOP technical recheck, human spatial review, hospital audience permission and final rehearsals were not performed by this publication task.

## Security and evidence limits

The complete candidate Git closure is scanned after its final commit. New payload objects are distinguished from public `main` ancestry. The original publicly reachable S3 locator file remains absent from the tip but present in old public history, as previously documented in [mainline provenance](MAINLINE_INTEGRATION_20261007.md). This import does not rewrite that history or describe it as locator-free.

This is a source/engineering candidate. CT-FM's observed validation AUROC remains 0.45; R18 has no fixed classification evaluation, and no new E2-R scientific readout or localization improvement follows from these tests. See [research status](../research/EPI_NEXT_STATUS_20261014.md).
