"""Boundary tests for the full frozen runner; benchmark execution is mocked."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np  # Keep extension modules loaded while sys.modules is isolated.

from scripts.research import d10_frozen_bundle_retest as retest


class FakeTorch:
    __version__ = "2.4.0+cu121"

    def __init__(self):
        self.version = SimpleNamespace(cuda="12.1")
        self.backends = SimpleNamespace(
            cuda=SimpleNamespace(matmul=SimpleNamespace(allow_tf32=False)),
            cudnn=SimpleNamespace(allow_tf32=True, benchmark=False, deterministic=False, version=lambda: 90100),
        )
        self.cuda = SimpleNamespace(is_available=lambda: True, manual_seed_all=mock.Mock())
        self.deterministic = False
        self.precision = "highest"
        self.manual_seed = mock.Mock()

    def use_deterministic_algorithms(self, enabled):
        self.deterministic = enabled

    def are_deterministic_algorithms_enabled(self):
        return self.deterministic

    def set_float32_matmul_precision(self, value):
        self.precision = value

    def get_float32_matmul_precision(self):
        return self.precision

    def is_autocast_enabled(self, device):
        return False

    def autocast(self, device_type, enabled):
        return contextlib.nullcontext()


class FrozenBundleRetestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / "package"
        self.package.mkdir()
        for relative in retest.ALLOWED_FILES:
            path = self.package / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"unit-test-only:" + relative.encode())
        self.input_sha = retest.sha256(self.package / "implementation/docs/interfaces/fixtures/p0_synthetic_ct.dcm")
        self.model_sha = retest.sha256(self.package / "frozen/outputs/experiments/FORMAL-BL-R18-V1/training/best_model.pth")
        self.config_sha = {"baseline": retest.sha256(self.package / "frozen/configs/formal_baseline_rule_b_v1.yaml"),
                           "protocol": retest.sha256(self.package / "frozen/docs/occlusion_instability_protocol_v1.md"),
                           "stage": retest.sha256(self.package / "frozen/configs/occlusion_instability_v1.yaml")}
        self.implementation_sha = {name: retest.sha256(self.package / ("implementation/" + name))
                                   for name in retest.IMPLEMENTATION_SHA256}
        reference = {"schema": "D10_REFERENCE_V1", "fixture": {"sha256": self.input_sha},
                     "checkpoint_sha256": self.model_sha, "frozen_config_sha256": self.config_sha,
                     "implementation_sha256": {name: self.implementation_sha[name] for name in (
                         "algorithm/service.py", "scripts/occlusion_runner.py", "src/model.py", "src/preprocessing.py")}}
        (self.package / "reference/d10_reference_manifest.json").write_text(json.dumps(reference))
        self.approved_sha = {relative: retest.sha256(self.package / relative) for relative in retest.EXPECTED_FILE_SHA256}
        self.manifest = {"schema": "D10_EXECUTION_PACKAGE_V1", "base_sha": retest.FROZEN_REFERENCE_LINEAGE_SHA,
                         "stage_b": "NOT_AUTHORIZED", "allowed_files": {
                             relative: {"sha256": retest.sha256(self.package / relative),
                                        "bytes": (self.package / relative).stat().st_size} for relative in retest.ALLOWED_FILES}}
        self._write_package_manifest()
        for name, value in (("EXPECTED_FILE_SHA256", self.approved_sha), ("INPUT_SHA256", self.input_sha),
                            ("CHECKPOINT_SHA256", self.model_sha), ("CONFIG_SHA256", self.config_sha),
                            ("IMPLEMENTATION_SHA256", self.implementation_sha)):
            patch = mock.patch.object(retest, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.formal = self.root / "formal-runtime.json"
        self.formal_data = {"schema": "FORMAL_CUDA_RESEARCH_RUNTIME_V1", "torch": "2.4.0+cu121",
                            "cuda_runtime": "12.1", "seed": 20260925,
                            "precision_flags": copy.deepcopy(retest.RESEARCH_FLAGS),
                            "gpu_model": "NVIDIA GeForce RTX 3090", "os": "Linux-test",
                            "node_fingerprint": "4" * 64,
                            "source_package_manifest_sha256": retest.sha256(self.package / "package_manifest.json")}
        self.formal.write_text(json.dumps(self.formal_data))
        self.torch = FakeTorch()

    def _write_package_manifest(self):
        (self.package / "package_manifest.json").write_text(json.dumps(self.manifest))

    def _environment(self, torch, device):
        return {"os": "Linux-test", "python": "3.11.15", "torch": str(torch.__version__), "torchvision": "0.19.0",
                "numpy": "1.26.4", "pydicom": "3.0.1", "cuda_runtime": torch.version.cuda,
                "gpu_model": "NVIDIA GeForce RTX 3090", "gpu_compute_capability": [8, 6], "driver": "550.1",
                "cudnn_version": 90100, "node_fingerprint": "4" * 64, "device": device,
                "precision_flags": retest.precision_flags(torch)}

    def _benchmark_outputs(self, device="CUDA"):
        positions = []
        for scale in (16, 32, 64):
            for y in range(0, 224 - scale + 1, scale // 2):
                for x in range(0, 224 - scale + 1, scale // 2):
                    positions.append({"block_size": scale, "x": x, "y": y})
        benchmark = {"requested_device": device, "actual_device": device, "input_sha256": self.input_sha,
                     "model_hash": self.model_sha, "torch_version": "2.4.0+cu121", "torch_cuda_runtime": "12.1",
                     "position_count_by_scale": {"16": 729, "32": 169, "64": 36}}
        bundle = {"device": device, "input_sha256": self.input_sha, "model_hash": self.model_sha,
                  "result": {"positions": positions}, "assets": {}}
        return benchmark, bundle

    @contextlib.contextmanager
    def _mock_execution(self, outputs=None):
        benchmark = SimpleNamespace(run_benchmark=mock.Mock(return_value=outputs or self._benchmark_outputs()))
        with mock.patch.dict(sys.modules), mock.patch.dict(os.environ), mock.patch.object(sys, "dont_write_bytecode"), \
             mock.patch.object(retest, "_import_torch", return_value=self.torch) as import_torch, \
             mock.patch.object(retest, "runtime_environment", side_effect=self._environment), \
             mock.patch.object(retest, "_import_benchmark", return_value=benchmark), \
             mock.patch.object(retest, "verify_loaded_sources"):
            sys.modules.pop("torch", None)
            yield benchmark, import_torch

    def test_package_verifies_exact_22_files_without_torch_import(self):
        with mock.patch.object(retest, "_import_torch") as import_torch:
            verified = retest.verify_package(self.package)
        self.assertEqual(len(verified["file_sha256"]), 22)
        import_torch.assert_not_called()

    def test_tampered_frozen_file_even_with_updated_manifest_is_rejected(self):
        relative = "implementation/worker/benchmark.py"
        path = self.package / relative
        path.write_bytes(b"changed benchmark mathematics")
        self.manifest["allowed_files"][relative] = {"sha256": retest.sha256(path), "bytes": path.stat().st_size}
        self._write_package_manifest()
        with self.assertRaisesRegex(retest.RetestValidationError, "pinned frozen/source/reference SHA mismatch"):
            retest.verify_package(self.package)

    def test_unhashed_changes_missing_and_extra_allowlist_entries_are_rejected(self):
        original = copy.deepcopy(self.manifest)
        for modification in ("tamper", "missing", "traversal"):
            with self.subTest(modification=modification):
                self.manifest = copy.deepcopy(original)
                if modification == "tamper":
                    self.manifest["allowed_files"]["implementation/worker/device.py"]["sha256"] = "0" * 64
                elif modification == "missing":
                    self.manifest["allowed_files"].pop("implementation/worker/device.py")
                else:
                    self.manifest["allowed_files"]["../outside"] = {"sha256": "0" * 64, "bytes": 1}
                self._write_package_manifest()
                with self.assertRaises(retest.RetestValidationError):
                    retest.verify_package(self.package)

    def test_symlinked_package_file_is_rejected(self):
        path = self.package / "implementation/worker/device.py"
        outside = self.root / "outside.py"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(retest.RetestValidationError, "regular package file required"):
            retest.verify_package(self.package)

    def test_manifest_requirement_and_invalid_flags_fail_before_torch_import_or_stdout(self):
        for missing in (True, False):
            with self.subTest(missing=missing):
                if not missing:
                    self.formal_data["precision_flags"]["cudnn_allow_tf32"] = True
                    self.formal.write_text(json.dumps(self.formal_data))
                output = self.root / f"failed-{missing}"
                stdout = io.StringIO()
                with mock.patch.object(retest, "_import_torch") as import_torch, contextlib.redirect_stdout(stdout), \
                     contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    args = ["--package-root", str(self.package), "--device", "CUDA", "--out-dir", str(output),
                            "--require-formal-runtime-manifest"]
                    if not missing:
                        args += ["--formal-runtime-manifest", str(self.formal)]
                    retest.main(args)
                import_torch.assert_not_called()
                self.assertEqual(stdout.getvalue(), "")
                failure = json.loads((output / "failure.json").read_text())
                self.assertEqual(failure["failed_phase"], "FORMAL_RUNTIME_MANIFEST_VERIFICATION")
                self.assertFalse(failure["d10_pass_asserted"])

    def test_runtime_manifest_source_package_identity_is_checked(self):
        self.formal_data["source_package_manifest_sha256"] = "9" * 64
        self.formal.write_text(json.dumps(self.formal_data))
        verified = retest.verify_package(self.package)
        with self.assertRaisesRegex(retest.RetestValidationError, "different source package"):
            retest.verify_formal_manifest(self.formal, verified, True)

    def test_workspace_set_before_import_and_benchmark_called_exactly_once(self):
        output = self.root / "full-success"
        with self._mock_execution() as (benchmark, import_torch):
            def import_after_workspace():
                self.assertEqual(os.environ["CUBLAS_WORKSPACE_CONFIG"], ":4096:8")
                return self.torch
            import_torch.side_effect = import_after_workspace
            result = retest.run_retest(self.package, "CUDA", output, self.formal, True)
        benchmark.run_benchmark.assert_called_once_with(self.package.resolve() / "frozen",
                                                        self.package.resolve() / "implementation/docs/interfaces/fixtures/p0_synthetic_ct.dcm", "CUDA")
        self.torch.manual_seed.assert_called_once_with(20260925)
        self.torch.cuda.manual_seed_all.assert_called_once_with(20260925)
        self.assertEqual(result["actual_environment_before_benchmark"]["precision_flags"], retest.RESEARCH_FLAGS)
        self.assertEqual(result["benchmark_invocation_count"], 1)
        self.assertEqual(result["occlusion_passes_per_invocation"], 2)
        self.assertEqual(result["execution_audit_base_sha"], "767d595658aed284181b8548c960aa9f8dbec60c")
        self.assertEqual(result["frozen_reference_lineage_sha"], "ebf6e8260b775e67857c3bd83a213fe0fecac8ff")
        self.assertFalse(result["d10_pass_asserted"])
        self.assertEqual({path.name for path in output.iterdir()}, {"benchmark.json", "bundle.json", "runtime_manifest.json"})
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        for path in output.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_cpu_formal_reference_uses_same_declared_linux_runtime(self):
        with self._mock_execution(self._benchmark_outputs("CPU")) as (benchmark, _):
            result = retest.run_retest(self.package, "CPU", self.root / "cpu-formal", self.formal, True)
        self.assertEqual(result["mode"], "FORMAL_RESEARCH_RUNTIME")
        self.assertEqual(result["actual_environment_before_benchmark"]["gpu_model"], "NVIDIA GeForce RTX 3090")
        benchmark.run_benchmark.assert_called_once()

    def test_wrong_hardware_torch_cuda_or_declared_node_is_rejected(self):
        actual = self._environment(self.torch, "CUDA")
        actual["precision_flags"] = retest.RESEARCH_FLAGS.copy()
        formal = {"manifest": self.formal_data}
        for name, value in (("gpu_model", "NVIDIA GeForce RTX 4090"), ("torch", "2.5.0+cu121"),
                            ("cuda_runtime", "12.4"), ("node_fingerprint", "5" * 64)):
            with self.subTest(name=name):
                changed = copy.deepcopy(actual)
                changed[name] = value
                with self.assertRaises(retest.RetestValidationError):
                    retest.validate_runtime(changed, formal, "CUDA")

    def test_benchmark_device_fallback_preserves_raw_outputs_and_failure(self):
        outputs = self._benchmark_outputs()
        outputs[0]["actual_device"] = "CPU"
        output = self.root / "fallback-failure"
        with self._mock_execution(outputs), self.assertRaisesRegex(retest.RetestValidationError, "fallback is forbidden"):
            retest.run_retest(self.package, "CUDA", output, self.formal, True)
        self.assertTrue((output / "benchmark.json").is_file())
        self.assertTrue((output / "bundle.json").is_file())
        failure = json.loads((output / "failure.json").read_text())
        self.assertEqual(failure["failed_phase"], "RESULT_VALIDATION")
        self.assertFalse(failure["d10_pass_asserted"])
        self.assertFalse((output / "runtime_manifest.json").exists())

    def test_full_grid_truncation_reordering_and_wrong_model_are_rejected(self):
        actual = self._environment(self.torch, "CUDA")
        for mutation in ("truncate", "order", "checkpoint"):
            with self.subTest(mutation=mutation):
                benchmark, bundle = self._benchmark_outputs()
                if mutation == "truncate":
                    bundle["result"]["positions"].pop()
                elif mutation == "order":
                    bundle["result"]["positions"][0:2] = reversed(bundle["result"]["positions"][0:2])
                else:
                    bundle["model_hash"] = "9" * 64
                with self.assertRaises(retest.RetestValidationError):
                    retest.validate_results(benchmark, bundle, "CUDA", actual)

    def test_existing_evidence_is_not_overwritten(self):
        output = self.root / "prior-evidence"
        output.mkdir()
        sentinel = output / "failure.json"
        sentinel.write_text("prior failure retained")
        with mock.patch.object(retest, "_import_torch") as import_torch, self.assertRaisesRegex(retest.RetestValidationError, "already exists"):
            retest.run_retest(self.package, "CUDA", output, self.formal, True)
        import_torch.assert_not_called()
        self.assertEqual(sentinel.read_text(), "prior failure retained")

    def test_torch_already_imported_requires_fresh_process(self):
        output = self.root / "not-fresh"
        with mock.patch.dict(sys.modules, {"torch": object()}), mock.patch.object(retest, "_import_torch") as import_torch, \
             self.assertRaisesRegex(retest.RetestValidationError, "fresh process"):
            retest.run_retest(self.package, "CUDA", output, self.formal, True)
        import_torch.assert_not_called()
        self.assertEqual(json.loads((output / "failure.json").read_text())["failed_phase"], "BEFORE_TORCH_IMPORT")

    def test_unadjusted_baseline_is_explicitly_diagnostic_and_preserves_flags(self):
        output = self.root / "default-diagnostic"
        with self._mock_execution() as (benchmark, _):
            result = retest.run_retest(self.package, "CUDA", output)
        self.assertEqual(result["mode"], "UNADJUSTED_DIAGNOSTIC_BASELINE")
        self.assertTrue(result["actual_environment_before_benchmark"]["precision_flags"]["cudnn_allow_tf32"])
        self.assertFalse(result["d10_pass_asserted"])
        self.torch.manual_seed.assert_not_called()
        benchmark.run_benchmark.assert_called_once()

    def test_loaded_frozen_module_from_other_tree_is_rejected(self):
        other = SimpleNamespace(__file__=str(self.root / "other/worker/benchmark.py"))
        with mock.patch.dict(sys.modules, {"worker.benchmark": other}), self.assertRaisesRegex(retest.RetestValidationError, "outside verified package"):
            retest.verify_loaded_sources(self.package / "implementation")


if __name__ == "__main__":
    unittest.main()
