# EPI-NEXT execution record — 2026-10-09

Project lead: 钟佳桦. Timezone: Asia/Shanghai. This is a local development
milestone, not the October 14 hospital release acceptance.

## Verified starting state

Repository `/Users/skyfrost/Documents/Techniques/infectious-ct-ai`, branch `main`,
HEAD `169bb42b94365ae0eeccae10e425fa1e167f3ce1`. No tracked changes at start; six
top-level untracked entries included design images/HTML, flow-fluidity and paper
outputs. Ignored contents included virtual environments, DICOM/data directories,
research results and deliverables. They were preserved. No `.codegraph/` directory
was found, so normal file searches were used without creating an index.

Existing local Canvas processes 78775/78776/78777 were observed and left alone.
No remote SSH, instance status, billing status or remote job state was inspected.
Historical D10/Stage B authorization is not current GPU authorization. The user
explicitly chose **no GPU execution for this round**.

Mac ARM64, 24 GiB physical memory; Python 3.11.15 in the existing project venv,
PyTorch 2.14.0, NumPy 2.4.6. CUDA unavailable; MPS available but unused. System
`python3` exited 69 because the Xcode license had not been accepted. No license
was accepted and no system installation was changed. Existing project Python
was used. The guessed Homebrew Python path did not exist (exit 127); it was not
installed. All successful commands record the actual interpreter path.

## Inputs read and audited

- Execution ZIP found; SHA-256
  `8b1e3bd3d5d05a5c80fee71b9b72c3e6f04313d201951fb7a86cbff5c69647a8`.
  All nine entries in PACKAGE_SHA256 matched. Read common contract and full plan,
  role instructions, configuration template and sources. Attached documents are
  reference material; the user's instruction defines authorization.
- Both supplied HSPI and XProtoNet PDF files were found and text extracted.
  Localization reviewed HSPI equations and rendered its CPF/PSMI page. No author
  source was found in the audited repository; no universal absence claim is made.
- The separately named `EpiLocate_Execution_Plan_v1_2026-10-09.md` was not found
  at repository root or Downloads top level. ZIP `01_EXECUTION_PLAN.md` was read;
  it is not silently represented as that separate file.
- Root AGENTS, README, project context, canonical source map, research status,
  engineering logs, documentation guide, baseline configs, model source, algorithm
  contract and Worker API lifecycle contract were read. Historical reports remain
  dated snapshots and do not prove current deployment.
- Frozen allocation verified from actual manifest: 186 patients = 130 train +
  28 observed validation + 28 test. SHA
  `6159532c4621f96ae09038af0ed850bca08cab7187040056c8f7cdf5183f08b0`.
  No test image/annotation or patient-level test output was accessed.
- Development GT bytes match frozen hash
  `1189e87d609cef39e9e363d77af975be04e00747ff9e11f8d5b412c3afaddb7f`:
  61 train patients / 811 SOP / 65 series. Technical QA PASS, clinical meaning
  unadjudicated. No polygon does not mean negative; these are not independent
  clinical test cases. Native real-image overlay was not executed.
- Nonsealed label/collection audit: 80 RICORD-1A cases carry label 1, 78 RICORD-1B
  cases label 0. Clinical source tables require further bounded verification;
  no new infection classification target or clinical training is enabled.
- Old baseline path in the algorithm worktree is absent. The archive index
  resolves the actual file; live hashing verified 134,262,661 bytes and SHA
  `548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`.
  File loaded with `weights_only=True`, CPU, no changes or redistribution.
- CT-FM official code/model metadata verified by ENCODER. Later in the same run,
  official weights were downloaded to isolated local storage and actual CPU
  adapter loading passed. See the supplement below. Full-case memory/timing,
  stride/offset spatial correctness and three-case feasibility remain NOT RUN.
  Pretraining overlap is `unknown`.

Exact private input roots, manifest/checkpoint paths and live hashes are saved
in ignored `.local/preflight_paths.json`; SHA
`b8d4ccabaa20353da046c96de0fa0adc39905872de88d354df5979114f1c6d2b`.
No individual UID, patient row, clinical pixel, credential or weight is committed.

## Actual work lines

Four new worktrees were created from the starting main SHA and added to the
private worktree registry; no old worktree was moved, cleaned or reset.

| Role | Branch | Worktree suffix | Imported source |
| --- | --- | --- | --- |
| DATA-EVAL | `codex/epi-next-data-eval-20261009` | `epi-next-data-eval` | `5098da53eb4a5458ba5f6e3a1acf49b1c1eec215` |
| ENCODER | `codex/epi-next-encoder-20261009` | `epi-next-encoder` | `d7ae5e6d61d4ea1212f7fd1940f94e440ef53751` |
| LOCALIZATION | `codex/epi-next-localization-20261009` | `epi-next-localization` | `d2877ba1ffd3e5355c1ed8af087b46bf78d22114` |
| INTEGRATION | `codex/epi-next-integration-20261009` | `epi-next-integration` | current branch; final delivery receipt records exact commit |

All suffixes are below `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/`.
Residual F1 v2 subsequently imported from `0f02daf2ad49323d6a9bdadb7994f338a6230c61`;
its tested source was `268b98843545c5f272cdac37cf16a04b46da98ad`.
Actual CT-FM adapter follow-up imported from `f769ac9d6a326039a40d08620b6abf9c8235095f`.
Three child agents did bounded work; the parent owned integration. Imported only
owned module/test/report files and reviewed cross-module contracts; no branch
merge, mainline update, push or deployment occurred.

## Milestone evidence

