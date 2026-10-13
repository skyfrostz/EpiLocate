#!/usr/bin/env python3
"""Single-command, serial CPU validation; optional real weights on synthetic input.

Choose a fresh output directory. Every command, exit code, log and file hash is
retained. No installs, GPU, networking, real patient input or application changes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--checkpoint-sha")
    parser.add_argument("--ctfm-weights", type=Path)
    parser.add_argument("--ctfm-sha")
    parser.add_argument("--ctfm-deps", type=Path)
    args = parser.parse_args()
    if bool(args.checkpoint) != bool(args.checkpoint_sha):
        parser.error("checkpoint and checkpoint-sha must be supplied together")
    if any([args.ctfm_weights, args.ctfm_sha, args.ctfm_deps]) and not all([args.ctfm_weights, args.ctfm_sha, args.ctfm_deps]):
        parser.error("ctfm-weights, ctfm-sha and ctfm-deps must be supplied together")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    module = Path(__file__).resolve().parent
    root = module.parents[1]
    env = dict(os.environ, PYTHONPATH=str(module), PYTHONDONTWRITEBYTECODE="1",
               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    jobs = [
        ("tests", ["-m", "pytest", str(module / "tests"), "-q", "-p", "no:cacheprovider"]),
        ("doctor", ["-m", "epi_next.cli", "doctor"]),
        ("data_eval", ["-m", "epi_next.data_eval", "--synthetic"]),
        ("encoder", ["-m", "epi_next.encoder_smoke", "--output", str(output / "encoder.json")]),
        ("localization", ["-m", "epi_next.localization_smoke", "--output", str(output / "localization.json")]),
        ("residual_f1", ["-m", "epi_next.residual_localization", "--output", str(output / "residual_f1.json")]),
    ]
    if args.checkpoint:
        jobs += [("baseline_e1_e2", ["-m", "epi_next.baseline_comparison_smoke", "--checkpoint",
                  str(args.checkpoint.resolve()), "--checkpoint-sha", args.checkpoint_sha,
                  "--output", str(output / "baseline_e1_e2.json")])]
    if args.ctfm_weights:
        jobs += [("ctfm_cpu", ["-m", "epi_next.encoder_ctfm_cpu_smoke", "--weights",
                  str(args.ctfm_weights.resolve()), "--sha256", args.ctfm_sha,
                  "--output", str(output / "ctfm_encoder_result.json")])]
    records = []
    for name, arguments in jobs:
        command = [sys.executable] + arguments
        start = time.perf_counter()
        job_env = dict(env)
        if name == "ctfm_cpu":
            job_env["PYTHONPATH"] = str(args.ctfm_deps.resolve()) + os.pathsep + str(module)
        result = subprocess.run(command, cwd=root, env=job_env, capture_output=True, text=True)
        (output / (name + ".log")).write_text(result.stdout + result.stderr)
        records.append({"name": name, "command": command, "exit_code": result.returncode,
                        "pythonpath": job_env["PYTHONPATH"],
                        "elapsed_seconds": time.perf_counter()-start,
                        "status": "PASS" if result.returncode == 0 else "FAIL"})
        print(name, records[-1]["status"], "exit", result.returncode, flush=True)
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}
    report = {"experiment_id": "EPI-NEXT-CPU-VERIFICATION-v1", "evidence_scope": "SYNTHETIC_ONLY",
              "source_git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "source_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)),
              "environment": {"python":sys.version,"platform":platform.platform(),"device":"cpu"},
              "jobs":records, "artifact_hashes":hashes, "processes_still_running":False,
              "real_patient_evaluation":"NOT RUN", "ctfm_three_case_feasibility":"NOT RUN"}
    (output / "receipt.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    raise SystemExit(0 if all(r["exit_code"] == 0 for r in records) else 1)


if __name__ == "__main__":
    main()
