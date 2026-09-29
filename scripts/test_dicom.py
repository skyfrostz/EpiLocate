#!/usr/bin/env python3
"""Read and display the first valid CT DICOM under data/raw."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pydicom


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"


def value_text(dataset: Any, keyword: str) -> str:
    value = getattr(dataset, keyword, "")
    return "" if value is None else str(value).strip()


def main() -> int:
    files = sorted(RAW_ROOT.rglob("*.dcm"), key=lambda path: path.as_posix())
    warnings: list[str] = []

    for path in files:
        try:
            dataset = pydicom.dcmread(path)
            if value_text(dataset, "Modality").upper() != "CT":
                continue
            image = np.asarray(dataset.pixel_array)
        except Exception as exc:
            warnings.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue

        print(f"File: {path.relative_to(PROJECT_ROOT).as_posix()}")
        print(f"PatientID: {value_text(dataset, 'PatientID')}")
        print(f"Modality: {value_text(dataset, 'Modality')}")
        print(f"StudyInstanceUID: {value_text(dataset, 'StudyInstanceUID')}")
        print(f"SeriesInstanceUID: {value_text(dataset, 'SeriesInstanceUID')}")
        print(f"SeriesDescription: {value_text(dataset, 'SeriesDescription')}")
        print(f"Rows x Columns: {value_text(dataset, 'Rows')} x {value_text(dataset, 'Columns')}")
        print(f"pixel_array shape: {image.shape}")
        print(f"pixel min/max: {image.min()} / {image.max()}")
        print(f"RescaleSlope: {value_text(dataset, 'RescaleSlope')}")
        print(f"RescaleIntercept: {value_text(dataset, 'RescaleIntercept')}")

        display_image = image[0] if image.ndim > 2 else image
        plt.imshow(display_image, cmap="gray")
        plt.title(f"Raw CT - {value_text(dataset, 'PatientID')}")
        plt.axis("off")
        plt.tight_layout()
        plt.show()
        return 0

    for warning in warnings[:20]:
        print(f"WARNING: {warning}", file=sys.stderr)
    print("ERROR: no readable CT DICOM with pixel data was found", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