First integrated suite: **115 tests passed**, exit 0. Single-command suite ran
tests, doctor, data metrics, synthetic encoder, localization and real-weight
synthetic E1/E2; all six process exit codes 0. Logs and commands are retained at
`.local/verification-integration-v1/receipt.json`.

Real checkpoint synthetic numerics: 5 calls; repeated logits max difference 0;
16/32/64 pixel fixed-target margin drops 0.453484811 / 0.587559011 / 1.057429209.
Original logits and probability changes are in `.local/runs/`.

Actual E1/E2 execution on the same real checkpoint and generated input: 25 total
calls, 0.493363 seconds observed in the first integrated run, E1 `OK`, E2
`NO_FEASIBLE_MASK`. CPF limits were not relaxed. This is executability evidence;
no lesion comparison, clinical classification or full E1/E2 experiment occurred.
Public synthetic numbers: `BASELINE_E1_E2_SYNTHETIC_INITIAL.json`, SHA
`79091fb2c0d0802d52dc77d3447f2ce934917e89e6a35d1bba01dae4c5e622f2`.

Independent review identified and fixed map-level expert-evidence impersonation,
failure serialization requiring invented logits, recomputation before receipt
reconciliation, malformed receipt type handling and missing explicit membership
binding. These fixes have focused regression tests. Local filesystem behavior
does not establish remote receiver recovery or distributed queue correctness.

## Task table to October 14

PASS below applies only to the stated scope. Dates are targets, not completion
claims; blocked items do not authorize substitution of synthetic evidence.

| Target date | Task | State | Evidence or remaining dependency |
| --- | --- | --- | --- |
| Oct 9 | Read-only preflight / four isolated work lines | PASS | Current Git, local process and input audits above |
| Oct 9–10 | Unified research contracts / immutable local assets | PASS | CPU contract/recovery tests; no production adapter |
| Oct 10 | E1 fixed-target numeric implementation | PASS | Unit fixtures and real-weight synthetic run |
| Oct 10 | CT-FM official weight / CPU synthetic loading | PASS | Exact SHA, strict adapter load, output 1×512×2×2×2; full-case performance unknown |
| Oct 10 | Real CT-FM three-case feasibility | BLOCKED | User deferred GPU; no approved three-case allowlist or native volume pipeline |
| Oct 10 | GT-vNext multipolygon/native overlay | BLOCKED | Scope/allowlist and annotation completeness must be locked; no real pixels processed |
| Oct 11 | E2 SPI/CPF/PSMI independent variant | PASS | Synthetic tests; real-weight short smoke returns NO_FEASIBLE_MASK |
| Oct 11 | Patient head / signed CAM / extraction cache plumbing | PASS | Three-seed synthetic head only; CT-FM F0 NOT RUN |
| Oct 11 | Real patient target definition / F0 training | BLOCKED | Clinical task source verification and CT-FM gate |
| Oct 11–12 | Residual-input F1 logic | PASS | 17 module tests and 7 interaction-model checks; real CT-FM connection NOT RUN |
| Oct 12 | Real E1/E2 and F0/F1 controlled comparisons | NOT RUN | Native GT, locked patients/labels, outputs and common support required |
| Oct 13 | Select and freeze hospital algorithm | NOT RUN | Requires actual localization evidence; stability alone insufficient |
| Oct 14 | Three repeat E2E checks / native overlay / cached demo | NOT RUN | No application deployment or hospital-ready claim |
| Oct 15–17 | Doctor annotation and evaluation workflow | READY | Draft checklist exists; institutional approval and execution remain pending |

No paid GPU, remote training, clinical upload, protected research modification or
sealed-data access is requested as part of this completed local milestone. Those
operations require separate explicit authorization. Current implementation work
continues without them. Later real-case work needs an exact approved nonsealed
allowlist, task definition and resource scope; elapsed time is not approval.

## CT-FM and residual F1 follow-up

The official 311,116,176-byte safetensors file was verified against LFS SHA
`b521ff13764ad0fce67f8ad2e5aa9ccc0823f69e4544b446581d8a2dee686215`.
Initial download reached its 180-second cap; one checked HTTP 206 byte-range
resume completed it. Both outcomes remain in `CTFM_CPU_DOWNLOAD_AUDIT.json`.
Isolated MONAI 1.5.1 and safetensors 0.5.3 were added locally without altering the
existing venv, system or frozen runtime. No GPU or remote computation occurred.

The shared `load_ctfm_local → FrozenEncoderAdapter.extract` path actually loaded
the checkpoint strictly and ran `[1,1,32,32,32] → [1,512,2,2,2]`, GAP `[1,512]`.
That adapter trial measured loading 0.33364 s, inference 0.07827 s and whole-child
peak RSS 1,315,815,424 bytes. GPU peak memory remains null. Parameters 77,760,992;
floating buffers 13,952; integer buffers 26. These measured counts explain the
model card's 77,774,944 floating values without conflating parameters/buffers.
Small-input throughput and shape ratio do not establish full-case feasibility
or a correct native-space feature transform.

Residual F1 now refreshes baseline and coarse map after accepted-region removal.
Interaction fixture baselines 6→5→2, selected centers A→C→B, responses 1/3/2,
8 total / 7 extra calls including 2 probes and 2 refreshes. Diagnostic probes
remain eligible for later formal candidate search; a regression verifies a sole
signal at a probe location is retained. Target-support loss stops explicitly.

A later combined run retained one failing test: the new no-overwrite test
expected FileExistsError, while the residual CLI correctly refused with argparse
exit 2. The assertion now accepts and verifies both refusal mechanisms. Its
original failure log remains in `.local/verification-residual-v2/`; final suite
results are recorded separately in the delivery receipt, not backfilled here.
