"""Generate anonymous 112×80 DICOM geometry fixtures; never use patient data.

Run with a Python environment containing pydicom. Outputs are ignored by Git.
"""
from __future__ import annotations

from array import array
from pathlib import Path
import sys

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.local'
OUTPUT.mkdir(exist_ok=True)


def make(name: str, oriented: bool) -> None:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = '2.25.18499269058459638566132766337321489010' if oriented else '2.25.18499269058459638566132766337321489011'
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = '2.25.18499269058459638566132766337321489012'
    data = FileDataset(name, {}, file_meta=meta, preamble=b'\0' * 128)
    data.SOPClassUID = meta.MediaStorageSOPClassUID
    data.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    data.Modality = 'CT'
    data.PatientName = 'SYNTHETIC^GEOMETRY'
    data.PatientID = 'SYNTHETIC-ONLY'
    data.Rows = 80
    data.Columns = 112
    data.SamplesPerPixel = 1
    data.PhotometricInterpretation = 'MONOCHROME2'
    data.BitsAllocated = 16
    data.BitsStored = 16
    data.HighBit = 15
    data.PixelRepresentation = 0
    data.RescaleSlope = 1
    data.RescaleIntercept = -1024
    data.WindowCenter = -400
    data.WindowWidth = 1200
    if oriented:
        data.PixelSpacing = [0.7, 1.2]
        data.ImageOrientationPatient = [0, 1, 0, -1, 0, 0]
        data.ImagePositionPatient = [12, 34, 56]
    pixels = array('H', (400 + 250 * ((row // 10 + col // 14) % 2) + row * 8
                         for row in range(data.Rows) for col in range(data.Columns)))
    if sys.byteorder != 'little':
        pixels.byteswap()
    data.PixelData = pixels.tobytes()
    data.save_as(OUTPUT / name, enforce_file_format=True)


if __name__ == '__main__':
    make('geometry_synthetic_ct.dcm', False)
    make('geometry_synthetic_oriented_ct.dcm', True)
    print('Generated anonymous geometry fixtures in frontend/.local')
