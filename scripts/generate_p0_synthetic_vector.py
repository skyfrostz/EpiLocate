#!/usr/bin/env python3
"""Create a deterministic, identifier-free CT DICOM for P0 API/UI tests."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian


def generate(path: Path) -> None:
    rows, columns = 80, 112
    y, x = np.indices((rows, columns))
    pixels = (350 + 3 * x + 2 * y + 150 * ((x // 14 + y // 10) % 2)).astype("<u2")
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = "1.2.826.0.1.3680043.8.498.20260926001"
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = "1.2.826.0.1.3680043.8.498.20260926002"
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "CT"
    ds.PatientIdentityRemoved = "YES"
    ds.BurnedInAnnotation = "NO"
    ds.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.SamplesPerPixel = 1
    ds.Rows, ds.Columns = rows, columns
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.RescaleSlope = "1"
    ds.RescaleIntercept = "-1024"
    ds.PixelData = pixels.tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(path, enforce_file_format=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    generate(parser.parse_args().output)
