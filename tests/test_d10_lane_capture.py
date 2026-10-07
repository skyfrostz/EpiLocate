"""Capture refuses unapproved input before importing any model implementation."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/research/d10_lane_capture.py"


class CaptureBoundaryTests(unittest.TestCase):
    def command(self, directory, output):
        fixture = directory / "unapproved.bin"
        fixture.write_bytes(b"not the frozen synthetic reference")
        manifest = directory / "reference.json"
        manifest.write_text(json.dumps({
            "fixture": {"sha256": "8e73851ac16215180f7a3e17d72c85814886fa25ef62fbfbc618686dc8df54ee"},
            "checkpoint_sha256": "548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734"}))
        return [sys.executable, str(SCRIPT), "--implementation-root", str(directory / "MUST_NOT_IMPORT"),
                "--frozen-root", str(directory / "MUST_NOT_READ"), "--fixture", str(fixture),
                "--reference-manifest", str(manifest), "--out-dir", str(output), "--lane", "A", "--run-id", "NEGATIVE-TEST"]

    def test_unapproved_input_stops_and_preserves_failed_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "evidence"
            result = subprocess.run(self.command(root, output), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            failure = json.loads((output / "failure.json").read_text())
            self.assertEqual(failure["status"], "FAILED")
            self.assertIn("fixture does not match", failure["error"])
            self.assertFalse((output / "capture.json").exists())
            self.assertFalse((output / "tensors").exists())
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertEqual((output / "failure.json").stat().st_mode & 0o777, 0o600)

    def test_existing_evidence_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "evidence"
            output.mkdir()
            sentinel = output / "capture.json"
            sentinel.write_bytes(b"immutable prior evidence")
            result = subprocess.run(self.command(root, output), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_bytes(), b"immutable prior evidence")
            self.assertFalse((output / "attempt.json").exists())


if __name__ == "__main__":
    unittest.main()
