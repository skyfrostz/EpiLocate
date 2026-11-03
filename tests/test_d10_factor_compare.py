"""Contract tests for controlled D10 CUDA factor comparisons; no GPU is used."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.research import d10_factor_compare as factor
from scripts.research import d10_three_way_compare as numerical
from tests import test_d10_three_way_compare as capture_fixtures


class FactorComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.baseline = self.root / "C"
        capture_fixtures.ThreeWayComparisonTests()._make_capture(self.baseline, "C")
        metadata = self._read(self.baseline)
        metadata.update(
            mode="baseline", run_id=factor.BASELINE_RUN_ID, status="CAPTURED_NOT_D10_PASS",
            base_sha="ebf6e8260b775e67857c3bd83a213fe0fecac8ff", audit_script_sha256="7" * 64,
            baseline_capture_sha256=None, factor_capture_sha256=[], factor_attempt_status=[], seed=None,
            environment_before_adjustment=copy.deepcopy(metadata["environment"]),
            position_691={"index": 691, "scale": 16, "x": 128, "y": 200},
            formal_batch_size=32, mask_fill=0.5, grid_counts={"16": 729, "32": 169, "64": 36},
            probability_computation_device="CPU (frozen infer_logits behavior)", frozen_tolerance=0.0001,
        )
        self._write(self.baseline, metadata)

    def _read(self, directory):
        return json.loads((directory / "capture.json").read_text())

    def _write(self, directory, metadata):
        (directory / "capture.json").write_text(json.dumps(metadata, sort_keys=True))

    def _make_factor(self, mode, suffix="", records=None):
        path = self.root / f"factor-{mode}{suffix}"
        shutil.copytree(self.baseline, path)
        metadata = self._read(path)
        metadata.update(mode=mode, run_id=f"RUN-D10-{mode.upper()}{suffix}",
                        baseline_capture_sha256=numerical.file_sha256(self.baseline / "capture.json"))
        before = copy.deepcopy(metadata["environment"])
        after = copy.deepcopy(before)
        flags = after["precision_flags"]
        if mode == "tf32-off":
            flags.update(cuda_matmul_allow_tf32=False, cudnn_allow_tf32=False)
            if before["precision_flags"]["cuda_matmul_allow_tf32"]:
                flags["float32_matmul_precision"] = "highest"
        elif mode == "deterministic-on":
            flags["torch_deterministic_algorithms"] = True
        elif mode == "benchmark-off":
            flags["cudnn_benchmark"] = False
        elif mode == "research":
            before["precision_flags"]["cublas_workspace_config"] = ":4096:8"
            flags.update(factor.RESEARCH_FLAGS)
            metadata["seed"] = factor.RESEARCH_SEED
            metadata["factor_capture_sha256"] = [numerical.file_sha256(record) for record in records or []]
            metadata["factor_attempt_status"] = [{"mode": json.loads(record.read_text())["mode"],
                                                "status": json.loads(record.read_text())["status"]}
                                               for record in records or []]
        metadata.update(environment_before_adjustment=before, environment=after)
        self._write(path, metadata)
        return path

    def _make_failure(self, mode="deterministic-on", incomplete=False):
        successful = self._make_factor(mode, "-failure-source")
        capture = self._read(successful)
        path = self.root / f"failed-{mode}"
        path.mkdir()
        failure = {
            "schema": "D10_ATTEMPT_V1", "lane": "C", "mode": mode, "run_id": f"RUN-D10-FAILED-{mode}",
            "status": "FAILED", "error_type": "RuntimeError", "error": "deterministic CUDA workspace requirement not satisfied",
            "traceback": "preserved failure traceback", "base_sha": capture["base_sha"],
            "audit_script_sha256": capture["audit_script_sha256"], "stage_b": "NOT_AUTHORIZED",
        }
        if not incomplete:
            failure.update(baseline_capture_sha256=capture["baseline_capture_sha256"],
                           input_sha256=capture["input_sha256"], checkpoint_sha256=capture["checkpoint_sha256"],
                           environment_before_adjustment=capture["environment_before_adjustment"],
                           effective_precision_flags=capture["environment"]["precision_flags"])
        (path / "failure.json").write_text(json.dumps(failure, sort_keys=True))
        return path / "failure.json"

    def _replace_tensor(self, directory, key, value):
        metadata = self._read(directory)
        tensor = metadata["tensors"][key]
        np.save(directory / tensor["file"], value)
        tensor.update(shape=list(value.shape), dtype=str(value.dtype), sha256=numerical.canonical_sha256(value))
        if "file_sha256" in tensor:
            tensor["file_sha256"] = numerical.file_sha256(directory / tensor["file"])
        self._write(directory, metadata)

    def test_tf32_matmul_precision_property_side_effect_is_recorded(self):
        baseline = self._read(self.baseline)
        baseline["environment"]["precision_flags"].update(cuda_matmul_allow_tf32=True, float32_matmul_precision="high")
        baseline["environment_before_adjustment"] = copy.deepcopy(baseline["environment"])
        self._write(self.baseline, baseline)
        variant = self._make_factor("tf32-off")
        result = factor.compare_factors(self.baseline, [variant])
        validation = result["attempts"][0]["configuration_validation"]
        self.assertTrue(validation["effective_flag_change_observed"])
        self.assertEqual(validation["related_property_deltas"][0]["field"], "precision_flags.float32_matmul_precision")
        self.assertEqual(validation["related_property_deltas"][0]["after"], "highest")
        self.assertFalse(result["d10_pass_asserted"])

    def test_noop_and_amp_explicit_scope_remain_visible(self):
        variants = [self._make_factor("benchmark-off"), self._make_factor("amp-off")]
        result = factor.compare_factors(self.baseline, variants)
        for row in result["attempts"]:
            self.assertFalse(row["configuration_validation"]["effective_flag_change_observed"])
            self.assertTrue(row["configuration_validation"]["baseline_already_had_requested_flags"])
            self.assertTrue(row["successful_capture"])
            self.assertIsNone(row.get("failure_evidence"))
        self.assertTrue(result["attempts"][1]["configuration_validation"]["explicit_amp_off_scope"])
        self.assertFalse(result["formal_cuda_research_authorized"])

    def test_unrelated_flags_node_and_dependency_changes_are_rejected(self):
        for field in ("precision_flags.cudnn_deterministic", "node_fingerprint", "torch"):
            with self.subTest(field=field):
                path = self._make_factor("tf32-off", field.replace(".", "-"))
                metadata = self._read(path)
                if field.startswith("precision_flags"):
                    metadata["environment"]["precision_flags"]["cudnn_deterministic"] = True
                else:
                    metadata["environment"][field] = "8" * 64 if field == "node_fingerprint" else "2.5.0+cu121"
                self._write(path, metadata)
                with self.assertRaisesRegex(numerical.CaptureValidationError, "unrelated environment changes"):
                    factor.compare_factors(self.baseline, [path])

    def test_factor_provenance_and_pre_adjustment_environment_must_match(self):
        variant = self._make_factor("deterministic-on")
        original = self._read(variant)
        changed = copy.deepcopy(original)
        changed["baseline_capture_sha256"] = "9" * 64
        self._write(variant, changed)
        with self.assertRaisesRegex(numerical.CaptureValidationError, "baseline_capture_sha256"):
            factor.compare_factors(self.baseline, [variant])
        original["environment_before_adjustment"]["numpy"] = "1.25.0"
        self._write(variant, original)
        with self.assertRaisesRegex(numerical.CaptureValidationError, "environment_before_adjustment"):
            factor.compare_factors(self.baseline, [variant])

    def test_source_config_and_model_identity_confounds_are_rejected(self):
        for name in ("source_sha256", "config_sha256", "model_identity"):
            with self.subTest(name=name):
                variant = self._make_factor("benchmark-off", name)
                metadata = self._read(variant)
                key = "state_dict_values_sha256" if name == "model_identity" else next(iter(metadata[name]))
                metadata[name][key] = "8" * 64
                self._write(variant, metadata)
                with self.assertRaisesRegex(numerical.CaptureValidationError, "mismatch"):
                    factor.compare_factors(self.baseline, [variant])

    def test_tensor_hash_tamper_prevents_any_output(self):
        variant = self._make_factor("amp-off")
        metadata = self._read(variant)
        path = variant / metadata["tensors"]["baseline/conv1"]["file"]
        np.save(path, np.array([8.0, 9.0], dtype=np.float32))
        output = self.root / "bad-output"
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            factor.main(["--baseline", str(self.baseline), "--factor", str(variant), "--out-dir", str(output)])
        self.assertEqual(caught.exception.code, 2)
        self.assertFalse(output.exists())

    def test_preprocessing_and_batch_geometry_are_required_to_stay_equal(self):
        variant = self._make_factor("deterministic-on")
        changed = np.full((3, 2, 2), 0.5001, dtype=np.float32)
        self._replace_tensor(variant, "preprocessing/tensor", changed)
        self._replace_tensor(variant, "baseline/input", changed)
        with self.assertRaisesRegex(numerical.CaptureValidationError, "input/preprocessing changed"):
            factor.compare_factors(self.baseline, [variant])
        variant2 = self._make_factor("deterministic-on", "-batch")
        metadata = self._read(variant2)
        metadata["formal_batch_size"] = 16
        self._write(variant2, metadata)
        with self.assertRaisesRegex(numerical.CaptureValidationError, "formal_batch_size mismatch"):
            factor.compare_factors(self.baseline, [variant2])

    def test_target_probability_logits_layers_batch_and_repeats_are_reported(self):
        variant = self._make_factor("tf32-off")
        self._replace_tensor(variant, "position_691_batch32/conv1", np.array([0.20001, -0.2], dtype=np.float32))
        self._replace_tensor(variant, "position_691_batch32/layer1.0", np.array([0.2002, -0.2], dtype=np.float32))
        for name in ("fc", "logits"):
            self._replace_tensor(variant, f"position_691_batch32/{name}", np.array([0.201, -0.2], dtype=np.float32))
        self._replace_tensor(variant, "position_691_batch32/probability", np.array([0.599, 0.401], dtype=np.float32))
        self._replace_tensor(variant, "repeatability/position_691_formal",
                             np.array([[0.6, 0.4], [0.6, 0.4], [0.599, 0.401]], dtype=np.float32))
        result = factor.compare_factors(self.baseline, [variant])
        numeric = result["attempts"][0]["numeric_comparison"]
        self.assertEqual(numeric["layerwise"]["position_691_batch32"]["first_nonzero_divergence"], "conv1")
        self.assertEqual(numeric["layerwise"]["position_691_batch32"]["first_threshold_exceeding_divergence"], "layer1.0")
        self.assertIsNone(numeric["layerwise"]["position_691_batch32"]["first_major_amplification"])
        target = numeric["position_691"]["samples"]["position_691_batch32"]
        self.assertGreater(target["logit_delta"]["max_abs_diff"], 0.0009)
        self.assertGreater(target["positive_probability_delta"]["max_abs_diff"], 0.0009)
        self.assertFalse(numeric["variant_batch_size_and_repeatability"]["position_691_batch1_vs_formal"]["positive_probability"]["compatible_at_frozen_tolerance"])
        self.assertFalse(numeric["variant_batch_size_and_repeatability"]["repeatability"]["position_691_formal"]["compatible_at_frozen_tolerance"])
        self.assertFalse(result["d10_pass_asserted"])

    def test_adjusted_failure_is_preserved_as_failed_not_success(self):
        failed = self._make_failure()
        result = factor.compare_factors(self.baseline, [failed])
        row = result["attempts"][0]
        self.assertEqual(row["attempt_interpretation"], "TESTED_ATTEMPT_FAILED")
        self.assertFalse(row["successful_capture"])
        self.assertIsNone(row["numeric_comparison"])
        self.assertEqual(row["failure_evidence"]["traceback"], "preserved failure traceback")
        self.assertEqual(result["single_factor_coverage"]["verified_tested_modes"], ["deterministic-on"])

    def test_incomplete_failure_has_no_adjusted_or_numerical_claim(self):
        failed = self._make_failure(incomplete=True)
        result = factor.compare_factors(self.baseline, [failed])
        row = result["attempts"][0]
        self.assertEqual(row["attempt_interpretation"], "INCOMPLETE_ATTEMPT_FAILED")
        self.assertFalse(row["configuration_validation"]["adjusted_attempt_verified"])
        self.assertFalse(row["configuration_validation"]["baseline_provenance_verified"])
        self.assertEqual(result["single_factor_coverage"]["verified_tested_modes"], [])

    def test_failed_attempt_confounds_are_rejected(self):
        failed = self._make_failure()
        metadata = json.loads(failed.read_text())
        metadata["effective_precision_flags"]["cudnn_deterministic"] = True
        failed.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(numerical.CaptureValidationError, "unrelated environment changes"):
            factor.compare_factors(self.baseline, [failed])

    def test_failed_research_preserves_unknown_seed_and_factor_provenance(self):
        failed = self._make_failure("research")
        result = factor.compare_factors(self.baseline, [failed])
        row = result["attempts"][0]
        self.assertEqual(row["comparison_kind"], "DISCLOSED_COMBINED_RESEARCH_CONFIGURATION")
        self.assertFalse(row["successful_capture"])
        self.assertIsNone(row["numeric_comparison"])
        self.assertFalse(row["combined_research_provenance"]["seed_provenance_verified"])
        self.assertFalse(row["combined_research_provenance"]["configuration_fully_documented"])
        self.assertFalse(result["d10_pass_asserted"])

    def test_failed_and_successful_retries_both_remain_visible(self):
        failed = self._make_failure()
        retry = self._make_factor("deterministic-on", "-retry")
        result = factor.compare_factors(self.baseline, [failed, retry])
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual([row["successful_capture"] for row in result["attempts"]], [False, True])

    def _research_records(self):
        records = []
        for mode in factor.SINGLE_FACTORS:
            records.append(self._make_failure(mode) if mode == "deterministic-on" else self._make_factor(mode) / "capture.json")
        research = self._make_factor("research", records=records)
        return records, research

    def test_research_combination_checks_seed_flags_and_failed_attempt_provenance(self):
        records, research = self._research_records()
        result = factor.compare_factors(self.baseline, [*records, research])
        row = result["attempts"][-1]
        self.assertEqual(row["comparison_kind"], "DISCLOSED_COMBINED_RESEARCH_CONFIGURATION")
        self.assertEqual(row["documented_seed"], 20260925)
        provenance = row["combined_research_provenance"]
        self.assertTrue(provenance["single_factor_provenance_verified"])
        self.assertEqual(sum(item["successful_capture"] for item in provenance["factor_attempts"]), 3)
        self.assertFalse(result["d10_pass_asserted"])

    def test_research_requires_exact_provenance_and_cannot_change_seed_or_flags(self):
        records, research = self._research_records()
        original = self._read(research)
        for field, value, message in (("seed", 42, "seed differs"),
                                      ("factor_capture_sha256", ["9" * 64] * 4, "four distinct")):
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed[field] = value
                self._write(research, changed)
                with self.assertRaisesRegex(numerical.CaptureValidationError, message):
                    factor.compare_factors(self.baseline, [*records, research])
        changed = copy.deepcopy(original)
        changed["environment"]["precision_flags"]["cudnn_deterministic"] = False
        self._write(research, changed)
        with self.assertRaisesRegex(numerical.CaptureValidationError, "research flag cudnn_deterministic"):
            factor.compare_factors(self.baseline, [*records, research])
        self._write(research, original)
        with self.assertRaisesRegex(numerical.CaptureValidationError, "missing single-factor attempt"):
            factor.compare_factors(self.baseline, [research])

    def test_incomplete_failed_factor_cannot_support_research_provenance(self):
        records = [self._make_failure(mode, incomplete=True) if mode == "deterministic-on"
                   else self._make_factor(mode) / "capture.json" for mode in factor.SINGLE_FACTORS]
        research = self._make_factor("research", records=records)
        with self.assertRaisesRegex(numerical.CaptureValidationError, "incomplete, unverified"):
            factor.compare_factors(self.baseline, [*records, research])

    def test_research_factor_statuses_must_match_preserved_failures(self):
        records, research = self._research_records()
        metadata = self._read(research)
        metadata["factor_attempt_status"][1]["status"] = "CAPTURED_NOT_D10_PASS"
        self._write(research, metadata)
        with self.assertRaisesRegex(numerical.CaptureValidationError, "statuses differ"):
            factor.compare_factors(self.baseline, [*records, research])

    def test_immutable_private_cli_output_and_no_duplicate_records(self):
        variant = self._make_factor("amp-off")
        output = self.root / "output"
        arguments = ["--baseline", str(self.baseline), "--factor", str(variant), "--out-dir", str(output)]
        with contextlib.redirect_stdout(io.StringIO()):
            factor.main(arguments)
        artifact = output / "factor_isolation_matrix.json"
        before = artifact.read_bytes()
        self.assertEqual({path.name for path in output.iterdir()}, {"factor_isolation_matrix.json"})
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            factor.main(arguments)
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(artifact.read_bytes(), before)
        with self.assertRaisesRegex(numerical.CaptureValidationError, "duplicate factor record"):
            factor.compare_factors(self.baseline, [variant, variant])

    def test_wrong_baseline_run_id_or_adjusted_baseline_is_rejected(self):
        variant = self._make_factor("amp-off")
        original = self._read(self.baseline)
        changed = copy.deepcopy(original)
        changed["run_id"] = "RUN-D10-OTHER"
        self._write(self.baseline, changed)
        with self.assertRaisesRegex(numerical.CaptureValidationError, "unadjusted RUN-D10-CUDA-BASELINE"):
            factor.compare_factors(self.baseline, [variant])
        original["seed"] = factor.RESEARCH_SEED
        self._write(self.baseline, original)
        with self.assertRaisesRegex(numerical.CaptureValidationError, "must not use a research seed"):
            factor.compare_factors(self.baseline, [variant])


if __name__ == "__main__":
    unittest.main()
