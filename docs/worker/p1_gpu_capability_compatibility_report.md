# GPU Capability & Compatibility Report

Date: 2026-09-27. Audited baseline: `p0/integration` at `c9a5cc6373ffc889725971e3cae5bc09252790bd`. The audit preceded Worker code changes.

## Host and runtime

| Item | Observed result |
| --- | --- |
| Host | macOS Darwin arm64, Apple M5 Pro (20 GPU cores) |
| PyTorch in the frozen inference environment | `2.14.0` |
| `torch.version.cuda` | `None` |
| `torch.cuda.is_available()` / device count | `False` / `0` |
| NVIDIA tools | `nvidia-smi` and `nvcc` absent |
| MPS | Available, outside this CPU/CUDA/AUTO scope |
| NVIDIA driver and CUDA runtime compatibility | Cannot be checked on this host |

**Conclusion:** There is no usable NVIDIA GPU here. No CUDA numerical result, peak GPU memory measurement, GPU Worker E2E, or production GPU deployment can be claimed from this run.

## Frozen execution path

- `FrozenBaseline.__init__` initializes `self.device = torch.device("cpu")`. Its `load()` verifies the exact checkpoint, protocol, stage config, and baseline config hashes, loads the trusted checkpoint with `map_location="cpu"`, then calls `model.eval().to(self.device)`. The Worker can set this existing device field before `load()` without editing frozen model code or checkpoint bytes.
- `predict()` preprocesses the DICOM on CPU and passes the normalized tensor, model, and `self.device` to the existing `infer_logits()`. That function stacks batches, moves them to the chosen device, runs the model under `torch.inference_mode()`, moves logits back to CPU, and computes softmax there.
- `occlusion()` uses the same model and `infer_logits()` path for 16/32/64 px masks in batches of 32. Synthetic fixture position counts are 729/169/36, total 934.
- The Worker checks `MODEL_HASH` against frozen `MODEL_SHA`; `MODEL_VERSION` must equal that hash. `FrozenBaseline.load()` independently verifies the checkpoint SHA-256 and frozen metadata before model use.
- Before this phase, Worker registration always reported CPU because the frozen service defaulted to CPU. Explicit device selection and truthful registration can be implemented in the Worker adapter. Actual CUDA execution remains unverified until a suitable host is available.

## Deployment gate for a future NVIDIA host

Install a CUDA-enabled PyTorch build compatible with the host driver. Record GPU model, driver, `torch.__version__`, `torch.version.cuda`, `torch.cuda.is_available()`, and device properties. Then run the committed CPU/GPU benchmark and comparison gate against the same synthetic DICOM and checkpoint before GPU Worker E2E. Explicit `WORKER_DEVICE=CUDA` must fail startup when that gate cannot find a usable NVIDIA device.
