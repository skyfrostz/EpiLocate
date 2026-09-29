"""One CT preprocessing entry point for QC and future train/eval/inference."""
from dataclasses import dataclass
from pathlib import Path
import warnings

import numpy as np
import pydicom
import torch
from torchvision.models import ResNet18_Weights
from torchvision.transforms import InterpolationMode
from torchvision.transforms import functional as TF

from src.data_checks import load_config


@dataclass
class PreprocessedDicom:
    tensor: torch.Tensor
    raw: np.ndarray
    hu: np.ndarray
    windowed: np.ndarray
    normalized: np.ndarray
    resized: torch.Tensor
    metadata: dict


def rescale_value(dataset, keyword, default):
    value = getattr(dataset, keyword, None)
    if value is None or str(value).strip() == "":
        warnings.warn(f"Missing {keyword}; using {default}", RuntimeWarning, stacklevel=2)
        return float(default)
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"Non-finite {keyword}")
    if keyword == "RescaleSlope" and result == 0:
        raise ValueError("RescaleSlope cannot be zero")
    return result


def preprocess_dicom(path: str | Path, config=None, *, return_stages=False):
    """Return float32 [3,H,W], or intermediate stages for QC (no pixel writes).

    Apply slope/intercept -> configured HU window -> [0,1] -> bilinear
    antialiased resize -> channel replication -> torchvision weight mean/std.
    The weight preset's resize/crop are intentionally not applied.
    """
    config = load_config() if config is None else config
    settings = config["preprocessing"]
    center, width = float(settings["window_center"]), float(settings["window_width"])
    size = int(settings["image_size"])
    if not np.isfinite([center, width]).all() or width <= 0 or size <= 0:
        raise ValueError("Window parameters must be finite; width and image_size must be positive")
    ds = pydicom.dcmread(path)
    if str(getattr(ds, "Modality", "")) != "CT":
        raise ValueError("Expected Modality=CT")
    if "LOCALIZER" in getattr(ds, "ImageType", []):
        raise ValueError("Localizer/scout is not an axial CT slice")
    if getattr(ds, "PhotometricInterpretation", "") != "MONOCHROME2":
        raise ValueError("Unsupported photometric interpretation; requires explicit review")
    raw = np.asarray(ds.pixel_array)
    if raw.ndim != 2 or raw.shape != (int(ds.Rows), int(ds.Columns)) or min(raw.shape) < 2:
        raise ValueError(f"Unexpected CT dimensions: {raw.shape}")
    if not np.isfinite(raw).all():
        raise ValueError("Raw pixels contain NaN/Inf")
    slope = rescale_value(ds, "RescaleSlope", 1)
    intercept = rescale_value(ds, "RescaleIntercept", 0)
    hu = raw.astype(np.float32) * slope + intercept
    lower, upper = center - width / 2, center + width / 2
    windowed = np.clip(hu, lower, upper)
    normalized = (windowed - lower) / width
    one_channel = torch.from_numpy(normalized).unsqueeze(0)
    resized = TF.resize(one_channel, [size, size], interpolation=InterpolationMode.BILINEAR, antialias=True)
    rgb = resized.repeat(3, 1, 1)
    # This reads installed torchvision metadata only; it does not download weights.
    preset = ResNet18_Weights.DEFAULT.transforms()
    tensor = TF.normalize(rgb, mean=preset.mean, std=preset.std)
    if not np.isfinite(hu).all() or not torch.isfinite(tensor).all():
        raise ValueError("Preprocessing produced NaN/Inf")
    if normalized.min() < 0 or normalized.max() > 1:
        raise ValueError("Window normalization outside [0,1]")
    if not return_stages:
        return tensor
    metadata = {key: str(getattr(ds, key, "")) for key in
                ("PatientID", "StudyInstanceUID", "SeriesInstanceUID", "SeriesDescription", "InstanceNumber")}
    metadata.update(slope=slope, intercept=intercept, mean=preset.mean, std=preset.std,
                    weights=str(ResNet18_Weights.DEFAULT),
                    pixel_spacing=[float(v) for v in getattr(ds, "PixelSpacing", [])])
    return PreprocessedDicom(tensor, raw, hu, windowed, normalized, resized, metadata)
