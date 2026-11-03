#!/usr/bin/env python3
"""Step 7: verify pretrained backbone loading and the replacement head."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import torch
import torchvision
from torchvision.models import ResNet18_Weights

from src.data_checks import PROJECT_ROOT, load_config
from src.model import build_model


def check_model(config):
    if config["model"]["pretrained"] is not True:
        raise ValueError("Step 7 acceptance requires pretrained weights")
    torch.manual_seed(config["seed"])
    model = build_model(config)
    weights = ResNet18_Weights.DEFAULT
    # Verify all backbone tensors, including batch-norm buffers, against the source.
    reference = weights.get_state_dict(progress=False, check_hash=True)
    actual = model.state_dict()
    keys = [key for key in reference if not key.startswith("fc.")]
    mismatches = [key for key in keys if not torch.equal(reference[key], actual[key])]
    assert not mismatches, f"Pretrained backbone mismatch: {mismatches}"
    assert isinstance(model.fc, torch.nn.Linear)
    assert model.fc.in_features == 512 and model.fc.out_features == 2
    # Structural forward only: no DICOM, loss, optimizer, backward, or training here.
    model.eval()
    size = int(config["preprocessing"]["image_size"])
    with torch.inference_mode():
        result = model(torch.zeros(1, 3, size, size))
    assert result.shape == (1, 2) and torch.isfinite(result).all()
    checkpoint = Path(torch.hub.get_dir()) / "checkpoints" / Path(urlparse(weights.url).path).name
    with checkpoint.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    expected_prefix = checkpoint.stem.rsplit("-", 1)[-1]
    assert digest.startswith(expected_prefix), "Pretrained checkpoint hash prefix mismatch"
    report = {"torch_version": torch.__version__, "torchvision_version": torchvision.__version__,
              "weights": str(weights), "weights_url": weights.url,
              "checkpoint_sha256": digest, "backbone_tensors_verified": len(keys),
              "fc_in_features": 512, "fc_out_features": 2,
              "head_status": "randomly initialized, not trained", "forward_device": "cpu",
              "structural_input_shape": [1, 3, size, size], "output_shape": list(result.shape),
              "finite_output": True, "training_started": False,
              "cuda_available": torch.cuda.is_available(), "mps_available": torch.backends.mps.is_available()}
    out = PROJECT_ROOT / "outputs/baseline"
    out.mkdir(parents=True, exist_ok=True)
    (out / "model_initialization.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/baseline.yaml")
    args = parser.parse_args()
    check_model(load_config(args.config))
