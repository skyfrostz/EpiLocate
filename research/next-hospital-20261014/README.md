# EPI-NEXT hospital preparation — local research implementation

This directory is an opt-in research package. It does not change the deployed
Worker, Backend, frontend, historical checkpoints, A/B/C, GT-v1, or frozen splits.
New code is integrated only in `codex/epi-next-integration-20261009`, not `main`.

The actual 2026-10-09 findings and task states are in [PREFLIGHT.md](reports/PREFLIGHT.md).
Read [DATA_EVAL.md](reports/DATA_EVAL.md), [ENCODER.md](reports/ENCODER.md), and
[LOCALIZATION.md](reports/LOCALIZATION.md) for exact implementation differences.

## One command

From this worktree root, with a Python environment containing the existing
PyTorch/torchvision, NumPy, SciPy and pytest dependencies:

```sh
python research/next-hospital-20261014/run_cpu_checks.py --output research/next-hospital-20261014/.local/my-new-run
```

The command executes all unit tests, environment inspection, independent metric
fixtures, the synthetic encoder/head/CAM/cache experiment, and E1/E2/F1-variant
numerical fixtures serially on CPU. It refuses an existing output directory and
saves commands, exit codes, logs, environment and artifact hashes in `receipt.json`.
The interpreter actually used in this delivery is recorded in the delivery receipt.

To additionally test E1/E2 with the verified existing checkpoint on a **generated
synthetic image**, append `--checkpoint /approved/local/checkpoint.pth
--checkpoint-sha 548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734`.
No patient data are loaded by either mode. Supply the actual verified local path,
not a historical path copied from a report. No dependency installation occurs.

For the separately isolated actual CT-FM CPU check, also supply `--ctfm-weights`,
`--ctfm-sha` and `--ctfm-deps`. The latter points to the isolated MONAI/safetensors
directory; it is used only for that job. The actual command and paths are in the
local delivery receipt. This mode tests one synthetic 32-cubed input, not three
patient CT volumes. See [CTFM_CPU_SMOKE.md](reports/CTFM_CPU_SMOKE.md).

## Modules and evidence

| Module | Implemented behavior | Current evidence limit |
| --- | --- | --- |
| `contracts.py` | VolumeRecord, PredictionResult, RunManifest; explicit coordinates, evidence and failure states | Schema validation; approved membership must come from a separately reviewed manifest |
| `artifacts.py` | Immutable local receipts, content hashes, local writer lock, conflict/unknown-state reconciliation | Not a remote receiver or distributed GPU queue; power-loss recovery has not been field tested |
| `baseline_bridge.py` | Hash-verified tensor-only ResNet-18 loading and normalized-array adapter | Real frozen weight + synthetic input only; not the D10 runtime gate |
| `localization.py` | E1 fixed target margin; static-coarse F1 input perturbation variant | E1 uses a disjoint grid, not historical overlapping windows; this static variant does not refresh baseline/map |
| `residual_localization.py` | F1 residual-input baselines and coarse-map refresh; every refresh and probe counted | Injected interaction-model tests only; real CT-FM/geometry adapter not yet connected |
| `hspi.py` | Differentiable continuous mask, full-logit consistency, hierarchical exclusion, CPF, PSMI | Independent projected-Adam variant; not author-code reproduction; no wall-clock interruption |
| `encoder.py` | Frozen/eval encoder adapter, patient-equal head, signed CAM, immutable feature cache | Actual CT-FM loader and one synthetic input tested; real patient feature extraction/head not run |
| `geometry.py` | Regular stack ordering, DICOM row/column spacing, LPS affine and inverse | Synthetic geometry only; rejects tilt/nonuniform spacing; not a volume resampler or native overlay pipeline |
| `data_eval.py` | Common-domain budgets, partial-reference limits, patient denominators and AUROC/AP | Synthetic fixtures only; no measured lesion improvement |

E1 uses a fixed class target. E2 preserves all logits and therefore has no
target argument: changing it to a target margin would be a separate variant.
Raw probability response, logit-margin response, optimized masks and signed CAM
remain distinct evidence. No output is a clinical disease probability.

The frozen encoder head currently uses CPU full-batch fixed epochs, at most the
three declared seeds. It does not implement the suggested patient batch of 16
and early stopping. That difference is explicit in the encoder report; real
training is disabled until task semantics and an approved dataset are locked.

## Safety and integration gates

Application default remains historical/read-only. Research CLI explicitly opts
into new code; no production model registry or UI flags were changed. Before any
real-data runner is added, bind patient and series membership to a reviewed,
hash-locked nonsealed manifest, record preprocessing transforms and verify native
overlays. A caller-supplied `train` string is not an authorization mechanism.

The static F1 variant is retained separately from the later residual-input F1
module. The latter re-evaluates remaining input and refreshes its coarse map;
its diagnostic probes do not remove regions from later candidate eligibility.
Both modules are research implementations, not validated lesion detectors.

Current F1 timeout is checked between synchronous forwards; a running forward
can exceed 120 seconds. The prototype counts attempted calls including failures,
reserves seeded probes and keeps partial responses, but has no remote cancellation.
Feature extraction caching is not used to accelerate input occlusion; equivalence
to full recomputation has not been established for such a shortcut.

Full-case CT-FM feasibility, GT-vNext overlays, patient classification/localization
comparison, hospital freeze, three repeated E2E acceptances and deployment remain
NOT RUN. See [HOSPITAL_EVALUATION.md](HOSPITAL_EVALUATION.md) for the workflow to
apply after institutional and data approvals.
