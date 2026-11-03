#!/usr/bin/env python3
"""Run the unchanged, complete synthetic Worker benchmark with verified inputs.

The benchmark runs once per invocation; its cold/warm passes each contain the
frozen 934 occlusion positions. This wrapper never grants D10 PASS and never
opens a research split, GT manifest, or arbitrary medical image.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

EXECUTION_AUDIT_BASE_SHA = "767d595658aed284181b8548c960aa9f8dbec60c"
FROZEN_REFERENCE_LINEAGE_SHA = "ebf6e8260b775e67857c3bd83a213fe0fecac8ff"
INPUT_SHA256 = "8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee"
CHECKPOINT_SHA256 = "548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734"
CONFIG_SHA256 = {
    "baseline": "7c456065fbff126d25417ad4580c8f8ac58a2b80f5e8fde1356bd6d92a021e17",
    "protocol": "204e34ae2474ab91076cbe3d2fb8ba5ad6f5affb631274c3feed57ed2da7160b",
    "stage": "6a9d1b011250e59956f443add621e786e04ceb6716a8329bc08df1e1e12f2b8a",
}
IMPLEMENTATION_SHA256 = {
    "algorithm/__init__.py": "b25c1ac2f0a84495ab9680dfca0b7b640479298be8ff0b5c9ff940e85bc22663",
    "algorithm/service.py": "b1edafeb3985cc79d7b171c7f89d43ab8c958b178c36f7cd7c2767b8992e8291",
    "worker/__init__.py": "30ca0c871fb0b6413c49456dd85bdb27847b7c8a6a6267425e3ce3910d846a9a",
    "worker/device.py": "17301b77fbc230c6c015fd4cd77b56802829e342e83020c5753fc33804af532f",
    "worker/inference.py": "b1bf2564c9b4698ba61ab52efa592614cd6035deac081d70da9e9807ade86421",
    "worker/consistency.py": "77cdde654fc03f6e5ff748f1c533ded6c103e6a46a2707075317fb03461920ec",
    "worker/benchmark.py": "930cbde503a4de6ee8f697de60291d69a9713a8614a559887643aeab206a8748",
    "scripts/occlusion_runner.py": "fb1e7aea1a41beea4afc2f26b2415d6999517cae9443fb139c742ea72da472a9",
    "src/model.py": "c4bc616c5f59271ca471126ae93e26648cabb1bc2b8cf71bf894fdd4490c2b24",
    "src/preprocessing.py": "b4630fd86e0628ab49683368fbaddfcfa2a80717feadf5c8e967ff2d6fa7d41c",
    "src/data_checks.py": "cf03e2dd3f19cc0dbfe271d0d0d3512ad07b2be2a706644be6d74e07ab29fc90",
    "docs/interfaces/fixtures/p0_synthetic_ct.dcm": INPUT_SHA256,
}
EXPECTED_FILE_SHA256 = {"implementation/" + name: value for name, value in IMPLEMENTATION_SHA256.items()}
EXPECTED_FILE_SHA256.update({
    "frozen/outputs/experiments/FORMAL-BL-R18-V1/training/best_model.pth": CHECKPOINT_SHA256,
    "frozen/docs/occlusion_instability_protocol_v1.md": CONFIG_SHA256["protocol"],
    "frozen/configs/occlusion_instability_v1.yaml": CONFIG_SHA256["stage"],
    "frozen/configs/formal_baseline_rule_b_v1.yaml": CONFIG_SHA256["baseline"],
    "reference/d10_reference_manifest.json": "1f4492006f46a117c42cd3cc5fe03ec6fafb16e7d6b7f8b79bd95a80b4adecf6",
    "reference/d10_model_identity.json": "43705dec298f0b4b6b28047cfa57d8278adfc4ff9bf66ea139c1d6b4ed0a4758",
    "requirements-gpu-worker.txt": "cbaa118e64e07a709e13cb6e77f446f31814a108b6daf0f6b995e149a6a3930a",
})
AUDIT_FILES = frozenset(("audit/d10_lane_capture.py", "audit/d10_three_way_compare.py", "audit/d10_prepare_package.py"))
ALLOWED_FILES = frozenset(EXPECTED_FILE_SHA256) | AUDIT_FILES
RESEARCH_SEED = 20260925
RESEARCH_FLAGS = {
    "cuda_matmul_allow_tf32": False, "cudnn_allow_tf32": False, "cudnn_benchmark": False,
    "cudnn_deterministic": True, "torch_deterministic_algorithms": True,
    "float32_matmul_precision": "highest", "autocast_cpu": False, "autocast_cuda": False,
    "amp_used_by_tool": False, "cublas_workspace_config": ":4096:8",
}
GPU_MODELS = frozenset(("NVIDIA GeForce RTX 3090", "GeForce RTX 3090"))
IMPORTED_IMPLEMENTATION = {
    "worker.benchmark": "worker/benchmark.py", "worker.device": "worker/device.py",
    "worker.inference": "worker/inference.py", "worker.consistency": "worker/consistency.py",
    "algorithm.service": "algorithm/service.py", "src.model": "src/model.py",
    "src.preprocessing": "src/preprocessing.py", "src.data_checks": "src/data_checks.py",
    "scripts.occlusion_runner": "scripts/occlusion_runner.py",
}


class RetestValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RetestValidationError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RetestValidationError(f"cannot read JSON evidence {path.name}: {error}") from error
    require(isinstance(value, dict), f"{path.name}: JSON object required")
    return value


def write_new(path: Path, value: dict[str, Any]) -> None:
    serialized = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(serialized)


def verify_package(package_root: str | Path) -> dict[str, Any]:
    """Verify the 22 allowlisted files and pinned frozen code before any imports."""
    root = Path(package_root).resolve()
    manifest_path = root / "package_manifest.json"
    require(manifest_path.is_file() and not manifest_path.is_symlink(), "regular package_manifest.json required")
    manifest = read_json(manifest_path)
    require(manifest.get("schema") == "D10_EXECUTION_PACKAGE_V1", "unsupported execution package schema")
    require(manifest.get("base_sha") == FROZEN_REFERENCE_LINEAGE_SHA, "package frozen-reference lineage differs")
    require(manifest.get("stage_b") == "NOT_AUTHORIZED", "package must not authorize Stage B")
    files = manifest.get("allowed_files")
    require(isinstance(files, dict) and set(files) == ALLOWED_FILES, "package must contain exactly the approved 22 allowlisted files")
    actual_hashes = {}
    for relative, metadata in files.items():
        require(isinstance(metadata, dict), f"invalid package metadata: {relative}")
        path = root / relative
        require(path.is_file() and not any((root.joinpath(*Path(relative).parts[:i])).is_symlink()
                                         for i in range(1, len(Path(relative).parts) + 1)), f"regular package file required: {relative}")
        require(path.resolve().is_relative_to(root), f"package path escapes root: {relative}")
        require(type(metadata.get("bytes")) is int and metadata["bytes"] == path.stat().st_size, f"package size mismatch: {relative}")
        digest = sha256(path)
        require(valid_sha256(metadata.get("sha256")) and digest == metadata["sha256"], f"package SHA mismatch: {relative}")
        if relative in EXPECTED_FILE_SHA256:
            require(digest == EXPECTED_FILE_SHA256[relative], f"pinned frozen/source/reference SHA mismatch: {relative}")
        actual_hashes[relative] = digest
    reference = read_json(root / "reference/d10_reference_manifest.json")
    require(reference.get("schema") == "D10_REFERENCE_V1", "unsupported frozen reference schema")
    require(reference.get("fixture", {}).get("sha256") == INPUT_SHA256, "reference must identify the fixed synthetic input")
    require(reference.get("checkpoint_sha256") == CHECKPOINT_SHA256, "reference checkpoint SHA differs")
    require(reference.get("frozen_config_sha256") == CONFIG_SHA256, "reference frozen configuration SHA differs")
    source = reference.get("implementation_sha256")
    require(isinstance(source, dict) and bool(source), "frozen implementation hash map required")
    for relative, digest in source.items():
        require(relative in IMPLEMENTATION_SHA256 and digest == IMPLEMENTATION_SHA256[relative], "reference implementation math SHA differs")
    return {"root": root, "manifest_sha256": sha256(manifest_path), "file_sha256": actual_hashes,
            "manifest": manifest, "reference": reference}


def verify_formal_manifest(path: Path | None, package: dict[str, Any], required: bool) -> dict[str, Any] | None:
    require(path is not None or not required, "formal runtime manifest is required for this invocation")
    if path is None:
        return None
    require(path.is_file() and not path.is_symlink(), "regular formal runtime manifest required")
    manifest = read_json(path)
    require(manifest.get("schema") == "FORMAL_CUDA_RESEARCH_RUNTIME_V1", "unsupported formal runtime schema")
    require(manifest.get("torch") == "2.4.0+cu121" and manifest.get("cuda_runtime") == "12.1",
            "formal runtime must declare PyTorch 2.4.0+cu121 / CUDA 12.1")
    require(type(manifest.get("seed")) is int and manifest["seed"] == RESEARCH_SEED, "formal runtime seed differs")
    require(manifest.get("precision_flags") == RESEARCH_FLAGS, "formal runtime flags must exactly declare reviewed research settings")
    if "source_package_manifest_sha256" in manifest:
        require(manifest["source_package_manifest_sha256"] == package["manifest_sha256"], "formal runtime references a different source package")
    if "gpu_model" in manifest:
        require(manifest["gpu_model"] in GPU_MODELS, "formal runtime must use the approved RTX 3090")
    return {"manifest": manifest, "sha256": sha256(path)}


def precision_flags(torch) -> dict[str, Any]:
    def autocast(device: str) -> bool:
        try:
            return bool(torch.is_autocast_enabled(device))
        except TypeError:
            return bool(torch.is_autocast_cpu_enabled() if device == "cpu" else torch.is_autocast_enabled())
    return {
        "cuda_matmul_allow_tf32": bool(torch.backends.cuda.matmul.allow_tf32),
        "cudnn_allow_tf32": bool(torch.backends.cudnn.allow_tf32),
        "cudnn_benchmark": bool(torch.backends.cudnn.benchmark),
        "cudnn_deterministic": bool(torch.backends.cudnn.deterministic),
        "torch_deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
        "float32_matmul_precision": torch.get_float32_matmul_precision(),
        "autocast_cpu": autocast("cpu"), "autocast_cuda": autocast("cuda"),
        "amp_used_by_tool": False, "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
    }


def runtime_environment(torch, device: str) -> dict[str, Any]:
    gpu, capability, driver = None, None, None
    node_identity = platform.node().encode()
    boot = Path("/proc/sys/kernel/random/boot_id")
    if boot.is_file():
        node_identity += b"\0" + boot.read_bytes().strip()
    if torch.cuda.is_available():
        require(torch.cuda.device_count() == 1, "single-GPU node required; hardware mapping must be explicit")
        gpu = torch.cuda.get_device_name(0)
        capability = list(torch.cuda.get_device_capability(0))
        lines = subprocess.check_output(["nvidia-smi", "--query-gpu=driver_version,uuid", "--format=csv,noheader"], text=True).splitlines()
        require(len(lines) == 1, "single-GPU driver/identity record required")
        driver, identifier = [value.strip() for value in lines[0].split(",", 1)]
        node_identity += b"\0" + identifier.encode()
    packages = {}
    for name in ("torch", "torchvision", "numpy", "pydicom", "pandas", "Pillow", "scipy", "PyYAML", "httpx", "pylibjpeg", "pylibjpeg-libjpeg"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "os": platform.platform(), "python": platform.python_version(), "torch": str(torch.__version__),
        "torchvision": packages["torchvision"], "numpy": packages["numpy"], "pydicom": packages["pydicom"],
        "cuda_runtime": torch.version.cuda, "cudnn_version": torch.backends.cudnn.version(), "driver": driver,
        "gpu_model": gpu, "gpu_compute_capability": capability, "cpu_model": platform.processor() or platform.machine(),
        "node_fingerprint": hashlib.sha256(node_identity).hexdigest(), "device": device, "packages": packages,
        "precision_flags": precision_flags(torch), "torch_num_threads": torch.get_num_threads(),
        "torch_num_interop_threads": torch.get_num_interop_threads(), "torch_build_config": torch.__config__.show(),
    }


def validate_runtime(actual: dict[str, Any], formal: dict[str, Any] | None, device: str) -> None:
    if device == "CUDA":
        require(actual["os"].startswith("Linux"), "CUDA audit requires the provisioned Linux node")
        require(actual["torch"] == "2.4.0+cu121" and actual["cuda_runtime"] == "12.1", "CUDA audit requires PyTorch 2.4.0+cu121 / CUDA 12.1")
        require(actual["gpu_model"] in GPU_MODELS, "CUDA requested without the approved RTX 3090; fallback is forbidden")
        require(actual["driver"] is not None and actual["cudnn_version"] is not None, "actual CUDA driver/cuDNN must be recorded")
    if formal is None:
        return
    declared = formal["manifest"]
    for name, value in declared.items():
        if name in actual:
            require(actual[name] == value, f"actual formal runtime differs at {name}")
    require(actual["precision_flags"] == RESEARCH_FLAGS, "effective formal runtime flags differ from declaration")


def _import_torch():
    return importlib.import_module("torch")


def _apply_formal(torch) -> None:
    import numpy as np
    random.seed(RESEARCH_SEED)
    np.random.seed(RESEARCH_SEED)
    torch.manual_seed(RESEARCH_SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(RESEARCH_SEED)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.set_float32_matmul_precision("highest")


def _import_benchmark(implementation: Path):
    sys.path.insert(0, str(implementation))
    module = importlib.import_module("worker.benchmark")
    require(Path(module.__file__).resolve() == implementation / "worker/benchmark.py", "benchmark imported from outside the verified package")
    return module


def verify_loaded_sources(implementation: Path, *, require_all: bool = False) -> None:
    for name, relative in IMPORTED_IMPLEMENTATION.items():
        module = sys.modules.get(name)
        if module is None:
            require(not require_all, f"benchmark did not load expected frozen module {name}")
        else:
            require(Path(getattr(module, "__file__", "")).resolve() == implementation / relative,
                    f"frozen module imported outside verified package: {name}")


def validate_results(benchmark: dict[str, Any], bundle: dict[str, Any], device: str, actual: dict[str, Any]) -> None:
    require(benchmark.get("requested_device") == device and benchmark.get("actual_device") == device and bundle.get("device") == device,
            "benchmark execution device differs from request; fallback is forbidden")
    for output in (benchmark, bundle):
        require(output.get("input_sha256") == INPUT_SHA256 and output.get("model_hash") == CHECKPOINT_SHA256,
                "benchmark/bundle fixed input or checkpoint identity differs")
    require(benchmark.get("torch_version") == actual["torch"] and benchmark.get("torch_cuda_runtime") == actual["cuda_runtime"],
            "benchmark runtime differs from recorded actual environment")
    require(benchmark.get("position_count_by_scale") == {"16": 729, "32": 169, "64": 36}, "full frozen grid counts differ")
    positions = bundle.get("result", {}).get("positions")
    require(isinstance(positions, list) and len(positions) == 934, "full frozen bundle must contain all 934 positions")
    expected = []
    for scale in (16, 32, 64):
        stride = scale // 2
        for y in range(0, 224 - scale + 1, stride):
            for x in range(0, 224 - scale + 1, stride):
                expected.append((scale, x, y))
    require([(item.get("block_size"), item.get("x"), item.get("y")) for item in positions] == expected,
            "full frozen bundle position coordinates/order differ")


def run_retest(package_root: Path, device: str, out_dir: Path,
               formal_runtime_manifest: Path | None = None, require_formal_runtime_manifest: bool = False) -> dict[str, Any]:
    require(device in ("CPU", "CUDA"), "device must be CPU or CUDA; AUTO fallback is not allowed")
    require(not out_dir.exists(), "output directory already exists; preserve prior evidence")
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    out_dir.chmod(0o700)
    provenance = {
        "schema": "D10_FULL_FROZEN_RETEST_RUNTIME_V1", "device": device,
        "execution_audit_base_sha": EXECUTION_AUDIT_BASE_SHA, "frozen_reference_lineage_sha": FROZEN_REFERENCE_LINEAGE_SHA,
        "wrapper_sha256": sha256(Path(__file__)), "d10_pass_asserted": False,
        "stage_b_training": "NOT_AUTHORIZED", "status": "STARTED",
    }
    phase = "PACKAGE_VERIFICATION"
    try:
        package = verify_package(package_root)
        provenance.update(source_package_manifest_sha256=package["manifest_sha256"], verified_package_file_sha256=package["file_sha256"])
        phase = "FORMAL_RUNTIME_MANIFEST_VERIFICATION"
        formal = verify_formal_manifest(formal_runtime_manifest, package, require_formal_runtime_manifest)
        provenance.update(mode="FORMAL_RESEARCH_RUNTIME" if formal else "UNADJUSTED_DIAGNOSTIC_BASELINE",
                          formal_runtime_manifest_sha256=formal["sha256"] if formal else None,
                          declared_formal_runtime=formal["manifest"] if formal else None)
        phase = "BEFORE_TORCH_IMPORT"
        require("torch" not in sys.modules, "use a fresh process: torch was imported before package/runtime preflight")
        if formal:
            os.environ["CUBLAS_WORKSPACE_CONFIG"] = formal["manifest"]["precision_flags"]["cublas_workspace_config"]
        sys.dont_write_bytecode = True
        torch = _import_torch()
        provenance["environment_before_adjustment"] = runtime_environment(torch, device)
        phase = "RUNTIME_CONFIGURATION"
        if formal:
            _apply_formal(torch)
        context = torch.autocast(device_type=device.lower(), enabled=False) if formal else contextlib.nullcontext()
        implementation = package["root"] / "implementation"
        with context:
            actual = runtime_environment(torch, device)
            provenance["actual_environment_before_benchmark"] = actual
            validate_runtime(actual, formal, device)
            phase = "FROZEN_BENCHMARK_IMPORT"
            module = _import_benchmark(implementation)
            verify_loaded_sources(implementation)
            phase = "FULL_FROZEN_BENCHMARK"
            benchmark, bundle = module.run_benchmark(package["root"] / "frozen",
                                                   implementation / "docs/interfaces/fixtures/p0_synthetic_ct.dcm", device)
            provenance["actual_environment_after_benchmark"] = runtime_environment(torch, device)
        # Retain returned raw outputs even when their validation fails.
        phase = "RESULT_PRESERVATION"
        write_new(out_dir / "benchmark.json", benchmark)
        write_new(out_dir / "bundle.json", bundle)
        provenance.update(benchmark_sha256=sha256(out_dir / "benchmark.json"), bundle_sha256=sha256(out_dir / "bundle.json"))
        phase = "RESULT_VALIDATION"
        require(provenance["actual_environment_after_benchmark"] == actual, "runtime changed during frozen benchmark")
        validate_results(benchmark, bundle, device, actual)
        verify_loaded_sources(implementation, require_all=True)
        provenance.update(status="CAPTURED_FULL_FROZEN_REFERENCE_NOT_D10_PASS", frozen_position_count=934,
                          benchmark_invocation_count=1, occlusion_passes_per_invocation=2,
                          inference_scope="One unchanged benchmark invocation; its cold/warm occlusion passes each contain 934 positions.")
        write_new(out_dir / "runtime_manifest.json", provenance)
        return provenance
    except Exception as error:
        failure = {**provenance, "status": "FAILED", "failed_phase": phase,
                   "error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc()}
        write_new(out_dir / "failure.json", failure)
        raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--device", choices=("CPU", "CUDA"), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--formal-runtime-manifest", type=Path)
    parser.add_argument("--require-formal-runtime-manifest", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_retest(args.package_root, args.device, args.out_dir, args.formal_runtime_manifest,
                            args.require_formal_runtime_manifest)
    except Exception as error:
        parser.exit(1, f"D10 frozen retest failed: {type(error).__name__}: {error}\n")
    print(json.dumps({"status": result["status"], "actual_device": args.device, "position_count": 934,
                      "benchmark_sha256": result["benchmark_sha256"], "bundle_sha256": result["bundle_sha256"],
                      "d10_pass_asserted": False}, sort_keys=True))


if __name__ == "__main__":
    main()
