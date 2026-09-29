"""Slice dataset backed by validated patient splits and shared preprocessing."""
from copy import deepcopy

import torch
from torch.utils.data import Dataset

from src.data_checks import load_config, project_path, read_manifest
from src.preprocessing import preprocess_dicom


class RICORDDataset(Dataset):
    def __init__(self, csv_path, config=None):
        self.config = deepcopy(load_config() if config is None else config)
        self.frame = read_manifest(csv_path).reset_index(drop=True)
        if self.frame.modality.ne("CT").any():
            raise ValueError("RICORDDataset requires CT images")
        self.records = self.frame[["image_path", "label"]].to_dict("records")

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        record = self.records[index]
        try:
            image = preprocess_dicom(project_path(record["image_path"]), self.config)
        except Exception as exc:
            raise RuntimeError(f"Cannot preprocess {record['image_path']}: {exc}") from exc
        size = int(self.config["preprocessing"]["image_size"])
        if image.shape != (3, size, size) or image.dtype != torch.float32:
            raise ValueError(f"Unexpected image shape/dtype at {record['image_path']}")
        if not torch.isfinite(image).all():
            raise ValueError(f"NaN/Inf at {record['image_path']}")
        return image, torch.tensor(int(record["label"]), dtype=torch.long)
