# EPI-NEXT actual CT-FM weights, synthetic CPU input — 2026-10-09

Status: **PASS for a single 32³ synthetic volume only**. Three real cases / G1, native DICOM geometry, trained clinical head, classification/localization metrics and GPU feasibility remain **NOT RUN**. RICORD pretraining overlap remains **unknown**.

## Evidence

Worktree `/Users/skyfrost/Documents/Techniques/EpiLocate-worktrees/epi-next-encoder`, branch `codex/epi-next-encoder-20261009`; pre-run HEAD `d7ae5e6d61d4ea1212f7fd1940f94e440ef53751`. Script SHA256 `2640adee2c190ea6be2c8b8263efdc1f8f0b6cf0e045732fd236dee54f8c4b6f` is bound into the output because this first and only actual model trial preceded its commit. The delivery SHA is recorded in the final handoff / Git history. No second model trial was run merely to change the recorded Git SHA.

| Measured item | Actual value |
|---|---|
| Official model revision | `527b0d1c262b433396c85ff2de84c427b26945a1` |
| Checkpoint | `model.safetensors`, 311,116,176 bytes |
| Official LFS and actual SHA256 | `b521ff13764ad0fce67f8ad2e5aa9ccc0823f69e4544b446581d8a2dee686215` |
| Input | `[1,1,32,32,32]`, deterministic normalized ramp, no patient data |
| Spatial output | `[1,512,2,2,2]` |
| GAP output | `[1,512]` |
| Loading | 0.147562 s, model construction + strict state load |
| Inference | 0.085596 s, one encoder call |
| Whole child process measured duration | 2.503342 s |
| Peak process RSS | 1,096,450,048 bytes, macOS `resource.RUSAGE_SELF.ru_maxrss` |
| GPU peak memory | null; no GPU used |
| Model parameters | 77,760,992; checkpoint also stores normalization buffers |
| Strict state validation | 161 tensors; zero missing/unexpected keys |
| Output finite range | -122.988686 to 181.507263 |
| Process exit code | 0; known child exited, no remaining task process |

Full raw 512 pooled values and feature/input/config hashes: `CTFM_CPU_SMOKE_v1.json`, SHA256 `533d9d52c8ff31b0cb582fed33319f8cf31f7e16dde55102169d314670ea4d97`. Captured stderr: `CTFM_CPU_SMOKE_v1.log`, only a Torch deprecation warning. Shape ratio does not establish spatial offsets, full-volume stitching or native-space localization correctness. Tiny synthetic throughput cannot be extrapolated to complete CT.

## Isolation and source review

Runtime: existing Python 3.11.15 / Torch 2.14.0, macOS arm64. Additional packages are under ignored `.local/ctfm-cpu/deps`: MONAI 1.5.1 and safetensors 0.5.3, installed from PyPI wheels with `--no-deps --no-index --target`. Wheels were downloaded from PyPI metadata URLs and SHA256 checked. Existing virtual environment, system packages, frozen runtime and formal checkpoints were not modified. Weight and dependencies remain local ignored assets and are not committed.

