"""Reproducible synthetic Worker benchmark and numerical-reference capture."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

import torch

from algorithm.service import MODEL_ID, MODEL_SHA, PREPROCESSING_VERSION, PROTOCOL_ID
from .consistency import capture_bundle, compare_bundles
from .inference import FrozenRunner


def _synchronize(runner: FrozenRunner) -> None:
    if runner.device_selection.actual == "CUDA":
        torch.cuda.synchronize(runner.device_selection.torch_device)


def _timed(runner: FrozenRunner, claim: dict, fixture: Path, output_dir: Path):
    _synchronize(runner)
    started = time.perf_counter()
    output = runner.run(claim, fixture, output_dir)
    _synchronize(runner)
    return output, round((time.perf_counter() - started) * 1000, 3)


def _claim(kind: str, input_hash: str) -> dict:
    return {"job_id": "job_synthetic_benchmark", "case_id": "case_synthetic_benchmark",
            "attempt_id": "00000000-0000-4000-8000-000000000001", "lease_token": "local-benchmark-only",
            "input_reference": {"sha256": input_hash},
            "model_version": {"model_id": MODEL_ID, "checkpoint_sha256": MODEL_SHA,
                              "preprocessing_version": PREPROCESSING_VERSION, "protocol_id": PROTOCOL_ID},
            "job_parameters": {"kind": kind, "slice_id": "slice_synthetic_benchmark",
                               "scales": [16, 32, 64] if kind == "OCCLUSION" else []}}


def run_benchmark(frozen_root: Path, fixture: Path, device: str) -> tuple[dict, dict]:
    input_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
    started = time.perf_counter()
    runner = FrozenRunner(frozen_root, MODEL_SHA, device)
    _synchronize(runner)
    initialization_ms = round((time.perf_counter() - started) * 1000, 3)
    if runner.device_selection.actual == "CUDA":
        torch.cuda.reset_peak_memory_stats(runner.device_selection.torch_device)
    with tempfile.TemporaryDirectory(prefix="epilocate-benchmark-") as directory:
        root = Path(directory)
        prediction = _claim("PREDICTION", input_hash)
        occlusion = _claim("OCCLUSION", input_hash)
        cold_prediction, cold_prediction_ms = _timed(runner, prediction, fixture, root / "cold-prediction")
        _, warm_prediction_ms = _timed(runner, prediction, fixture, root / "warm-prediction")
        cold_occlusion, cold_occlusion_ms = _timed(runner, occlusion, fixture, root / "cold-occlusion")
        _, warm_occlusion_ms = _timed(runner, occlusion, fixture, root / "warm-occlusion")
        bundle = capture_bundle(cold_occlusion, input_hash, runner.device_selection.actual)
    _synchronize(runner)
    benchmark = {
        "benchmark_version": "1.0", "requested_device": device, "actual_device": runner.device_selection.actual,
        "gpu_name": runner.device_selection.gpu_name, "gpu_memory_mib": runner.device_selection.gpu_memory_mib,
        "torch_version": str(torch.__version__), "torch_cuda_runtime": torch.version.cuda,
        "model_hash": MODEL_SHA, "input_sha256": input_hash,
        "preprocessing_version": PREPROCESSING_VERSION, "protocol_id": PROTOCOL_ID,
        "timings_ms": {"model_initialization": initialization_ms,
                       "prediction_cold": cold_prediction_ms, "prediction_warm": warm_prediction_ms,
                       "occlusion_cold": cold_occlusion_ms, "occlusion_warm": warm_occlusion_ms},
        "peak_gpu_memory_allocated_bytes": (torch.cuda.max_memory_allocated(runner.device_selection.torch_device)
                                            if runner.device_selection.actual == "CUDA" else None),
        "prediction": cold_prediction.result["prediction"],
        "position_count_by_scale": {str(scale): sum(item["block_size"] == scale for item in bundle["result"]["positions"])
                                    for scale in (16, 32, 64)},
        "assets": {name: {key: value for key, value in asset.items() if key != "png_base64"}
                   for name, asset in bundle["assets"].items()},
    }
    return benchmark, bundle


def _write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=Path("docs/interfaces/fixtures/p0_synthetic_ct.dcm"))
    parser.add_argument("--device", choices=("CPU", "CUDA", "AUTO"), default="CPU")
    parser.add_argument("--benchmark-output", type=Path, required=True)
    parser.add_argument("--bundle-output", type=Path, required=True)
    parser.add_argument("--compare-to", type=Path)
    args = parser.parse_args()
    benchmark, bundle = run_benchmark(args.frozen_root, args.fixture, args.device)
    if args.compare_to:
        reference = json.loads(args.compare_to.read_text(encoding="utf-8"))
        benchmark["comparison"] = compare_bundles(reference, bundle)
    _write_new(args.benchmark_output, benchmark)
    _write_new(args.bundle_output, bundle)
    print(json.dumps({"actual_device": benchmark["actual_device"], "benchmark": str(args.benchmark_output),
                      "bundle": str(args.bundle_output), "comparison_passed": benchmark.get("comparison", {}).get("passed")},
                     sort_keys=True))
    if args.compare_to and not benchmark["comparison"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
