"""Local release inspection and immutable opt-in algorithm selection.

Flags are sidecar configuration, never a mutation of Backend/Worker protocols.
No hospital approval, data allowlist, submission or model run is created here.
"""
import argparse
import hashlib
import json
from pathlib import Path

from .artifacts import canonical_json, sha256
from .contracts import require_hash
from .hospital_contract import ALGORITHMS, SPATIAL_CHECKS
from .hospital_contract import validate_result


LEGACY = ("FrozenBaseline", "Occlusion16", "Occlusion32", "Occlusion64")
ACCEPTANCE_CHECKS = ("deidentified_ct_display", "model_traceability", "native_overlay",
                     "save_refresh_recovery", "clear_failure_states", "legacy_rollback")


def verify_reference(reference, root):
    """References resolve within the versioned release root, never via URLs."""
    require_hash(reference["sha256"], "evidence SHA")
    root = Path(root).resolve()
    relative = Path(reference["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("release-local evidence reference required")
    path = root / relative
    if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
        raise ValueError("symlink evidence is unsupported")
    if root not in path.resolve().parents or not path.is_file():
        raise ValueError("missing release evidence")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != reference["sha256"]:
        raise ValueError("evidence SHA mismatch")
    return path


def acceptance_gate(manifest, algorithm, root):
    """All real evidence must bind the exact same frozen release identity.

    Report statements are trusted human acceptance inputs; hashing them alone
    does not prove that a medical image was correct or clinically valid.
    """
    failures = []
    if manifest.get("schema") != "EPI-NEXT-HOSPITAL-RELEASE-1":
        return ["UNSUPPORTED_MANIFEST"]
    entry = manifest.get("algorithms", {}).get(algorithm)
    if not entry or algorithm not in ALGORITHMS:
        return ["UNKNOWN_ALGORITHM"]
    if entry.get("algorithm_version") != ALGORITHMS[algorithm]["version"]:
        failures.append("UNREGISTERED_ALGORITHM_VERSION")
    if entry.get("status") != "ENGINEERING_ACCEPTED":
        failures.append("ALGORITHM_NOT_ACCEPTED")
    identity = {"source_git_sha": manifest["source_git_sha"], "algorithm_id": algorithm,
                "algorithm_version": entry["algorithm_version"], "model_sha256": entry["model_sha256"],
                "preprocessing_sha256": entry["preprocessing_sha256"],
                "algorithm_config_sha256": entry.get("algorithm_config_sha256"),
                "resource_budget_sha256": entry.get("resource_budget_sha256"),
                "task_definition_sha256": manifest.get("task_definition_sha256"),
                "data_handoff_sha256": manifest.get("data_handoff_sha256")}
    for key, digest in identity.items():
        if key.endswith("sha256") or key == "source_git_sha":
            try:
                require_hash(digest, key, 40 if key == "source_git_sha" else 64)
            except ValueError:
                failures.append("MISSING_IDENTITY:" + key)
    if manifest.get("real_e2e_status") != "PASS":
        failures.append("BLOCKED_BY_DATA_HANDOFF_OR_REAL_E2E")
    acceptance = entry.get("acceptance", {})
    refs = {key: acceptance.get(key) for key in ACCEPTANCE_CHECKS}
    refs.update({"spatial:" + key: acceptance.get("spatial_checks", {}).get(key) for key in SPATIAL_CHECKS})
    for key, reference in refs.items():
        try:
            report = json.loads(verify_reference(reference, root).read_bytes())
            if (report.get("source") != "LIVE_CASE" or report.get("status") != "PASS"
                    or report.get("identity") != identity or report.get("check") != key):
                raise ValueError("acceptance identity/source/check mismatch")
        except (OSError, ValueError, KeyError, TypeError):
            failures.append("MISSING_OR_INVALID_EVIDENCE:" + key)
    runs = acceptance.get("consecutive_demo_runs", [])
    if not isinstance(runs, list) or len(runs) < 3:
        failures.append("THREE_CONSECUTIVE_REAL_RUNS_REQUIRED")
    else:
        observed_runs = []
        for reference in runs[-3:]:
            try:
                report = json.loads(verify_reference(reference, root).read_bytes())
                if (report.get("source") != "LIVE_CASE" or report.get("identity") != identity
                        or report.get("status") != "PASS" or report.get("blocking_faults") != 0
                        or any(report.get("checks", {}).get(k) != "PASS" for k in ACCEPTANCE_CHECKS)
                        or type(report.get("sequence")) is not int or not report.get("workflow_run_id")):
                    raise ValueError("real workflow acceptance incomplete")
                observed_runs.append(report)
            except (OSError, ValueError, KeyError, TypeError):
                failures.append("INVALID_REAL_DEMO_RUN")
        if len(observed_runs) == 3 and (
                len({r["workflow_run_id"] for r in observed_runs}) != 3
                or [r["sequence"] for r in observed_runs] != list(range(observed_runs[0]["sequence"], observed_runs[0]["sequence"] + 3))):
            failures.append("DEMO_RUNS_MUST_BE_DISTINCT_AND_CONSECUTIVE")
    for key in ("precomputed_result", "backup_recording", "rollback_receipt"):
        try:
            path = verify_reference(acceptance.get(key), root)
            if key != "backup_recording":
                report = json.loads(path.read_bytes())
                if report.get("identity") != identity or report.get("source") != "LIVE_CASE":
                    raise ValueError("fallback identity mismatch")
                if key == "precomputed_result":
                    if report.get("schema") != "EPI-NEXT-HOSPITAL-PRECOMPUTED-1" or report.get("status") != "PASS":
                        raise ValueError("precomputed result receipt required")
                    request = json.loads(verify_reference(report["request_reference"], root).read_bytes())
                    result = json.loads(verify_reference(report["result_reference"], root).read_bytes())
                    validate_result(request, result)
                    if (request["source"] != "LIVE_CASE" or result["status"] not in {"SUCCESS", "NO_RELIABLE_RESPONSE"}
                            or any(request.get(k) != v for k,v in identity.items() if k not in {"data_handoff_sha256", "resource_budget_sha256", "task_definition_sha256"})
                            or sha256(canonical_json(request["resource_budget"])) != identity["resource_budget_sha256"]
                            or request["task"]["definition_sha256"] != identity["task_definition_sha256"]
                            or request.get("access_approval_sha256") != identity["data_handoff_sha256"]):
                        raise ValueError("precomputed identity or status mismatch")
                    for asset in result["artifacts"]:
                        verify_reference({"path": str(Path(report["result_reference"]["path"]).parent / asset["path"]),
                                          "sha256": asset["sha256"]}, root)
                elif report.get("status") != "PASS" or report.get("fallback_algorithm") not in LEGACY:
                    raise ValueError("passed exact legacy rollback receipt required")
            else:
                with path.open("rb") as stream:
                    raw = stream.read(32)
                valid_container = ((path.suffix.lower() in {".mp4", ".mov"} and raw[4:8] == b"ftyp")
                                   or (path.suffix.lower() == ".webm" and raw[:4] == b"\x1a\x45\xdf\xa3"))
                if not valid_container or path.stat().st_size < 32:
                    raise ValueError("recording container invalid")
                review = json.loads(verify_reference(acceptance["backup_recording_review"], root).read_bytes())
                if (review.get("identity") != identity or review.get("status") != "PASS"
                        or review.get("recording_sha256") != acceptance[key]["sha256"]
                        or review.get("playback_verified") is not True):
                    raise ValueError("actual recording playback review required")
        except (OSError, ValueError, KeyError, TypeError):
            failures.append("MISSING_OR_INVALID_EVIDENCE:" + key)
    return failures


def select_algorithm(manifest, algorithm, release_root, output):
    if algorithm not in (*LEGACY, *ALGORITHMS):
        raise ValueError("unknown algorithm flag")
    if algorithm in ALGORITHMS:
        failures = acceptance_gate(manifest, algorithm, release_root)
        if failures:
            raise RuntimeError("HOSPITAL_SELECTION_BLOCKED: " + ", ".join(failures))
    flag = {"schema": "EPI-NEXT-HOSPITAL-FLAG-1", "selected_algorithm": algorithm,
            "release_manifest_sha256": sha256(canonical_json(manifest)),
            "mode": "LEGACY_ROLLBACK" if algorithm in LEGACY else "ACCEPTED_LOCAL_SIDECAR",
            "hospital_approval": "REQUIRES_PROJECT_OWNER_DECISION", "clinical_validation": "NOT RUN"}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(canonical_json(flag))
    return flag


def dispatch_selected(request, manifest, release_root, output_root, *, flag=None,
                      runtime=None, legacy_runner=None):
    """Minimal callable integration seam; legacy protocol stays byte-for-byte.

    With no sidecar flag, call the existing legacy handler. This is NOT an
    installed Backend route; wiring is deferred until formal accepted handoff.
    """
    algorithm = "FrozenBaseline" if flag is None else flag.get("selected_algorithm")
    if flag is not None and (flag.get("schema") != "EPI-NEXT-HOSPITAL-FLAG-1"
                            or flag.get("release_manifest_sha256") != sha256(canonical_json(manifest))):
        raise ValueError("flag/release manifest mismatch")
    if algorithm in LEGACY:
        if legacy_runner is None:
            return {"status": "NOT RUN", "reason": "LEGACY_HANDLER_NOT_BOUND", "algorithm_id": algorithm}
        return legacy_runner(algorithm, request)
    if algorithm not in ALGORITHMS or request.get("algorithm_id") != algorithm:
        raise ValueError("selected algorithm/request mismatch")
    failures = acceptance_gate(manifest, algorithm, release_root)
    if failures:
        raise RuntimeError("HOSPITAL_SELECTION_BLOCKED: " + ", ".join(failures))
    entry = manifest["algorithms"][algorithm]
    for key in ("source_git_sha", "model_sha256", "preprocessing_sha256", "algorithm_version"):
        expected = manifest[key] if key == "source_git_sha" else entry[key]
        if request.get(key) != expected:
            raise ValueError("request differs from accepted release identity")
    if (request.get("algorithm_config_sha256") != entry["algorithm_config_sha256"]
            or sha256(canonical_json(request["resource_budget"])) != entry["resource_budget_sha256"]
            or request["task"]["definition_sha256"] != manifest["task_definition_sha256"]):
        raise ValueError("request config/budget/task differs from accepted release")
    from .hospital_runtime import execute_registered
    return execute_registered(request, runtime, output_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--algorithm", choices=[*LEGACY, *ALGORITHMS])
    parser.add_argument("--output-flag", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_bytes())
    if args.output_flag:
        if not args.algorithm:
            parser.error("--algorithm required for a switch")
        print(json.dumps(select_algorithm(manifest, args.algorithm, args.manifest.parent, args.output_flag), indent=2))
    else:
        for name, entry in manifest["algorithms"].items():
            print(json.dumps({"algorithm": name, "version": entry["algorithm_version"],
                              "status": entry["status"], "evidence_type": entry["evidence_type"],
                              "admission_failures": acceptance_gate(manifest, name, args.manifest.parent)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
