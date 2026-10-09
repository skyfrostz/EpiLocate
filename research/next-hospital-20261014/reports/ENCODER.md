# EPI-NEXT ENCODER initial CPU delivery — 2026-10-09

Historical initial report: later genuine CT-FM CPU loading and local adapter validation are recorded in `CTFM_CPU_SMOKE.md` / `CTFM_CPU_ADAPTER_v2.json`; those later results supersede the initial MODEL_UNAVAILABLE state only in the isolated dependency environment. Real three-case/geometry/clinical gates remain NOT RUN.

Owner: ENCODER work line; project lead 钟佳桦. Branch `codex/epi-next-encoder-20261009`, worktree `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-encoder`. Base `169bb42b94365ae0eeccae10e425fa1e167f3ce1`; initially clean tracked/untracked/ignored state, no `.codegraph/`. Final commit is recorded by the handoff message / Git log; each numerical artifact records exact source SHA256 in addition to pre-commit HEAD.

## Actual state

| Item | Status | Evidence / blocking condition |
|---|---|---|
| Frozen adapter, case head, signed CAM | PASS | 17 CPU synthetic numerical tests |
| Hash-bound immutable feature cache | PASS | Content corruption, identity change, overwrite and sealed split tests |
| 3 fixed head seeds | PASS, SYNTHETIC ONLY | `encoder_cpu_smoke_v2.json`, raw logits and all 100 losses per seed |
| CT-FM dependency availability | MODEL_UNAVAILABLE | `monai`, `lighter_zoo`, `safetensors` absent; nothing installed |
| Official checkpoint loading | NOT RUN | No weights downloaded or local real checkpoint supplied |
| Three real cases / timing / GPU memory | NOT RUN | User: no GPU yet; approved three-case allowlist not supplied to this line |
| Real F0 / native geometry / lesion evaluation | NOT RUN | Real encoder and task/geometry/label gates not met |
| Pretraining RICORD overlap | unknown | SQL is insufficient to establish exact checkpoint training membership |

No real DICOM, private GT, sealed data, existing checkpoint or remote process was opened by this work line. No GPU/MPS kernels, cloud operations, package installation, push, merge, or deployment. No process started by this work line remains running after the finite foreground commands.

## Official source audit (public text only)

