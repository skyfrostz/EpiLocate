"""Synthetic contract tests for D10 evidence integrity and numeric isolation."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.research import d10_three_way_compare as compare


class ThreeWayComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.paths = {lane: self.root / lane for lane in ("A", "B", "C")}
        for lane, path in self.paths.items():
            self._make_capture(path, lane)

    def _read(self, lane):
        return json.loads((self.paths[lane] / "capture.json").read_text())

    def _write(self, lane, metadata):
        (self.paths[lane] / "capture.json").write_text(json.dumps(metadata, sort_keys=True))

    def _replace_tensor(self, lane, key, value):
        metadata = self._read(lane)
        path = self.paths[lane] / metadata["tensors"][key]["file"]
        np.save(path, value)
        metadata["tensors"][key].update(
            dtype=str(value.dtype), shape=list(value.shape), sha256=compare.canonical_sha256(value),
        )
        self._write(lane, metadata)

    def _make_capture(self, path, lane):
        path.mkdir()
        device = "CUDA" if lane == "C" else "CPU"
        flags = {
            "cuda_matmul_allow_tf32": False, "cudnn_allow_tf32": True, "cudnn_benchmark": False,
            "cudnn_deterministic": False, "torch_deterministic_algorithms": False,
            "float32_matmul_precision": "highest", "autocast_cpu": False, "autocast_cuda": False,
            "amp_used_by_tool": False, "cublas_workspace_config": None,
        }
        environment = {
            "os": "macOS-arm64" if lane == "A" else "Linux-x86_64", "python": "3.11.15",
            "torch": "2.14.0" if lane == "A" else "2.4.0+cu121", "torchvision": "0.19.0",
            "numpy": "2.4.6" if lane == "A" else "1.26.4", "pydicom": "3.0.1",
            "cuda_runtime": None if lane == "A" else "12.1", "driver": None if lane == "A" else "550.1",
            "cudnn_version": None if lane == "A" else 90100,
            "gpu_model": None if lane == "A" else "NVIDIA GeForce RTX 3090",
            "gpu_compute_capability": None if lane == "A" else [8, 6],
            "cpu_model": "arm64" if lane == "A" else "x86_64", "device": device,
            "input_dtype": "torch.float32", "model_dtype": "torch.float32", "precision_flags": flags,
            "node_fingerprint": "2" * 64 if lane == "A" else "3" * 64,
        }
        model = {
            "architecture": "ResNet", "parameter_count": 11177538, "state_dict_key_count": 122,
            "state_dict_keys_sha256": "a" * 64, "state_dict_values_sha256": "b" * 64,
            "checkpoint_sha256": compare.EXPECTED_CHECKPOINT_SHA256, "eval": True,
            "dtype": "torch.float32", "batchnorm_training_count": 0, "dropout_training_count": 0,
        }
        metadata = {
            "schema": "D10_LANE_CAPTURE_V1", "lane": lane, "device": device,
            "run_id": "RUN-D10-MAC-BASELINE" if lane == "A" else "RUN-D10-GPU-BASELINE",
            "input_sha256": compare.EXPECTED_INPUT_SHA256, "checkpoint_sha256": compare.EXPECTED_CHECKPOINT_SHA256,
            "config_sha256": {"stage": "c" * 64, "protocol": "d" * 64, "baseline": "e" * 64},
            "source_sha256": {"algorithm/service.py": "f" * 64}, "model_identity": model,
            "environment": environment, "layer_order": list(compare.LAYERS),
            "small_reference_positions": compare.expected_small_reference_positions(),
            "tensors": {},
        }
        input_tensor = np.full((3, 2, 2), 0.5, dtype=np.float32)
        logits = np.array([0.2, -0.2], dtype=np.float32)
        probability = np.array([0.6, 0.4], dtype=np.float32)
        values = {}
        for name in compare.PREPROCESSING:
            values[f"preprocessing/{name}"] = input_tensor.copy() if name != "raw" else np.ones((2, 2), dtype=np.int16)
        for sample in compare.SAMPLES:
            for name in compare.LAYERS:
                values[f"{sample}/{name}"] = (
                    input_tensor.copy() if name == "input" else probability.copy() if name == "probability" else logits.copy()
                )
        count = len(metadata["small_reference_positions"])
        values["small_reference/masked_tensors"] = np.stack([input_tensor] * count)
        for name in compare.SMALL_REFERENCE[1:]:
            values[f"small_reference/{name}"] = np.stack([probability if name.startswith("probabilities") else logits] * count)
        for name in compare.REPEATABILITY:
            values[f"repeatability/{name}"] = np.stack([probability] * 3)
        for index, (key, value) in enumerate(values.items()):
            filename = f"tensor_{index:03d}.npy"
            np.save(path / filename, value)
            metadata["tensors"][key] = {
                "file": filename, "shape": list(value.shape), "dtype": str(value.dtype),
                "sha256": compare.canonical_sha256(value),
            }
        (path / "capture.json").write_text(json.dumps(metadata, sort_keys=True))

    def _compare(self):
        return compare.compare_captures(self.paths["A"], self.paths["B"], self.paths["C"])

    def test_symmetric_relative_metric_handles_zero_and_sign_change(self):
        left = np.array([0.0, 0.0, 1.0, -1.0], dtype=np.float32)
        right = np.array([0.0, 1.0, 1.5, 1.0], dtype=np.float32)
        result = compare.numeric_metrics(left, right)
        self.assertEqual(result["max_abs_diff"], 2.0)
        self.assertEqual(result["mean_abs_diff"], 0.875)
        self.assertEqual(result["max_symmetric_relative_diff"], 2.0)
        self.assertAlmostEqual(result["mean_symmetric_relative_diff"], 1.1)
        self.assertEqual(result["max_abs_diff_index"], [3])
        zeros = compare.numeric_metrics(np.zeros(2), np.zeros(2))
        self.assertEqual(zeros["max_symmetric_relative_diff"], 0.0)
        self.assertTrue(zeros["exactly_equal"])

    def test_compatible_small_reference_never_claims_d10_pass(self):
        result, layerwise = self._compare()
        self.assertFalse(result["d10_pass_asserted"])
        self.assertFalse(result["formal_cuda_research_authorized"])
        self.assertEqual(result["interpretation"]["observed_small_probability_compatibility_case"], "CASE_4")
        self.assertEqual(result["root_cause"], "NOT_ESTABLISHED_BY_COMPARISON_ALONE")
        self.assertIsNone(layerwise["pairs"]["B_vs_C"]["samples"]["baseline"]["first_nonzero_divergence"])

    def test_layer_threshold_and_adjacent_growth_are_diagnostics(self):
        self._replace_tensor("C", "baseline/conv1", np.array([0.20001, -0.2], dtype=np.float32))
        self._replace_tensor("C", "baseline/layer1.0", np.array([0.2002, -0.2], dtype=np.float32))
        self._replace_tensor("C", "baseline/probability", np.array([0.5998, 0.4002], dtype=np.float32))
        result, layerwise = self._compare()
        layers = layerwise["pairs"]["B_vs_C"]["samples"]["baseline"]
        self.assertEqual(layers["first_nonzero_divergence"], "conv1")
        self.assertEqual(layers["first_threshold_exceeding_divergence"], "layer1.0")
        self.assertEqual(layers["largest_adjacent_growth_ratio"]["to_layer"], "layer1.0")
        self.assertGreater(layers["largest_adjacent_growth_ratio"]["growth_ratio"], 19.0)
        self.assertIsNone(layers["first_major_amplification"])
        self.assertEqual(result["interpretation"]["observed_small_probability_compatibility_case"], "CASE_1")
        self.assertFalse(result["pairs"]["B_vs_C"]["small_reference_probability_compatibility"]["compatible"])

    def test_modified_tensor_is_rejected_before_output(self):
        metadata = self._read("C")
        path = self.paths["C"] / metadata["tensors"]["baseline/conv1"]["file"]
        np.save(path, np.array([7, 8], dtype=np.float32))
        with self.assertRaisesRegex(compare.CaptureValidationError, "SHA-256 mismatch"):
            self._compare()
        output = self.root / "output"
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            compare.main(["compare", "--lane-a", str(self.paths["A"]), "--lane-b", str(self.paths["B"]),
                          "--lane-c", str(self.paths["C"]), "--out-dir", str(output)])
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse(output.exists())

    def test_metadata_shape_and_cross_lane_shape_mismatch_are_rejected(self):
        metadata = self._read("B")
        metadata["tensors"]["baseline/conv1"]["shape"] = [9]
        self._write("B", metadata)
        with self.assertRaisesRegex(compare.CaptureValidationError, "shape metadata mismatch"):
            self._compare()
        self._replace_tensor("B", "baseline/conv1", np.array([0.2, -0.2, 0.0], dtype=np.float32))
        with self.assertRaisesRegex(compare.CaptureValidationError, "tensor shape differs"):
            self._compare()

    def test_runtime_state_identity_mismatch_is_rejected(self):
        metadata = self._read("C")
        metadata["model_identity"]["state_dict_values_sha256"] = "1" * 64
        self._write("C", metadata)
        with self.assertRaisesRegex(compare.CaptureValidationError, "runtime model identity mismatch"):
            self._compare()

    def test_source_or_config_identity_mismatch_is_rejected(self):
        for field in ("source_sha256", "config_sha256"):
            with self.subTest(field=field):
                original = self._read("B")
                changed = json.loads(json.dumps(original))
                changed[field][next(iter(changed[field]))] = "9" * 64
                self._write("B", changed)
                with self.assertRaisesRegex(compare.CaptureValidationError, f"shared {field} mismatch"):
                    self._compare()
                self._write("B", original)

    def test_linux_cuda_environment_confounds_and_unrecorded_flags_are_rejected(self):
        original = self._read("C")
        changed = json.loads(json.dumps(original))
        changed["environment"]["precision_flags"]["cudnn_allow_tf32"] = False
        self._write("C", changed)
        with self.assertRaisesRegex(compare.CaptureValidationError, "environment differs beyond device"):
            self._compare()
        del original["environment"]["precision_flags"]["autocast_cuda"]
        self._write("C", original)
        with self.assertRaisesRegex(compare.CaptureValidationError, "missing precision flags"):
            self._compare()

    def test_missing_data_reordered_layers_and_device_fallback_are_rejected(self):
        original = self._read("C")
        mutations = (
            (lambda item: item["tensors"].pop("small_reference/logits_formal"), "missing tensors"),
            (lambda item: item["layer_order"].reverse(), "layer order"),
            (lambda item: item.update(device="CPU"), "fallback forbidden"),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                changed = json.loads(json.dumps(original))
                mutate(changed)
                self._write("C", changed)
                with self.assertRaisesRegex(compare.CaptureValidationError, message):
                    self._compare()

    def test_tensor_path_traversal_and_dtype_casting_are_rejected(self):
        original = self._read("C")
        changed = json.loads(json.dumps(original))
        changed["tensors"]["baseline/conv1"]["file"] = "../outside.npy"
        self._write("C", changed)
        with self.assertRaisesRegex(compare.CaptureValidationError, "without traversal"):
            self._compare()
        self._write("C", original)
        self._replace_tensor("C", "baseline/conv1", np.array([0.2, -0.2], dtype=np.float64))
        with self.assertRaisesRegex(compare.CaptureValidationError, "float32 capture required"):
            self._compare()

    def test_preprocessing_difference_blocks_neural_backend_attribution(self):
        changed = np.full((3, 2, 2), 0.5001, dtype=np.float32)
        self._replace_tensor("B", "preprocessing/tensor", changed)
        self._replace_tensor("B", "baseline/input", changed)
        result, _ = self._compare()
        self.assertFalse(result["pairs"]["A_vs_B"]["neural_backend_attribution_supported_by_equal_input"])
        self.assertFalse(result["interpretation"]["model_input_tensors_exactly_equal_all_pairs"])
        self.assertIn("preprocessing/library", result["interpretation"]["next_investigation"])

    def test_batch_size_and_repeatability_effects_are_reported(self):
        self._replace_tensor("C", "position_691_batch32/probability", np.array([0.599, 0.401], dtype=np.float32))
        repeats = np.array([[0.6, 0.4], [0.6, 0.4], [0.599, 0.401]], dtype=np.float32)
        self._replace_tensor("C", "repeatability/position_691_formal", repeats)
        result, _ = self._compare()
        diagnostics = result["batch_size_and_repeatability"]["C"]
        self.assertFalse(diagnostics["position_691_batch1_vs_formal"]["positive_probability"]["compatible_at_frozen_tolerance"])
        self.assertFalse(diagnostics["repeatability"]["position_691_formal"]["compatible_at_frozen_tolerance"])
        self.assertFalse(result["d10_pass_asserted"])

    def test_position_mapping_and_unapproved_gpu_are_rejected(self):
        original = self._read("C")
        changed = json.loads(json.dumps(original))
        changed["small_reference_positions"][19]["x"] = 136
        self._write("C", changed)
        with self.assertRaisesRegex(compare.CaptureValidationError, "coordinates mismatch"):
            self._compare()
        original["environment"]["gpu_model"] = "NVIDIA GeForce RTX 4090"
        self._write("C", original)
        with self.assertRaisesRegex(compare.CaptureValidationError, "substitution is not authorized"):
            self._compare()

    def test_truncated_or_reordered_small_reference_is_rejected(self):
        original = self._read("C")
        changed = json.loads(json.dumps(original))
        changed["small_reference_positions"] = changed["small_reference_positions"][:-1]
        self._write("C", changed)
        with self.assertRaisesRegex(compare.CaptureValidationError, "approved 68 reference positions"):
            self._compare()
        original["small_reference_positions"][0:2] = reversed(original["small_reference_positions"][0:2])
        self._write("C", original)
        with self.assertRaisesRegex(compare.CaptureValidationError, "approved 68 reference positions"):
            self._compare()

    def test_cli_writes_only_diagnostic_outputs(self):
        output = self.root / "output"
        with contextlib.redirect_stdout(io.StringIO()):
            compare.main(["compare", "--lane-a", str(self.paths["A"]), "--lane-b", str(self.paths["B"]),
                          "--lane-c", str(self.paths["C"]), "--out-dir", str(output)])
        self.assertEqual({item.name for item in output.iterdir()}, {"three_way_comparison.json", "layerwise_comparison_gpu.json"})
        result = json.loads((output / "three_way_comparison.json").read_text())
        self.assertFalse(result["d10_pass_asserted"])
        self.assertEqual(result["frozen_tolerance"], 0.0001)
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        for artifact in output.iterdir():
            self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
        original = (output / "three_way_comparison.json").read_bytes()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            compare.main(["compare", "--lane-a", str(self.paths["A"]), "--lane-b", str(self.paths["B"]),
                          "--lane-c", str(self.paths["C"]), "--out-dir", str(output)])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual((output / "three_way_comparison.json").read_bytes(), original)

    def test_same_model_different_node_or_unrecorded_node_is_rejected(self):
        original = self._read("C")
        changed = json.loads(json.dumps(original))
        changed["environment"]["node_fingerprint"] = "4" * 64
        self._write("C", changed)
        with self.assertRaisesRegex(compare.CaptureValidationError, "environment differs beyond device"):
            self._compare()
        del original["environment"]["node_fingerprint"]
        self._write("C", original)
        with self.assertRaisesRegex(compare.CaptureValidationError, "hashed node_fingerprint required"):
            self._compare()

    def test_nested_checkpoint_is_optional_but_must_match_when_present(self):
        metadata = self._read("A")
        del metadata["model_identity"]["checkpoint_sha256"]
        self._write("A", metadata)
        result, _ = self._compare()
        self.assertFalse(result["d10_pass_asserted"])
        metadata["model_identity"]["checkpoint_sha256"] = "0" * 64
        self._write("A", metadata)
        with self.assertRaisesRegex(compare.CaptureValidationError, "model checkpoint differs"):
            self._compare()


if __name__ == "__main__":
    unittest.main()
