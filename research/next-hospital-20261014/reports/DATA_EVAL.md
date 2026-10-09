# EPI-NEXT DATA-EVAL — 2026-10-09

Status: synthetic implementation **PASS**; real-patient GT-vNext and localization validation **NOT RUN**.

## Provenance and scope

Branch `codex/epi-next-data-eval-20261009`; worktree `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-data-eval`. Starting HEAD `169bb42b94365ae0eeccae10e425fa1e167f3ce1`; initial tracked, untracked, and ignored state empty. Source commit is the introducing commit, recoverable with `git log --diff-filter=A -1 --format=%H -- research/next-hospital-20261014/epi_next/data_eval.py`. Owner: DATA-EVAL Codex; project lead: 钟佳桦.

Read repository AGENTS, project context, source map, project skill, documentation guide, and execution-pack 00/01/02. No local CodeGraph index. Read-only historical Dataset documentation at branch `research/ricord-ground-truth-v1`, actual HEAD `4fbf83c221aae98075689b3cc3eb2883d01cabc4`. No changes to that worktree, frozen GT-v1, A/B/C, or the cohort.

## Actual data findings

- Recomputed frozen allocation from actual `patient_assignments.csv`: 186 patients, train 130, observed val 28, test 28. File SHA-256 `6159532c4621f96ae09038af0ed850bca08cab7187040056c8f7cdf5183f08b0`; matches GT source anchor. Read for membership metadata audit only; no patient IDs or test records emitted.
- Nonsealed allocation has 80 RICORD-1A patients carrying label 1 and 78 RICORD-1B patients carrying label 0. This establishes an exact collection/label relationship in the manifest. It does not independently verify clinical adjudication or absence of imaging abnormality. Clinical CSV/XLSX contents were not re-audited in this task; new target definition remains a pretraining gate.
- Actual development primary manifest bytes SHA-256 `1189e87d609cef39e9e363d77af975be04e00747ff9e11f8d5b412c3afaddb7f`, matching frozen hash; recomputed 61 train patients, 65 series, 811 distinct SOP, 811 records with technical QA `PASS`, all 811 `CLINICAL_VALIDITY_NOT_ADJUDICATED`.
- Historical `RICORD_GT_V1_FINAL_FREEZE.md` confirms later formal GT-v1 freeze. The development manifest's retained `DEVELOPMENT_GT_FREEZE_CANDIDATE` string describes its generation time, not the latest governance state. Single-polygon inclusion, local annotation completeness unknown, and no whole-lung negative inference remain binding.
- Both existing RICORD-1A and RICORD-1B raw roots exist. No recursive patient traversal, real pixel decode, sealed GT access, or mask inspection occurred. Private UID-bearing paths are excluded from this report.
- CT-FM actual pretraining membership comparison: `unknown`; **NOT RUN**. No actual checkpoint training manifest was evaluated. No disjointness claim.

## Implemented and executed

`epi_next/data_eval.py` implements a common support intersection, explicit reliability-mask candidate budget caps at 5/10/20% (or a caller-specified fraction), deterministic flat-index ties, observed-reference coverage, and complete-reference metrics gated independently by annotation completeness and clinical semantic agreement. Budgeting never creates reliable candidates or fills a target quota. Non-finite supported scores fail closed. GT outside support is explicitly counted; predictions outside support are rejected.

Patient summaries require unique patient IDs, retain failed/abstaining/partial cases in the expected denominator, and label conditional reference coverage explicitly. Binary AUROC and stepwise average precision use threshold-group ties, reject duplicate patient records, retain missing predictions and unknown labels, and return null for empty/single-class evaluation. Slices must first be aggregated within patient by a locked protocol.

`epi_next/geometry.py` uses `(slice,row,column)` array coordinates and DICOM LPS millimetres, correctly separates PixelSpacing row/column semantics, sorts by IPP projection on the IOP normal, measures spacing independently of SliceThickness, and validates affine round trips. It rejects duplicate/nonuniform positions, inconsistent orientations/spacings, and gantry tilt. Regular gaps cannot establish missing-slice absence without an independent SOP inventory; single-slice 3D spacing is unsupported. No model resampling, real DICOM ingestion, annotation rasterization, or real overlay is claimed.

Environment: macOS 27.0.1 arm64; Python 3.11.15, numpy 2.4.6, pytest 8.4.2. Local CPU, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`; no GPU, model weights, remote jobs, or clinical data used. Input is embedded synthetic arrays, no data split or model SHA applicable to the experiment.

Executed from the worktree root:

```sh
PYTHONPATH=research/next-hospital-20261014 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m pytest -q research/next-hospital-20261014/tests/test_data_eval.py research/next-hospital-20261014/tests/test_geometry.py
PYTHONPATH=research/next-hospital-20261014 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m epi_next.data_eval --synthetic
```

Both exit codes **0**. **28 tests passed**, covering ties, empty support/reference/candidates, incomplete GT, failed denominators, single-class classification, duplicate IDs, NaN, oblique/sagittal/coronal/axial coordinates, crop/resample transform composition, and unsupported geometry.

Machine-readable numerical artifact: `reports/data_eval_synthetic.json`, SHA-256 `dd176b6e2b0ac60da5415098f90c0b7610716cd3c4a5a5434895083bdc80ef3f`. 100-voxel common domain; budget 5/10/20 voxels yields actual 5/8/8 candidates; observed four-voxel synthetic reference coverage 1.0 at each budget. Complete-reference metrics remain null because annotation completeness is not asserted. Synthetic classification has expected n=3, evaluable n=2, one missing score, AUROC/AP=1.0. These are constructed numerical checks, not model performance.

Test log: `reports/data_eval_tests.txt`, SHA-256 `1146ae11f460190ee18d635f51b2646559f501ddc3aa51826ce99fac19ffc70b`.

## Remaining gates

| Task | State | Reason |
|---|---|---|
| Frozen split aggregate and development manifest hash audit | PASS | Actual metadata checked |
| Independent metrics and synthetic geometry QA | PASS | 28 CPU tests |
| Locked nonsealed allowlist and target definition | BLOCKED | Coordinator must bind explicit membership and task semantics before real-data work |
| GT-vNext multipolygon mapping, completeness audit, native overlay | NOT RUN | No real pixels or annotation bodies processed this run |
| CT-FM pretraining membership overlap | NOT RUN | Actual training membership unavailable in this task; status unknown |
| Real patient localization comparison | NOT RUN | No new model outputs or GT-vNext prepared |
| Clinical accuracy or unseen-data generalization | NOT RUN | No supporting evaluation |

No tasks launched by this workline remain running; every CPU subprocess completed synchronously. Unrelated processes were neither inspected in detail nor stopped. No push, merge, deployment, GPU rental, or paid computation.
