"""Explicit opt-in CPU research runner. No DICOM, GPU, or network access."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np

from .artifacts import canonical_json, exclusive_local_queue, persist_run, reconcile_run, sha256
from .contracts import RunManifest


def source_identity():
    root = Path(__file__).resolve().parents[3]
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True))
    return sha, dirty


def doctor():
    import torch
    return {"protocol_id": "EPI-NEXT-HOSPITAL-20261014-v1", "mode": "LOCAL_CPU_ONLY",
            "python": sys.version, "torch": torch.__version__, "platform": platform.platform(),
            "cuda_available": torch.cuda.is_available(), "gpu_authorized": False,
            "mps_available": torch.backends.mps.is_available(),
            "modules": {x: importlib.util.find_spec(x) is not None for x in
                        ["numpy", "pydicom", "monai", "lighter_zoo", "safetensors"]},
            "ctfm_three_cases": "NOT RUN", "real_localization_validation": "NOT RUN",
            "application_default": "historical_read_only", "source": source_identity()}


def baseline_synthetic(args):
    if not args.enable_research:
        raise ValueError("EPI-NEXT feature flag disabled: pass --enable-research")
    # Serialize local compute as well as writes. Unknown state stops before any
    # weight load or forward; an identical request replays the stored evidence.
    with exclusive_local_queue(Path(args.output) / ".execution"):
        observed = reconcile_run(args.output, args.run_id)
        if observed["state"] == "COMMITTED":
            directory = Path(args.output) / args.run_id
            saved = json.loads((directory / "run_manifest.json").read_text())
            config = json.loads((directory / "config.json").read_text())
            if saved["model_sha"] != args.checkpoint_sha or config.get("experiment") != "EPI-NEXT-BASELINE-SYNTHETIC-NUMERICS-v1":
                raise RuntimeError("RESULT_CONFLICT: use a new run ID")
            return observed
        if observed["state"] != "ABSENT":
            raise RuntimeError(observed["state"] + ": reconcile before compute")
        return _baseline_synthetic_new(args)


def _baseline_synthetic_new(args):
    import torch
    from .baseline_bridge import load_verified_resnet18, Preprocessed2DPredictor
    torch.set_num_threads(1)
    torch.manual_seed(17)
    start = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    model = load_verified_resnet18(args.checkpoint, args.checkpoint_sha)
    load_seconds = time.perf_counter() - start
    predict = Preprocessed2DPredictor(model)
    yy, xx = np.mgrid[:224, :224]
    image = (0.15 + 0.65 * np.exp(-((xx - 92.) ** 2 + (yy - 113.) ** 2) / (2 * 27. ** 2))).astype(np.float32)
    config = {"experiment": "EPI-NEXT-BASELINE-SYNTHETIC-NUMERICS-v1", "seed": 17,
              "target": 1, "synthetic_generator": "Gaussian224-center92-113-sigma27-base0.15-amplitude0.65",
              "fill_normalized_intensity": 0.5, "image_shape": [224, 224],
              "patch_sizes_px": [16, 32, 64], "patch_center_xy": [92, 113],
              "device": "cpu", "intraop_threads": 1,
              "scope": "SYNTHETIC_INPUT_REAL_CHECKPOINT_NUMERICS_NOT_LOCALIZATION_VALIDATION"}
    baseline = predict(image)
    repeat = predict(image)
    rows = []
    def probability(logits):
        z = logits - max(logits)
        return float(np.exp(z)[1] / np.exp(z).sum())
    for size in config["patch_sizes_px"]:
        perturbed = image.copy()
        y, x = 113 - size // 2, 92 - size // 2
        perturbed[y:y+size, x:x+size] = config["fill_normalized_intensity"]
        logits = predict(perturbed)
        rows.append({"size_px": size, "bbox_xyxy": [x, y, x+size, y+size],
                     "masked_logits": logits.tolist(), "fixed_target": 1,
                     "baseline_margin": float(baseline[1] - baseline[0]),
                     "masked_margin": float(logits[1] - logits[0]),
                     "signed_margin_response": float((baseline[1] - baseline[0]) - (logits[1] - logits[0])),
                     "target_probability_response": probability(baseline) - probability(logits)})
    result = {"evidence_scope": config["scope"], "baseline_logits": baseline.tolist(),
              "repeat_logits": repeat.tolist(), "repeat_max_abs_difference": float(abs(baseline-repeat).max()),
              "raw_target_score": probability(baseline), "calibration_status": "UNCALIBRATED",
              "rows": rows, "actual_model_calls": predict.calls, "real_patient_count": 0,
              "localization_quality": "NOT RUN", "ctfm_feasibility": "NOT RUN"}
    source_sha, dirty = source_identity()
    artifacts = {"config.json": canonical_json(config), "numeric_result.json": canonical_json(result)}
    manifest = RunManifest(args.run_id, source_sha, sha256(artifacts["config.json"]),
                           sha256(b"SYNTHETIC_NO_PATIENT_SPLIT"), args.checkpoint_sha, 17,
                           {"python": sys.version, "torch": torch.__version__, "numpy": np.__version__},
                           {"device": "cpu", "platform": platform.platform()}, started_at,
                           {"load_seconds": load_seconds, "total_seconds": time.perf_counter()-start},
                           predict.calls, None, [], {k:sha256(v) for k,v in artifacts.items()},
                           config["scope"], "EXISTING_PRIVATE_CHECKPOINT_NO_REDISTRIBUTION",
                           source_dirty=dirty, command=sys.argv, exit_code=0, process_running=False)
    artifacts["run_manifest.json"] = canonical_json(manifest.to_dict())
    return persist_run(args.output, args.run_id, artifacts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--output", type=Path, required=True)
    reconcile.add_argument("--run-id", required=True)
    baseline = sub.add_parser("baseline-synthetic")
    baseline.add_argument("--enable-research", action="store_true")
    baseline.add_argument("--checkpoint", type=Path, required=True)
    baseline.add_argument("--checkpoint-sha", required=True)
    baseline.add_argument("--output", type=Path, required=True)
    baseline.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command == "doctor":
        result = doctor()
    elif args.command == "reconcile":
        result = reconcile_run(args.output, args.run_id)
    else:
        result = baseline_synthetic(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
