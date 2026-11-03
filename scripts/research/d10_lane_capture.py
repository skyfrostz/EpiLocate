#!/usr/bin/env python3
"""Read-only D10 synthetic capture: default baseline precedes any flag isolation.

The supplied implementation is hash-checked before importing it. No manifest,
split, GT, training, or model download entry point is called. Each process writes
to a new evidence directory; failed attempts are retained there too.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
import traceback
from pathlib import Path

BASE_SHA = "ebf6e8260b775e67857c3bd83a213fe0fecac8ff"
INPUT_SHA = "8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee"
MODEL_SHA = "548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734"
DATA_CHECKS_SHA = "cf03e2dd3f19cc0dbfe271d0d0d3512ad07b2be2a706644be6d74e07ab29fc90"
SEED = 20260925
MODES = ("baseline", "tf32-off", "deterministic-on", "benchmark-off", "amp-off", "research")
LAYERS = ["input", "conv1", *[f"layer{i}.{j}" for i in range(1, 5) for j in range(2)],
          "avgpool", "fc", "logits", "probability"]


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    Path(path).chmod(0o600)


def array_metadata(value, np):
    value = np.asarray(value)
    if not value.flags.c_contiguous:
        value = np.ascontiguousarray(value)
    header = json.dumps({"dtype": str(value.dtype), "shape": list(value.shape)}, sort_keys=True).encode()
    return {"dtype": str(value.dtype), "shape": list(value.shape),
            "sha256": hashlib.sha256(header + b"\n" + value.tobytes(order="C")).hexdigest()}


def flags(torch):
    def autocast(device):
        try:
            return bool(torch.is_autocast_enabled(device))
        except TypeError:
            return bool(torch.is_autocast_cpu_enabled() if device == "cpu" else torch.is_autocast_enabled())
    return {"cuda_matmul_allow_tf32": bool(torch.backends.cuda.matmul.allow_tf32),
            "cudnn_allow_tf32": bool(torch.backends.cudnn.allow_tf32),
            "cudnn_benchmark": bool(torch.backends.cudnn.benchmark),
            "cudnn_deterministic": bool(torch.backends.cudnn.deterministic),
            "torch_deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
            "float32_matmul_precision": torch.get_float32_matmul_precision(),
            "autocast_cpu": autocast("cpu"), "autocast_cuda": autocast("cuda"),
            "amp_used_by_tool": False, "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG")}


def apply_mode(mode, torch, np):
    # Single-factor runs deliberately preserve every unrelated default.
    if mode == "tf32-off":
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
    elif mode == "deterministic-on":
        torch.use_deterministic_algorithms(True)
    elif mode == "benchmark-off":
        torch.backends.cudnn.benchmark = False
    elif mode == "research":
        random.seed(SEED)
        np.random.seed(SEED)
        torch.manual_seed(SEED)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(SEED)
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.set_float32_matmul_precision("highest")
    # baseline does not set seeds, flags, thread counts, or workspace settings.
    # amp-off uses explicit autocast(enabled=False), retaining float32 math.


def environment(torch, torchvision, np, pydicom, device):
    gpu, capability, driver = None, None, None
    node_identity = platform.node().encode()
    boot_id = Path("/proc/sys/kernel/random/boot_id")
    if boot_id.is_file():
        node_identity += b"\0" + boot_id.read_bytes().strip()
    if torch.cuda.is_available():
        gpu = torch.cuda.get_device_name(0)
        capability = list(torch.cuda.get_device_capability(0))
        gpu_identity = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=driver_version,uuid", "--format=csv,noheader"], text=True).splitlines()
        if len(gpu_identity) != 1:
            raise ValueError("single-GPU node required; explicit device mapping needed before using multiple GPUs")
        driver, gpu_uuid = [v.strip() for v in gpu_identity[0].split(",", 1)]
        node_identity += b"\0" + gpu_uuid.encode()
    packages = {}
    for name in ("torch", "torchvision", "numpy", "pandas", "Pillow", "scipy", "pydicom", "PyYAML", "httpx", "pylibjpeg", "pylibjpeg-libjpeg"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"os": platform.platform(), "python": platform.python_version(),
            "torch": str(torch.__version__), "torchvision": torchvision.__version__,
            "numpy": np.__version__, "pydicom": pydicom.__version__,
            "cuda_runtime": torch.version.cuda, "cudnn_version": torch.backends.cudnn.version(),
            "gpu_model": gpu, "gpu_compute_capability": capability, "driver": driver,
            "cpu_model": platform.processor() or platform.machine(), "device": device,
            "node_fingerprint": hashlib.sha256(node_identity).hexdigest(),
            "input_dtype": "torch.float32", "model_dtype": "torch.float32",
            "precision_flags": flags(torch), "packages": packages,
            "torch_num_threads": torch.get_num_threads(), "torch_num_interop_threads": torch.get_num_interop_threads(),
            "torch_build_config": torch.__config__.show()}


def state_identity(model, torch, np):
    digest, names = hashlib.sha256(), []
    for name, tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous().numpy()
        item = array_metadata(value, np)
        names.append(name)
        digest.update(name.encode() + b"\0" + item["dtype"].encode() + b"\0")
        digest.update(json.dumps(item["shape"]).encode() + b"\0")
        digest.update(value.tobytes(order="C"))
    return {"architecture": type(model).__name__, "parameter_count": sum(p.numel() for p in model.parameters()),
            "state_dict_key_count": len(names), "state_dict_keys_sha256": hashlib.sha256("\n".join(names).encode()).hexdigest(),
            "state_dict_values_sha256": digest.hexdigest(), "eval": all(not m.training for m in model.modules()),
            "batchnorm_training_count": sum(isinstance(m, torch.nn.modules.batchnorm._BatchNorm) and m.training for m in model.modules()),
            "dropout_training_count": sum(isinstance(m, torch.nn.modules.dropout._DropoutNd) and m.training for m in model.modules()),
            "dtype": str(next(model.parameters()).dtype)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementation-root", required=True, type=Path)
    parser.add_argument("--frozen-root", required=True, type=Path)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--reference-manifest", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--lane", required=True, choices=("A", "B", "C"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=MODES, default="baseline")
    parser.add_argument("--baseline-manifest", type=Path)
    parser.add_argument("--factor-manifest", action="append", type=Path, default=[])
    args = parser.parse_args()
    args.out_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    args.out_dir.chmod(0o700)
    attempt = {"schema": "D10_ATTEMPT_V1", "base_sha": BASE_SHA, "lane": args.lane,
               "run_id": args.run_id, "mode": args.mode, "status": "STARTED",
               "audit_script_sha256": file_hash(Path(__file__)), "stage_b": "NOT_AUTHORIZED"}
    args.evidence_context = {}
    write_new(args.out_dir / "attempt.json", attempt)
    try:
        capture(args, parser)
    except Exception as exc:
        write_new(args.out_dir / "failure.json", {**attempt, **args.evidence_context, "status": "FAILED", "error_type": type(exc).__name__,
                                                   "error": str(exc), "traceback": traceback.format_exc()})
        raise


def capture(args, parser):
    reference = json.loads(args.reference_manifest.read_text())
    if reference["fixture"]["sha256"] != INPUT_SHA or reference["checkpoint_sha256"] != MODEL_SHA:
        raise ValueError("manifest does not identify the approved synthetic/checkpoint")
    if file_hash(args.fixture) != reference["fixture"]["sha256"]:
        raise ValueError("fixture does not match frozen synthetic input SHA")
    for name, expected in reference["implementation_sha256"].items():
        if file_hash(args.implementation_root / name) != expected:
            raise ValueError(f"frozen implementation differs: {name}")
    if file_hash(args.implementation_root / "src/data_checks.py") != DATA_CHECKS_SHA:
        raise ValueError("use the same Phase5 data_checks helper in all three lanes")
    config_paths = {"stage": "configs/occlusion_instability_v1.yaml", "protocol": "docs/occlusion_instability_protocol_v1.md",
                    "baseline": "configs/formal_baseline_rule_b_v1.yaml"}
    for name, relative in config_paths.items():
        if file_hash(args.frozen_root / relative) != reference["frozen_config_sha256"][name]:
            raise ValueError(f"frozen config differs: {name}")
    checkpoint = args.frozen_root / "outputs/experiments/FORMAL-BL-R18-V1/training/best_model.pth"
    if file_hash(checkpoint) != reference["checkpoint_sha256"]:
        raise ValueError("checkpoint differs from frozen SHA")
    baseline_manifest = None
    if args.mode != "baseline":
        if not args.baseline_manifest:
            raise ValueError("capture default baseline before any factor adjustment")
        baseline_manifest = json.loads(args.baseline_manifest.read_text())
        args.evidence_context["baseline_capture_sha256"] = file_hash(args.baseline_manifest)
        if baseline_manifest["mode"] != "baseline" or baseline_manifest["lane"] != args.lane:
            raise ValueError("factor baseline must be this lane's unadjusted capture")
        if args.mode == "research":
            factors = [json.loads(p.read_text()) for p in args.factor_manifest]
            if {p["mode"] for p in factors} != {"tf32-off", "deterministic-on", "benchmark-off", "amp-off"}:
                raise ValueError("research combination requires all four single-factor attempts")
            for p in factors:
                if p["lane"] != args.lane or p["baseline_capture_sha256"] != file_hash(args.baseline_manifest):
                    raise ValueError("research factor evidence is from a different lane/baseline")
                if p.get("status") == "FAILED" and (
                    "effective_precision_flags" not in p or
                    p.get("environment_before_adjustment") != baseline_manifest["environment"]):
                    raise ValueError("failed factor evidence must record an actual same-environment adjusted attempt")
    if args.mode == "research":
        # This is a disclosed combined configuration, never a one-factor claim.
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    sys.path.insert(0, str(args.implementation_root.resolve()))
    import numpy as np
    import pydicom
    import torch
    import torchvision
    from algorithm.service import FrozenBaseline
    from scripts.occlusion_runner import build_grid, infer_logits, mask_resized

    device = "CUDA" if args.lane == "C" else "CPU"
    before = environment(torch, torchvision, np, pydicom, device)
    args.evidence_context.update(environment_before_adjustment=before,
                                 input_sha256=reference["fixture"]["sha256"], checkpoint_sha256=reference["checkpoint_sha256"])
    write_new(args.out_dir / "runtime_preflight.json", args.evidence_context)
    if args.lane in ("B", "C"):
        if platform.system() != "Linux":
            raise ValueError("B/C require the same Linux GPU node")
        if before["gpu_model"] not in ("NVIDIA GeForce RTX 3090", "GeForce RTX 3090"):
            raise ValueError(f"STOP: RTX 3090 required; available GPU is {before['gpu_model']}")
        if before["torch"] != "2.4.0+cu121" or before["cuda_runtime"] != "12.1":
            raise ValueError("historical compatibility lanes require PyTorch 2.4.0+cu121 / CUDA 12.1")
    elif platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("Lane A requires the frozen Mac ARM reference host")
    if before["precision_flags"]["autocast_cpu"] or before["precision_flags"]["autocast_cuda"]:
        raise ValueError("ambient autocast enabled; baseline needs a fresh process")
    if baseline_manifest:
        # Compare host/runtime before applying a factor, ignoring its device label.
        expected = dict(baseline_manifest["environment"])
        observed = dict(before)
        if args.mode == "research":
            expected["precision_flags"] = {**expected["precision_flags"], "cublas_workspace_config": ":4096:8"}
        if observed != expected:
            raise ValueError("factor run environment differs from default baseline before adjustment")
        if baseline_manifest["input_sha256"] != reference["fixture"]["sha256"] or baseline_manifest["checkpoint_sha256"] != reference["checkpoint_sha256"]:
            raise ValueError("baseline input/checkpoint identity differs")
    apply_mode(args.mode, torch, np)
    args.evidence_context["effective_precision_flags"] = flags(torch)
    baseline = FrozenBaseline(args.frozen_root)
    baseline.device = torch.device("cuda" if device == "CUDA" else "cpu")
    model = baseline.load()
    identity = state_identity(model, torch, np)
    identity["checkpoint_sha256"] = reference["checkpoint_sha256"]
    expected_identity = json.loads((args.reference_manifest.parent / "d10_model_identity.json").read_text())["cpu"]
    if not identity["eval"] or identity["dtype"] != "torch.float32":
        raise ValueError("model must be float32 and entirely in eval mode")
    for key in ("parameter_count", "state_dict_key_count", "state_dict_keys_sha256", "state_dict_values_sha256"):
        if identity[key] != expected_identity[key]:
            raise ValueError(f"runtime model identity mismatch: {key}")
    stages = baseline.stages(args.fixture)
    if stages.tensor.dtype != torch.float32 or stages.tensor.device.type != "cpu":
        raise ValueError("preprocessing must produce the frozen CPU float32 tensor")
    sources = {name: file_hash(args.implementation_root / name) for name in (
        "algorithm/service.py", "scripts/occlusion_runner.py", "src/model.py", "src/preprocessing.py", "src/data_checks.py")}
    tensors = {}

    def save(key, value):
        if isinstance(value, torch.Tensor):
            value = value.detach().cpu().contiguous().numpy()
        value = np.ascontiguousarray(value)
        if not np.isfinite(value).all():
            raise ValueError(f"non-finite output: {key}")
        relative = f"tensors/{key}.npy"
        path = args.out_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            np.save(stream, value, allow_pickle=False)
        path.chmod(0o600)
        tensors[key] = {"file": relative, **array_metadata(value, np), "file_sha256": file_hash(path)}

    for stage in ("raw", "hu", "windowed", "normalized", "resized", "tensor"):
        save(f"preprocessing/{stage}", getattr(stages, stage))
    args.evidence_context["preprocessing_tensors"] = dict(tensors)
    if tensors["preprocessing/tensor"]["sha256"] != reference["preprocessing_cpu"]["tensor"]["sha256"]:
        args.evidence_context["root_cause_candidate"] = "INPUT_PREPROCESSING_MISMATCH"
        raise ValueError("model input differs from frozen Mac reference; STOP before forward and compare saved preprocessing tensors")

    def amp_context():
        if args.mode in ("amp-off", "research"):
            return torch.autocast(device_type=baseline.device.type, enabled=False)
        return contextlib.nullcontext()

    def trace(sample, inputs, row=0):
        batch = torch.stack(inputs).to(baseline.device)
        save(sample + "/input", batch[row])
        handles = []
        def hook(name):
            def observe(_module, _inputs, output):
                # Clone immediately: a following in-place ReLU may mutate conv1.
                save(sample + "/" + name, output[row].detach().clone())
            return observe
        for name, module in model.named_modules():
            if name in LAYERS[1:-2]:
                handles.append(module.register_forward_hook(hook(name)))
        try:
            with torch.inference_mode(), amp_context():
                logits = model(batch).detach().cpu()
                # Frozen infer_logits extracts logits then computes softmax on CPU.
                probability = torch.softmax(logits, dim=1)
            save(sample + "/logits", logits[row])
            save(sample + "/probability", probability[row])
        finally:
            for handle in handles:
                handle.remove()

    grids = {scale: build_grid(224, scale, scale // 2) for scale in (16, 32, 64)}
    if {str(k): len(v) for k, v in grids.items()} != {"16": 729, "32": 169, "64": 36}:
        raise ValueError("frozen grid count mismatch")
    x, y = grids[16][691]
    if (x, y) != (128, 200):
        raise ValueError("position 691 frozen coordinate mismatch")
    positions, chunks = [], []
    for scale, start, end in ((16, 672, 704), (32, 0, 32), (64, 32, 36)):
        group = []
        for index in range(start, end):
            px, py = grids[scale][index]
            positions.append({"index": index, "scale": scale, "x": px, "y": py})
            group.append(mask_resized(stages.resized, px, py, scale, 0.5))
        chunks.append(group)
    masked = chunks[0][19]
    trace("baseline", [stages.tensor])
    trace("position_691_batch1", [masked])
    trace("position_691_batch32", chunks[0], 19)
    all_masked = [t for group in chunks for t in group]
    save("small_reference/masked_tensors", torch.stack(all_masked))
    with amp_context():
        logits1, probs1 = infer_logits(model, all_masked, baseline.device, 1)
        formal = [infer_logits(model, group, baseline.device, 32) for group in chunks]
        save("small_reference/logits_batch1", logits1)
        save("small_reference/probabilities_batch1", probs1)
        save("small_reference/logits_formal", np.concatenate([p[0] for p in formal]))
        save("small_reference/probabilities_formal", np.concatenate([p[1] for p in formal]))
        for label, group, batchsize, row in (("baseline", [stages.tensor], 1, 0),
                                             ("position_691_batch1", [masked], 1, 0),
                                             ("position_691_formal", chunks[0], 32, 19)):
            repeated = [infer_logits(model, group, baseline.device, batchsize)[1][row] for _ in range(3)]
            save("repeatability/" + label, np.stack(repeated))
    after = environment(torch, torchvision, np, pydicom, device)
    metadata = {"schema": "D10_LANE_CAPTURE_V1", "base_sha": BASE_SHA, "lane": args.lane, "run_id": args.run_id,
                "mode": args.mode, "device": device, "input_sha256": file_hash(args.fixture),
                "checkpoint_sha256": file_hash(checkpoint), "config_sha256": reference["frozen_config_sha256"],
                "source_sha256": sources, "model_identity": identity, "environment": after,
                "environment_before_adjustment": before, "layer_order": LAYERS, "tensors": tensors,
                "small_reference_positions": positions, "position_691": {"index": 691, "scale": 16, "x": x, "y": y},
                "grid_counts": {str(k): len(v) for k, v in grids.items()}, "formal_batch_size": 32,
                "mask_fill": 0.5, "probability_computation_device": "CPU (frozen infer_logits behavior)",
                "audit_script_sha256": file_hash(Path(__file__)), "frozen_tolerance": 0.0001,
                "baseline_capture_sha256": file_hash(args.baseline_manifest) if baseline_manifest else None,
                "factor_capture_sha256": [file_hash(p) for p in args.factor_manifest],
                "factor_attempt_status": [{"mode": json.loads(p.read_text())["mode"],
                                            "status": json.loads(p.read_text())["status"]} for p in args.factor_manifest],
                "seed": SEED if args.mode == "research" else None,
                "stage_b": "NOT_AUTHORIZED", "status": "CAPTURED_NOT_D10_PASS"}
    write_new(args.out_dir / "capture.json", metadata)
    print(json.dumps({"lane": args.lane, "run_id": args.run_id, "mode": args.mode, "status": metadata["status"],
                      "tensor_count": len(tensors), "small_positions": len(positions),
                      "capture_sha256": file_hash(args.out_dir / "capture.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
