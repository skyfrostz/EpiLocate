"""Read-only verified ResNet-18 loader for EPI-NEXT experiments.

Accepts already preprocessed arrays only. This module does not decode DICOM,
select patients, change frozen preprocessing, or download weights.
"""
from pathlib import Path
import hashlib

import numpy as np
import torch
from torchvision.models import resnet18

from .contracts import require_hash


def load_verified_resnet18(path: Path, expected_sha: str):
    require_hash(expected_sha, "checkpoint_sha")
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("MODEL_UNAVAILABLE: checkpoint absent")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected_sha:
        raise ValueError("MODEL_UNAVAILABLE: checkpoint hash mismatch")
    # Safe tensor-only loading; never fall back to unrestricted pickle.
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    state = checkpoint.get("model_state_dict") if isinstance(checkpoint, dict) else None
    if not isinstance(state, dict):
        raise ValueError("MODEL_UNAVAILABLE: missing model_state_dict")
    if any(not isinstance(v, torch.Tensor) or not torch.isfinite(v).all() for v in state.values()):
        raise ValueError("MODEL_UNAVAILABLE: invalid checkpoint tensors")
    model = resnet18(weights=None, num_classes=2)
    model.load_state_dict(state, strict=True)
    model.eval().requires_grad_(False)
    return model


class Preprocessed2DPredictor:
    """One-channel normalized 224x224 input; replicate then ImageNet normalize.

    Input-level filling happens before this adapter. Scalars are normalized
    intensities, not HU or clinical counterfactuals. Gradients stay enabled when
    callers use the torch model directly for continuous masks.
    """
    def __init__(self, model):
        self.model = model
        self.calls = 0

    def __call__(self, image: np.ndarray) -> np.ndarray:
        image = np.asarray(image)
        if image.shape != (224, 224) or not np.isfinite(image).all() or image.min() < 0 or image.max() > 1:
            raise ValueError("expected finite normalized 224x224 input in [0,1]")
        tensor = torch.from_numpy(image.astype(np.float32, copy=True))[None, None].repeat(1, 3, 1, 1)
        mean = torch.tensor([.485, .456, .406])[None, :, None, None]
        std = torch.tensor([.229, .224, .225])[None, :, None, None]
        self.calls += 1
        with torch.inference_mode():
            logits = self.model((tensor - mean) / std)[0]
        if logits.shape != (2,) or not torch.isfinite(logits).all():
            raise ValueError("nonfinite or unexpected classifier output")
        return logits.numpy().astype(np.float64)