[The official lighter-zoo wrapper](https://github.com/project-lighter/lighter-zoo) was reviewed from its 0.1.3 PyPI wheel: `SegResEncoder` only inherits MONAI's encoder and a Hugging Face mixin, without adding neural layers. The reviewed MONAI 1.5.1 `segresnet_ds.py` SHA256 is `5b634c1f7077b12e1c87e3de2bf2bf4588341592c3e312b12cda13e955f3982f`. This trial directly constructs that MONAI class with the exact pinned [official model config](https://huggingface.co/project-lighter/ct_fm_feature_extractor/blob/527b0d1c262b433396c85ff2de84c427b26945a1/config.json), loads only safetensors with `strict=True`, freezes parameters/eval state, and uses the existing `FrozenEncoderAdapter` to extract last-stage features. No remote installation scripts, `trust_remote_code`, pickle or decoder execution.

**Interface distinction at the first trial:** the earlier `load_ctfm_local` imports lighter_zoo and at that point reported missing dependencies in the base environment. It had not been modified or validated by that first trial. This standalone direct-MONAI entry point has loaded real weights; the production/integration loader has not thereby passed. No real head was fitted.

## Download history and boundaries

First bounded request reached its 180 s cap at 181.169982 s: BLOCKED_DOWNLOAD, 225,443,840 bytes received, only 224,395,264 bytes written (last chunk rejected before write). One explicitly approved resume used HTTP 206, exact `Content-Range: bytes 224395264-311116175/311116176`, received 86,720,912 bytes in 69.774298 s under a 120 s cap, then verified the complete official LFS SHA. Original failure is retained in `CTFM_CPU_DOWNLOAD_AUDIT.json`. Total weight response bytes including the discarded chunk: 312,164,752, plus about 3.1 MB package wheels, under the 500 MB ceiling. No signed redirect URL, authentication value or patient information is included in public artifacts.

## Reproduction (already executed)

From this worktree, with the retained isolated dependencies/weight:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.local/ctfm-cpu/deps:research/next-hospital-20261014 /Users/skyfrost/Documents/Techniques/infectious-ct-ai/.venv/bin/python -m epi_next.encoder_ctfm_cpu_smoke --weights .local/ctfm-cpu/weights/model.safetensors --sha256 b521ff13764ad0fce67f8ad2e5aa9ccc0823f69e4544b446581d8a2dee686215 --output research/next-hospital-20261014/reports/CTFM_CPU_SMOKE_v1.json
```

The output exists and is intentionally not replaceable; use a new output path for an explicitly requested rerun. Parent supervises only its own child, CPU thread=1, 60 s whole-child wall limit, RSS polling threshold 3 GiB. All model computations use CPU. Original encoder modules were unchanged in the first trial. No real patient input or clinical-data upload, remote compute, paid resource, GPU/MPS job, deployment, push or merge.

## Final local adapter integration (subsequent code change)

After the direct-MONAI trial, the coordinator authorized removing the unnecessary lighter_zoo loader dependency. `load_ctfm_local` now constructs the exact reviewed `monai.networks.nets.segresnet_ds.SegResEncoder`, loads SHA-checked safetensors with strict keys, and returns `FrozenEncoderAdapter`. `ctfm_availability` explicitly reports this runtime path and checks only MONAI/safetensors. It does not fetch dependencies or weights. The base virtual environment remains untouched and requires the isolated dependency target on PYTHONPATH.

The revised entrypoint **actually called this local loader** and then `adapter.extract` once on the same 32³ synthetic input. This is a second, separately retained trial, necessary to validate the loader code change; it does not replace the initial record.

* 17 encoder tests PASS, 0.94 s, exit 0: `CTFM_CPU_ADAPTER_TESTS.log`.
* Adapter trial PASS, exit 0, process ended: `CTFM_CPU_ADAPTER_v2.json`; SHA256 `2f808d821861e20d1d3d796429204db9caeb13ab91a5768504238a1fb38f1a27`.
* Actual loader 0.333644 s; inference 0.078275 s; peak whole-child RSS 1,315,815,424 bytes. Input `[1,1,32,32,32]`, features `[1,512,2,2,2]`, GAP `[1,512]`.
* Feature bytes SHA256 `99357963e44ac8a7d9d8eb2d3c94faa33eadb160a41aa7655b7849e964a2223b`, exactly identical to the first direct-MONAI trial.
* Measured `parameters()` numel 77,760,992, floating `buffers()` numel 13,952, integer `buffers()` numel 26. The first two sum to the upstream safetensors F32 total 77,774,944; no parameter-count discrepancy remains.
* Revised `encoder.py` source SHA256 `fa990c17c3d3a781d401b1efd5ce7c4f0edd5ebec4e5e9150bc49caeeee8780c` bound in output. Pre-change HEAD `3300e1f3b084d6f962368b347fa7d0dafdaa6c92`; final implementation commit is in handoff/Git history.

The exact actual command is the one above with output `research/next-hospital-20261014/reports/CTFM_CPU_ADAPTER_v2.json`. Only the existing loader and this standalone smoke entrypoint changed; `encoder_smoke.py` was left unchanged for the integrator's independent output-guard fix. This proves the local adapter path for genuine weights plus synthetic input; production job integration, full CT, clinical head training, geometry and three-case G1 remain NOT RUN.
