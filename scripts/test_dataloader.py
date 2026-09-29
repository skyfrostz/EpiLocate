#!/usr/bin/env python3
"""Step 6: a real sample and batch from every split, without model training."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import torch
from torch.utils.data import DataLoader

from src.data_checks import PROJECT_ROOT, load_config
from src.dataset import RICORDDataset


def tensor_stats(images):
    return {"shape": list(images.shape), "dtype": str(images.dtype),
            "finite": bool(torch.isfinite(images).all()),
            "min": images.min().item(), "max": images.max().item(),
            "mean": images.mean().item(), "std": images.std().item()}


def smoke_test(config):
    datasets = {split: RICORDDataset(config["data"][f"{split}_csv"], config)
                for split in ("train", "val", "test")}
    patients = {name: set(ds.frame.patient_id) for name, ds in datasets.items()}
    assert not patients["train"] & patients["val"], "train/val patient leakage"
    assert not patients["train"] & patients["test"], "train/test patient leakage"
    assert not patients["val"] & patients["test"], "val/test patient leakage"
    size = int(config["preprocessing"]["image_size"])
    batch_size = int(config["training"]["batch_size"])
    report = {"patient_leakage": 0, "batch_size": batch_size, "splits": {}}
    for name, dataset in datasets.items():
        image, label = dataset[0]
        assert image.shape == (3, size, size) and image.dtype == torch.float32
        assert label.ndim == 0 and label.dtype == torch.long and label.item() in (0, 1)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=name == "train", num_workers=0,
                            generator=torch.Generator().manual_seed(config["seed"]))
        images, labels = next(iter(loader))
        expected_batch = min(batch_size, len(dataset))
        assert images.shape == (expected_batch, 3, size, size)
        assert labels.shape == (expected_batch,) and labels.dtype == torch.long
        assert torch.isfinite(images).all(), f"NaN/Inf in {name}"
        assert torch.all((labels == 0) | (labels == 1))
        report["splits"][name] = {"patients": len(patients[name]), "slices": len(dataset),
            "single_image": tensor_stats(image), "batch_images": tensor_stats(images),
            "batch_labels_shape": list(labels.shape), "batch_labels_dtype": str(labels.dtype),
            "batch_labels": labels.tolist()}
    out = PROJECT_ROOT / "outputs/baseline"
    out.mkdir(parents=True, exist_ok=True)
    (out / "dataloader_smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/baseline.yaml")
    args = parser.parse_args()
    smoke_test(load_config(args.config))
