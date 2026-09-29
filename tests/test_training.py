import unittest

import numpy as np
import pandas as pd

from scripts.run_tiny_overfit import select_fixed_slices
from src.training import classification_metrics, patient_predictions


class TrainingChecks(unittest.TestCase):
    def test_classification_metrics_known_confusion_matrix(self):
        labels = np.array([0, 0, 1, 1])
        probabilities = np.array([[0.9, 0.1], [0.4, 0.6], [0.2, 0.8], [0.7, 0.3]])
        result = classification_metrics(labels, probabilities)
        self.assertEqual(result["confusion_matrix"], [[1, 1], [1, 1]])
        self.assertEqual(result["accuracy"], 0.5)
        self.assertEqual(result["sensitivity"], 0.5)
        self.assertEqual(result["specificity"], 0.5)

    def test_metrics_reject_single_label(self):
        with self.assertRaisesRegex(ValueError, "Both labels"):
            classification_metrics([0, 0], [[0.8, 0.2], [0.7, 0.3]])

    def test_patient_predictions_average_slice_probabilities(self):
        slices = pd.DataFrame([
            {"patient_id": "p0", "study_uid": "s0", "series_uid": "r0", "true_label": 0,
             "prob_negative": 0.8, "prob_positive": 0.2},
            {"patient_id": "p0", "study_uid": "s0", "series_uid": "r0", "true_label": 0,
             "prob_negative": 0.6, "prob_positive": 0.4},
            {"patient_id": "p1", "study_uid": "s1", "series_uid": "r1", "true_label": 1,
             "prob_negative": 0.1, "prob_positive": 0.9},
        ])
        patients = patient_predictions(slices).set_index("patient_id")
        self.assertAlmostEqual(patients.loc["p0", "prob_positive"], 0.3)
        self.assertEqual(patients.loc["p0", "pred_label"], 0)
        self.assertEqual(patients.loc["p1", "pred_label"], 1)

    def test_tiny_selection_is_balanced_and_deterministic(self):
        rows = []
        for label in ("0", "1"):
            for i in range(20):
                rows.append({"label": label, "patient_id": f"p{label}", "series_uid": f"s{label}",
                             "instance_number": str(i), "image_path": f"{label}/{i}.dcm"})
        frame = pd.DataFrame(rows)
        first = select_fixed_slices(frame, 16, 42)
        second = select_fixed_slices(frame, 16, 42)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(first.label.value_counts().to_dict(), {"0": 8, "1": 8})


if __name__ == "__main__":
    unittest.main()
