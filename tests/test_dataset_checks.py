import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import torch

from scripts.check_dicom_metadata import dimension_flags
from src.dataset import RICORDDataset


class DatasetChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "data/raw/example.dcm"
        self.raw.parent.mkdir(parents=True)
        self.raw.write_bytes(b"intentionally unreadable for failure-path testing")
        self.csv = self.root / "split.csv"
        self.frame = pd.DataFrame([{"patient_id": "patient", "collection": "MIDRC-RICORD-1A",
            "label": "1", "study_uid": "1.2.3", "series_uid": "1.2.3.4", "sop_uid": "1.2.3.4.5",
            "image_path": "data/raw/example.dcm", "modality": "CT", "series_description": "test"}])
        self.config = {"preprocessing": {"image_size": 224}}
        self.patcher = patch("src.data_checks.PROJECT_ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_swapped_label_rejected_at_construction(self):
        self.frame["label"] = "0"
        self.frame.to_csv(self.csv, index=False)
        with self.assertRaisesRegex(ValueError, "Collection/label mismatch"):
            RICORDDataset(self.csv, self.config)

    def test_shared_preprocessing_and_long_label_contract(self):
        self.frame.to_csv(self.csv, index=False)
        dataset = RICORDDataset(self.csv, self.config)
        tensor = torch.zeros(3, 224, 224)
        with patch("src.dataset.preprocess_dicom", return_value=tensor) as preprocess:
            image, label = dataset[0]
        preprocess.assert_called_once_with(self.raw, self.config)
        self.assertIs(image, tensor)
        self.assertEqual(label.dtype, torch.long)
        self.assertEqual(label.item(), 1)

    def test_bad_dicom_raises_with_path_not_skipped(self):
        self.frame.to_csv(self.csv, index=False)
        config = {"preprocessing": {"image_size": 224, "window_center": -600, "window_width": 1500}}
        dataset = RICORDDataset(self.csv, config)
        with self.assertRaisesRegex(RuntimeError, "data/raw/example.dcm"):
            dataset[0]

    def test_nonfinite_tensor_rejected(self):
        self.frame.to_csv(self.csv, index=False)
        dataset = RICORDDataset(self.csv, self.config)
        with patch("src.dataset.preprocess_dicom", return_value=torch.full((3, 224, 224), float("nan"))):
            with self.assertRaisesRegex(ValueError, "NaN/Inf"):
                dataset[0]


class MetadataChecks(unittest.TestCase):
    def test_dimensions_read_column_values_not_dataframe_column_names(self):
        frame = pd.DataFrame({"rows": ["512", "512"], "columns": ["512", "512"]})
        self.assertEqual(dimension_flags(frame), [])
        frame.loc[1, "columns"] = "888"
        self.assertEqual(dimension_flags(frame), ["variable_dimensions"])
        frame.loc[1, "rows"] = ""
        self.assertIn("invalid_dimensions", dimension_flags(frame))


if __name__ == "__main__":
    unittest.main()
