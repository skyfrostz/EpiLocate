"""Read-only SHA-256 audit of the Stage 1 validation freeze; never opens test pixels."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.frozen_root.resolve()
    freeze_path = root / "outputs/experiments/FORMAL-BL-R18-V1/occlusion_stage1/validation/result_freeze.json"
    report: dict = {"audit": "metadata-and-artifact-hashes-only", "frozen_root_available": freeze_path.is_file()}
    if not freeze_path.is_file():
        report["status"] = "BLOCKED"
    else:
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        expected = freeze["artifact_sha256"]
        allowed = (root / "outputs/experiments/FORMAL-BL-R18-V1/occlusion_stage1/validation").resolve()
        mismatches = []
        for relative, expected_sha in expected.items():
            path = (root / relative).resolve()
            if not path.is_relative_to(allowed) or not path.is_file() or digest(path) != expected_sha:
                mismatches.append(relative)
        fixed_files = {
            "protocol_sha256": root / "docs/occlusion_instability_protocol_v1.md",
            "config_sha256": root / "configs/occlusion_instability_v1.yaml",
            "checkpoint_sha256": root / "outputs/experiments/FORMAL-BL-R18-V1/training/best_model.pth",
        }
        fixed_checks = {name: path.is_file() and digest(path) == freeze[name] for name, path in fixed_files.items()}
        report.update({
            "status": "PASS" if freeze["status"] == "FROZEN" and len(expected) == 161 and not mismatches and all(fixed_checks.values()) else "FAIL",
            "freeze_sha256": digest(freeze_path),
            "manifest_in_artifacts": "outputs/experiments/FORMAL-BL-R18-V1/occlusion_stage1/validation/run_manifest.json" in expected,
            "expected_artifact_count": len(expected),
            "artifact_mismatches": mismatches,
            "fixed_input_checks": fixed_checks,
            "recorded_independent_qa_status": freeze.get("independent_qa_status"),
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
