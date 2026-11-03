"""Bounded E1/E2 execution on one synthetic image and a real frozen checkpoint.

No patient or GT files are read. This verifies executability, not lesion quality.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import time

import numpy as np
import torch

from .artifacts import canonical_json, sha256
from .baseline_bridge import load_verified_resnet18, Preprocessed2DPredictor
from .cli import source_identity
from .hspi import HSPIConfig, hspi_reference
from .localization import occlusion_2d


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("existing evidence preserved; choose a new output")
    torch.set_num_threads(1)
    torch.manual_seed(17)
    began = time.perf_counter()
    model = load_verified_resnet18(args.checkpoint, args.checkpoint_sha)
    yy, xx = np.mgrid[:224, :224]
    image = (0.15 + 0.65 * np.exp(-((xx-92.)**2 + (yy-113.)**2)/(2*27.**2))).astype(np.float32)
    support = np.ones_like(image, dtype=bool)
    predict = Preprocessed2DPredictor(model)
    e1 = occlusion_2d(predict, image, support, target=1, patch_sizes=(64,), fill=0.)
    assert e1["model_calls"] == predict.calls

    class DifferentiableNormalization(torch.nn.Module):
        def __init__(self, classifier):
            super().__init__()
            self.classifier = classifier
            self.register_buffer("mean", torch.tensor([.485, .456, .406])[None,:,None,None])
            self.register_buffer("std", torch.tensor([.229, .224, .225])[None,:,None,None])

        def forward(self, x):
            return self.classifier((x.repeat(1, 3, 1, 1) - self.mean) / self.std)

    # Locked project-reference 100-step budget, two grids and one stage. The
    # earlier v1 three-step loader diagnostic is retained as separate evidence.
    # Infeasibility is retained without relaxing CPF thresholds.
    config = HSPIConfig(grids=((4, 4), (7, 7)), stages=1, epochs=100)
    e2 = hspi_reference(DifferentiableNormalization(model), torch.from_numpy(image)[None,None],
                        config=config, valid_mask=torch.from_numpy(support))
    failed = e1["status"] in {"FAILED", "MODEL_FAILURE", "NUMERICAL_FAILURE"} or e2["status"] in {"FAILED", "MODEL_FAILURE", "NUMERICAL_FAILURE"}
    elapsed = time.perf_counter() - began
    git_sha, dirty = source_identity()
    result = {"experiment": "EPI-NEXT-E1-E2-REAL-WEIGHTS-SYNTHETIC-v2",
              "evidence_scope": "SYNTHETIC_INPUT_REAL_CHECKPOINT_EXECUTABILITY",
              "status": "FAIL" if failed else "PASS", "git_sha": git_sha, "source_dirty": dirty,
              "checkpoint_sha256": args.checkpoint_sha, "input_sha256": sha256(image.tobytes()),
              "config_sha256": sha256(canonical_json({"e1": {"target":1,"patch_sizes":[64],"fill":0.},"e2":e2["config"]})),
              "timestamp": datetime.now(timezone.utc).isoformat(),
              "environment": {"python": platform.python_version(), "torch":torch.__version__,
                              "numpy":np.__version__, "device":"cpu", "threads":1},
              "elapsed_seconds": elapsed, "peak_gpu_memory_bytes": None,
              "actual_model_calls": e1["model_calls"] + e2["model_calls"],
              "E1":e1, "E2":e2, "patient_count":0, "lesion_quality_comparison":"NOT RUN",
              "native_ct_overlay":"NOT RUN", "failure_or_infeasibility_is_not_normal_ct":True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(canonical_json(result))
    print(json.dumps({"output":str(args.output), "sha256":sha256(args.output.read_bytes()),
                      "E1_status":e1["status"], "E2_status":e2["status"],
                      "actual_model_calls":result["actual_model_calls"], "elapsed_seconds":elapsed}))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