* [CT-FM repository](https://github.com/project-lighter/CT-FM/tree/f58c89a75ff0270ba6e339027e40bf04a221735d): pinned revision `f58c89a75ff0270ba6e339027e40bf04a221735d`, repository MIT license. Do not transfer this license assertion to the weights.
* [Feature extractor card](https://huggingface.co/project-lighter/ct_fm_feature_extractor/blob/527b0d1c262b433396c85ff2de84c427b26945a1/README.md): HF revision `527b0d1c262b433396c85ff2de84c427b26945a1`, Apache-2.0 tag, model metadata 77,774,944 F32 parameters. The card shows SPL orientation, HU clipping/scaling from [-1024,2048] to [0,1], foreground crop, last spatial encoder output and 512-dimensional GAP. These are upstream examples, not locally measured dimensions or runtime.
* [Pinned config](https://huggingface.co/project-lighter/ct_fm_feature_extractor/raw/527b0d1c262b433396c85ff2de84c427b26945a1/config.json): `blocks_down=[1,2,2,4,4]`, `in_channels=1`, `init_filters=32`, `spatial_dims=3`; SHA256 `9d2014ac1ff7d083b405d23e559e0559710a97f0b87ade74da886105eec6208a`.
* [Pinned training SQL](https://github.com/project-lighter/CT-FM/blob/f58c89a75ff0270ba6e339027e40bf04a221735d/notebooks/data-download/query.sql): SHA256 `281bd7b383e4b24c95dc559fb742c35434685f5171134180969a372dded5eb32`. It queries public CT in IDC v14 with thickness, position-count and localizer constraints; no explicit RICORD exclusion. The actual checkpoint membership was not examined; no claim of overlap or disjointness follows.
* [Pinned feature script](https://github.com/project-lighter/CT-FM/blob/f58c89a75ff0270ba6e339027e40bf04a221735d/scripts/feature_extractor.py): SHA256 `b838e9cee27b62c5fe48fd65fa38246c5e9409ced74c9cfc653b03e755451128`. Its example uses 3/1/1 spacing, unlike the card without explicit resampling. It also selects CUDA and uses pickle/local paths; no upstream script was executed. Project 2 mm / 96×160×160 remains an unvalidated resource-trial design.

## Implemented interface

`FrozenEncoderAdapter(module, output_index=-1).extract(volume, preserve_input_grad=False)` consumes N,C,D,H,W and emits N,F,d,h,w. All encoder parameters are frozen; `.train()` cannot update BN. `preserve_input_grad=True` supports mask differentiation. The default extracts without gradients. `actual_queries` counts attempted actual encoder calls.

`load_ctfm_local(path, expected_sha256)` accepts only a local exact-hash safetensors checkpoint. Missing file/dependencies or incompatible strict state keys fail closed. **Real loader compatibility is NOT RUN**. It does not install dependencies, fetch weights, execute external scripts, fix state key mismatches or use an untrained decoder.

`CaseLinearHead` is GAP → train-only channel standardization → linear logits. `class_contribution_map(features, head, target)` keeps signed contributions and the standardization offset; spatial mean plus class bias reproduces that class logit. No softmax heatmap, threshold or disease-probability interpretation is introduced.

`fit_patient_head(features, labels, patient_ids, splits, config, seed)` requires one vector per unique patient, explicitly rejects test/sealed/unknown split names, legacy validation/development aliases and synthetic training splits and invalid labels, fits mean/std only from train, and minimizes equal-patient CE in one full batch. A locked config uses AdamW lr 0.001, decay 0.0001, 100 epochs, seeds 17/29/43; fixed final epoch without validation selection. This deliberately bounded full-batch implementation differs from the pack's suggested mini-batch/early-stop design. Actual labels and target-definition authorization remain caller gates before real training. No clinical training occurred.

`FeatureCache` keys exact input, model, preprocessing, geometry, config, split-manifest SHA256, code commit and explicit train/observed_validation/synthetic split. It writes a flushed temporary NPZ then atomically links into an immutable key, verifies content SHA on read and disables pickle. This is a feature extraction cache, with no input-occlusion equivalence claim. Transform ledger construction, tiling, feature stride/offset and native coordinate mapping are not implemented here and must pass geometry QC before F0.

## Reproduction and actual evidence

Working directory: the worktree above. Runtime: `/Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python`, Python 3.11.15, Torch 2.14.0, macOS arm64, CPU. The system `python3` preflight failed with an Xcode license prompt; no license accepted or system settings modified; the existing virtual environment ran successfully.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/next-hospital-20261014 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m pytest research/next-hospital-20261014/tests/test_encoder.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=research/next-hospital-20261014 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m epi_next.encoder_smoke --output /tmp/EPI-NEXT-ENCODER-new-run.json
```

Use a new output path each run; output replacement is rejected. Actual smoke used `reports/encoder_cpu_smoke_v2.json`, exit 0, 0.420916333 seconds in-process. It ran one 1×1 Conv3D extraction on eight synthetic 4×5×6 volumes, trained three head seeds, and retained per-epoch losses/raw logits; it is not CT-FM or realistic performance evidence. Feature shape `[8,4,4,5,6]`. CAM/logit max errors `[7.301568984985352e-7, 2.0116567611694336e-7, 4.76837158203125e-7]`; cache roundtrip max error 0. GPU memory null, not zero measured GPU usage.

Artifact SHA256 `146f3f9c4aaa53672f698b2a0087e86d258b414cdf8bc6b5a5a43a1375fa604c`. Initial pre-hardening smoke `encoder_cpu_smoke.json` retained with SHA256 `9d51fe2449fb855f9b3d4282db3d2d0402a9f163f75c10d881653afcf3a613b9`; use v2 for final cache implementation evidence. Test run: 12 passed in 1.04s, exit 0. No metrics in these artifacts establish patient classification or lesion localization efficacy.

Committed-source rerun: `7a4ec0c7979d8eefe23e51cfaa7aa2209c138dd1`; identical command with output `reports/encoder_cpu_smoke_committed.json`, exit 0, artifact SHA256 `7a42ce4fe1c45f3cfb8420315220f5274ca2a5d5577368c07287cee706f779e3`. Runtime 0.568820374988718 seconds; numeric outputs unchanged. Final test log `encoder_tests.log`: 12 passed in 0.76s, exit 0.

Contract alignment: training accepts only `train` / `observed_validation`; cache accepts `train` / `observed_validation` / `synthetic`. Ambiguous `validation` and `development` aliases are rejected. Synthetic head test rows retain train/observed_validation split with separate SYNTHETIC_NUMERIC_ONLY provenance. Initial reports above predate this naming-only hardening. Full-batch fixed-epoch training is an explicit development design difference from suggested patient-batch=16 / early stopping; no performance claim or validation-based model selection has been made.
