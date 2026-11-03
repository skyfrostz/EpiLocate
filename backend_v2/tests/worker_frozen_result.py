"""Run the unchanged Worker v1 inference adapter in its own Python environment.

Used only by the optional Backend/Worker integration test. No model data or
generated assets are added to Git.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

from worker.inference import FrozenRunner, manifest_for_success


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    claim = json.load(sys.stdin)
    runner = FrozenRunner(args.frozen_root, claim["model_version"]["checkpoint_sha256"])
    output = runner.run(claim, args.input, args.output / "generated")
    manifest = manifest_for_success(args.worker_id, claim, hashlib.sha256(args.input.read_bytes()).hexdigest(), output)
    encoded_assets = {}
    for name, (data, media_type) in output.assets.items():
        if Path(name).name != name:
            raise ValueError("unsafe Worker asset name")
        encoded_assets[name] = {"data": base64.b64encode(data).decode("ascii"), "media_type": media_type}
    print(json.dumps({"manifest": manifest, "assets": encoded_assets}, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
