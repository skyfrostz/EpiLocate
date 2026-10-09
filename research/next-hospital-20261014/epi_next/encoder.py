"""EPI-NEXT frozen feature plumbing; no automatic downloads or clinical claims.

Spatial inputs/features use N,C,D,H,W. Geometry is the caller's explicit ledger.
No GT is accepted. Real CT-FM inference remains gated on local verified weights.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import importlib.util
import io
import json
import os
import tempfile
from pathlib import Path
import re
from typing import Mapping, Sequence

import numpy as np
import torch
from torch import Tensor, nn

CTFM_REPO_REVISION = "f58c89a75ff0270ba6e339027e40bf04a221735d"
CTFM_MODEL_REVISION = "527b0d1c262b433396c85ff2de84c427b26945a1"
CTFM_CONFIG = dict(blocks_down=[1, 2, 2, 4, 4], in_channels=1, init_filters=32, spatial_dims=3)


class ModelUnavailable(RuntimeError):
    status = "MODEL_UNAVAILABLE"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def ctfm_availability() -> dict:
    missing = [name for name in ("monai", "safetensors")
               if importlib.util.find_spec(name) is None]
    return {"status": "MODEL_UNAVAILABLE" if missing else "NOT RUN",
            "missing_dependencies": missing, "weights_loaded": False, "runtime_path": "monai.networks.nets.segresnet_ds.SegResEncoder",
            "model_revision": CTFM_MODEL_REVISION, "pretraining_overlap_status": "unknown"}


def load_ctfm_local(checkpoint: str | Path, expected_sha256: str) -> "FrozenEncoderAdapter":
    """Load only an explicitly provided safetensors file; never fetch or run remote code.

    This loader is tested with genuine CT-FM weights and a synthetic 32-cube CPU input.
    Real-case geometry and clinical evaluation remain separate unrun gates.
    Strict state-key checking rejects incompatible versions rather than guessing.
    """
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("expected checkpoint SHA256 is required")
    path = Path(checkpoint)
    if path.suffix != ".safetensors" or not path.is_file():
        raise ModelUnavailable("local safetensors checkpoint is required")
    raw = path.read_bytes()
    if sha256_bytes(raw) != expected_sha256:
        raise ModelUnavailable("checkpoint SHA256 mismatch")
    availability = ctfm_availability()
    if availability["missing_dependencies"]:
        raise ModelUnavailable("missing dependencies: " + ",".join(availability["missing_dependencies"]))
    from monai.networks.nets.segresnet_ds import SegResEncoder
    from safetensors.torch import load
    model = SegResEncoder(**CTFM_CONFIG)
    try:
        model.load_state_dict(load(raw), strict=True)
    except (RuntimeError, ValueError) as exc:
        raise ModelUnavailable("strict CT-FM state validation failed") from exc
    return FrozenEncoderAdapter(model)


class FrozenEncoderAdapter(nn.Module):
    """Freeze weights and statistics, optionally retaining input/mask gradients."""
    def __init__(self, encoder: nn.Module, output_index: int = -1):
        super().__init__()
        self.encoder = encoder
        self.output_index = output_index
        self.actual_queries = 0
        for p in encoder.parameters():
            p.requires_grad_(False)
        self.train(False)

    def train(self, mode: bool = True):
        # Calling parent model.train() must never unfreeze normalization statistics.
        super().train(False)
        return self

    def extract(self, volume: Tensor, preserve_input_grad: bool = False) -> Tensor:
        if volume.ndim != 5 or not volume.is_floating_point() or not torch.isfinite(volume).all():
            raise ValueError("expected finite floating N,C,D,H,W tensor")
        self.encoder.eval()
        self.actual_queries += 1
        with torch.set_grad_enabled(preserve_input_grad):
            value = self.encoder(volume)
            if isinstance(value, (list, tuple)):
                value = value[self.output_index]
            if not isinstance(value, Tensor) or value.ndim != 5 or value.shape[0] != volume.shape[0]:
                raise ValueError("encoder must produce N,F,d,h,w spatial features")
            if not torch.isfinite(value).all():
                raise ValueError("nonfinite encoder output")
            return value

    def forward(self, volume: Tensor) -> Tensor:
        return self.extract(volume)


def scale_hu(volume_hu: Tensor) -> Tensor:
    """Only the model-card intensity operation; does not perform orientation/resampling."""
    if not volume_hu.is_floating_point() or not torch.isfinite(volume_hu).all():
        raise ValueError("finite floating HU required")
    return (volume_hu.clamp(-1024, 2048) + 1024) / 3072


class CaseLinearHead(nn.Module):
    """One pooled vector per patient. Scores are uncalibrated softmax outputs."""
    def __init__(self, feature_channels: int, num_classes: int = 2):
        super().__init__()
        if feature_channels < 1 or num_classes < 2:
            raise ValueError("positive channels and >=2 classes required")
        self.register_buffer("mean", torch.zeros(feature_channels))
        self.register_buffer("scale", torch.ones(feature_channels))
        self.linear = nn.Linear(feature_channels, num_classes)

    def forward(self, features: Tensor) -> Tensor:
        if features.ndim == 5:
            features = features.mean(dim=(2, 3, 4))
        if features.ndim != 2 or features.shape[1] != self.mean.numel():
            raise ValueError("expected pooled N,F or spatial N,F,d,h,w")
        return self.linear((features - self.mean) / self.scale)


def class_contribution_map(features: Tensor, head: CaseLinearHead, target: int) -> Tensor:
    """Signed standardized CAM; CAM.mean(spatial) + target bias == target logit.

    Standardization offset is retained in the map. This is coarse contribution,
    not a disease probability or an input perturbation response.
    """
    if features.ndim != 5 or features.shape[1] != head.mean.numel():
        raise ValueError("spatial N,F,d,h,w features required")
    if not 0 <= target < head.linear.out_features:
        raise ValueError("target out of range")
    normalized = (features - head.mean[None, :, None, None, None]) / head.scale[None, :, None, None, None]
    return torch.einsum("ncxyz,c->nxyz", normalized, head.linear.weight[target])


@dataclass(frozen=True)
class HeadConfig:
    seeds: tuple[int, ...] = (17, 29, 43)
    epochs: int = 100
    learning_rate: float = 0.001
    weight_decay: float = 0.0001

    def __post_init__(self):
        if not 1 <= len(self.seeds) <= 3 or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("use 1 to 3 unique predeclared seeds")
        if not 1 <= self.epochs <= 100 or not np.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError("invalid fixed training budget")
        if not np.isfinite(self.weight_decay) or self.weight_decay < 0:
            raise ValueError("invalid weight decay")


def fit_patient_head(features: Tensor, labels: Tensor, patient_ids: Sequence[str],
                     splits: Sequence[str], config: HeadConfig = HeadConfig(),
                     seed: int = 17, num_classes: int = 2) -> tuple[CaseLinearHead, dict]:
    """CPU full-batch equal-patient CE; train-only statistics and optimization.

    Input requires exactly one already-aggregated vector per patient. Validation
    vectors may be present but never fit/choose parameters. Test is rejected.
    Fixed epochs; no post-hoc seed/model selection is performed here.
    """
    n = len(patient_ids)
    if features.ndim != 2 or features.shape[0] != n or len(splits) != n or labels.shape != (n,):
        raise ValueError("one feature vector and label per patient required")
    if len(set(patient_ids)) != n or any(not p for p in patient_ids):
        raise ValueError("duplicate or empty patient IDs are not equal-patient input")
    if set(splits) - {"train", "observed_validation"}:
        raise ValueError("test/sealed/unknown split is forbidden")
    if seed not in config.seeds or features.device.type != "cpu" or labels.device.type != "cpu":
        raise ValueError("predeclared seed and CPU tensors required")
    if not features.is_floating_point() or not torch.isfinite(features).all():
        raise ValueError("finite features required")
    if labels.dtype != torch.long or torch.any((labels < 0) | (labels >= num_classes)):
        raise ValueError("verified integer labels in class range required")
    ix = torch.tensor([s == "train" for s in splits], dtype=torch.bool)
    if ix.sum() < 2 or len(torch.unique(labels[ix])) != num_classes:
        raise ValueError("training set must contain each declared class")
    x, y = features[ix].detach().float(), labels[ix]
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        head = CaseLinearHead(features.shape[1], num_classes)
        head.mean.copy_(x.mean(0))
        head.scale.copy_(x.std(0, unbiased=False).clamp_min(1e-6))
        opt = torch.optim.AdamW(head.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
        losses = []
        for _ in range(config.epochs):
            opt.zero_grad()
            loss = nn.functional.cross_entropy(head(x), y, reduction="mean")
            if not torch.isfinite(loss):
                raise ValueError("nonfinite training loss")
            losses.append(float(loss.detach()))
            loss.backward()
            opt.step()
    head.eval()
    return head, {"seed": seed, "training_patients": int(ix.sum()), "losses": losses,
                  "patient_weighting": "one_equal_loss_per_patient", "calibration_status": "UNCALIBRATED",
                  "selection_rule": "fixed_final_epoch_no_validation_selection", "config": asdict(config)}


_REQUIRED_CACHE_FIELDS = {"input_sha", "model_sha", "preprocess_sha", "geometry_sha", "config_sha", "code_sha", "split_manifest_sha"}


def feature_cache_key(metadata: Mapping) -> str:
    if not _REQUIRED_CACHE_FIELDS.issubset(metadata):
        raise ValueError("missing cache identity fields")
    if metadata.get("split") not in {"train", "observed_validation", "synthetic"}:
        raise ValueError("nonsealed cache split required")
    for key in _REQUIRED_CACHE_FIELDS:
        size = 40 if key == "code_sha" else 64
        if not re.fullmatch(r"[a-f0-9]{%d}" % size, str(metadata[key])):
            raise ValueError("invalid cache identity hash: " + key)
    return sha256_bytes(canonical_json(dict(metadata)))


def _feature_digest(array: np.ndarray) -> str:
    return sha256_bytes(canonical_json({"shape": list(array.shape), "dtype": str(array.dtype)}) + array.tobytes())


class FeatureCache:
    """Single immutable NPZ per key, no pickle, identity + feature-content hash checked.

    This is an encoder extraction cache; it is never an input-occlusion shortcut.
    Caller supplies hashes of exact normalized inputs, geometry and configuration.
    """
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def write(self, metadata: Mapping, features: Tensor) -> str:
        key = feature_cache_key(metadata)
        array = features.detach().cpu().contiguous().numpy()
        if array.ndim != 5 or not np.isfinite(array).all():
            raise ValueError("finite 5D spatial features required")
        payload = {"identity": dict(metadata), "feature_sha": _feature_digest(array)}
        stream = io.BytesIO()
        np.savez(stream, features=array, metadata=np.frombuffer(canonical_json(payload), dtype=np.uint8))
        # Publish only a fully flushed immutable file; link fails if key already exists.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.directory, prefix=".pending-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(stream.getvalue())
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, self.directory / (key + ".npz"))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return key

    def read(self, metadata: Mapping) -> Tensor:
        key = feature_cache_key(metadata)
        with np.load(self.directory / (key + ".npz"), allow_pickle=False) as loaded:
            array = loaded["features"]
            payload = json.loads(loaded["metadata"].tobytes())
        if payload["identity"] != dict(metadata) or payload["feature_sha"] != _feature_digest(array):
            raise ValueError("cache identity/content mismatch")
        if array.ndim != 5 or not np.isfinite(array).all():
            raise ValueError("invalid cached features")
        return torch.from_numpy(array.copy())
