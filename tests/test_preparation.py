"""Regression checks for HU math, failure behavior and patient leakage."""
import hashlib
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

from scripts.create_splits import allocation, build_patient_split
from src.preprocessing import preprocess_dicom


class PreprocessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.dcm"
        meta = FileMetaDataset()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        self.ds = FileDataset(str(self.path), {}, file_meta=meta, preamble=b"\0"*128)
        self.ds.Modality = "CT"
        self.ds.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
        self.ds.Rows = self.ds.Columns = 2
        self.ds.SamplesPerPixel = 1
        self.ds.PhotometricInterpretation = "MONOCHROME2"
        self.ds.BitsAllocated = self.ds.BitsStored = 16
        self.ds.HighBit = 15
        self.ds.PixelRepresentation = 1
        self.ds.RescaleSlope = 2
        self.ds.RescaleIntercept = -1024
        self.ds.PixelData = np.array([[-1000, 0], [1000, 2000]], dtype="<i2").tobytes()
        self.config = {"preprocessing": {"window_center": -600, "window_width": 1500, "image_size": 2}}

    def save(self):
        self.ds.save_as(self.path, enforce_file_format=True)

    def test_exact_hu_window_and_normalization_order(self):
        self.save()
        before = hashlib.sha256(self.path.read_bytes()).digest()
        result = preprocess_dicom(self.path, self.config, return_stages=True)
        np.testing.assert_array_equal(result.hu, [[-3024, -1024], [976, 2976]])
        np.testing.assert_array_equal(result.windowed, [[-1350, -1024], [150, 150]])
        expected = np.array([[0, 326/1500], [1, 1]], dtype=np.float32)
        np.testing.assert_allclose(result.normalized, expected)
        for channel, (mean, std) in enumerate(zip([.485, .456, .406], [.229, .224, .225])):
            np.testing.assert_allclose(result.tensor[channel].numpy(), (expected-mean)/std, atol=1e-6)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), before)

    def test_resize_constant_and_channel_replication(self):
        self.ds.PixelData = np.zeros((2, 2), dtype="<i2").tobytes()
        self.config["preprocessing"]["image_size"] = 224
        self.save()
        tensor = preprocess_dicom(self.path, self.config)
        self.assertEqual(tuple(tensor.shape), (3, 224, 224))
        self.assertEqual(tensor.dtype, torch.float32)
        self.assertTrue(torch.isfinite(tensor).all())
        for channel, (mean, std) in enumerate(zip([.485, .456, .406], [.229, .224, .225])):
            self.assertTrue(torch.allclose(tensor[channel]*std+mean, torch.full((224, 224), 326/1500)))

    def test_missing_rescale_emits_both_warnings(self):
        del self.ds.RescaleSlope
        del self.ds.RescaleIntercept
        self.save()
        with warnings.catch_warnings(record=True) as notices:
            warnings.simplefilter("always")
            result = preprocess_dicom(self.path, self.config, return_stages=True)
        self.assertTrue(any("RescaleSlope" in str(n.message) for n in notices))
        self.assertTrue(any("RescaleIntercept" in str(n.message) for n in notices))
        np.testing.assert_array_equal(result.hu, [[-1000, 0], [1000, 2000]])

    def test_invalid_window_and_localizer_fail(self):
        self.save()
        self.config["preprocessing"]["window_width"] = 0
        with self.assertRaises(ValueError):
            preprocess_dicom(self.path, self.config)
        self.config["preprocessing"]["window_width"] = 1500
        self.ds.ImageType = ["ORIGINAL", "PRIMARY", "LOCALIZER"]
        self.save()
        with self.assertRaisesRegex(ValueError, "Localizer"):
            preprocess_dicom(self.path, self.config)

    def test_multiframe_fails_instead_of_selecting_a_frame(self):
        self.ds.NumberOfFrames = 2
        self.ds.PixelData *= 2
        self.save()
        with self.assertRaisesRegex(ValueError, "dimensions"):
            preprocess_dicom(self.path, self.config)


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame([{"patient_id": f"{label}-{i}", "label": label,
                                    "collection": "MIDRC-RICORD-1A" if label == "1" else "MIDRC-RICORD-1B"}
                                   for label in ("0", "1") for i in range(5) for _ in range(i+1)])
        self.settings = {"mode": "smoke", "counts_per_class": [3, 1, 1]}

    def test_stratification_disjointness_and_order_independence(self):
        a = build_patient_split(self.frame, self.settings, 42)
        b = build_patient_split(self.frame.iloc[::-1], self.settings, 42)
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(len(a), 10)
        self.assertEqual(a.patient_id.nunique(), 10)
        for _, group in a.groupby("label"):
            self.assertEqual(group.split.value_counts().to_dict(), {"train": 3, "val": 1, "test": 1})
        merged = self.frame.merge(a[["patient_id", "split"]], on="patient_id")
        self.assertTrue(merged.groupby("patient_id").split.nunique().eq(1).all())

    def test_conflicting_patient_fails(self):
        self.frame.loc[0, "label"] = "1"
        self.frame.loc[0, "patient_id"] = "0-1"
        with self.assertRaisesRegex(ValueError, "conflict"):
            build_patient_split(self.frame, self.settings, 42)

    def test_future_ratio_mode_and_small_sample_guard(self):
        settings = {"mode": "ratios", "ratios": [.7, .15, .15]}
        np.testing.assert_array_equal(allocation(100, settings), [70, 15, 15])
        with self.assertRaises(ValueError):
            allocation(2, settings)


if __name__ == "__main__":
    unittest.main()
