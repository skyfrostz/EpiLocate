"""Local immutable run receipts. Unknown writes are reconciled, never overwritten.

This is a local research store, not a replacement for Backend Worker leases or
a distributed GPU queue. No remote compute is scheduled by this module.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re


def canonical_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", name):
        raise ValueError("one plain filename required")
    return name


@contextmanager
def exclusive_local_queue(root: Path):
    """One nonblocking local writer per root; leave lock file in place."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".writer.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("LOCAL_QUEUE_BUSY") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def reconcile_run(root: Path, run_id: str) -> dict:
    run_id = _safe_name(run_id)
    directory = Path(root) / run_id
    if not directory.exists():
        return {"state": "ABSENT", "run_id": run_id}
    if directory.is_symlink() or not directory.is_dir():
        return {"state": "CONFLICT", "run_id": run_id}
    receipt = directory / "receipt.json"
    if not receipt.is_file():
        return {"state": "UNKNOWN_TRANSACTION", "run_id": run_id}
    try:
        if receipt.is_symlink():
            raise ValueError("symlink")
        metadata = json.loads(receipt.read_text())
        if (not isinstance(metadata, dict) or metadata.get("run_id") != run_id
                or not isinstance(metadata.get("artifact_hashes"), dict)
                or not metadata["artifact_hashes"]):
            raise ValueError("receipt identity")
        expected = {"receipt.json"} | set(metadata["artifact_hashes"])
        if {p.name for p in directory.iterdir()} != expected:
            raise ValueError("unexpected or absent artifact")
        for name, digest in metadata["artifact_hashes"].items():
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("invalid artifact hash")
            path = directory / _safe_name(name)
            if path.is_symlink() or sha256(path.read_bytes()) != digest:
                raise ValueError("artifact hash mismatch")
    except (OSError, ValueError, KeyError, TypeError):
        return {"state": "CORRUPT", "run_id": run_id}
    return {"state": "COMMITTED", "run_id": run_id, "receipt": metadata}


def persist_run(root: Path, run_id: str, artifacts: dict[str, bytes]) -> dict:
    """Identical retries return saved receipt; all uncertain/conflicting states stop."""
    run_id = _safe_name(run_id)
    if not run_id.startswith("EPI-NEXT"):
        raise ValueError("EPI-NEXT run ID required")
    if not artifacts or "receipt.json" in artifacts:
        raise ValueError("nonempty artifacts required; receipt.json is reserved")
    for name, data in artifacts.items():
        _safe_name(name)
        if not isinstance(data, bytes):
            raise TypeError("artifact contents must be bytes")
    hashes = {name: sha256(data) for name, data in artifacts.items()}
    root = Path(root)
    with exclusive_local_queue(root):
        observed = reconcile_run(root, run_id)
        if observed["state"] == "COMMITTED":
            if observed["receipt"]["artifact_hashes"] != hashes:
                raise RuntimeError("RESULT_CONFLICT")
            return observed
        if observed["state"] != "ABSENT":
            raise RuntimeError(observed["state"] + ": reconcile before retry")
        directory = root / run_id
        directory.mkdir()
        root_descriptor = os.open(root, os.O_RDONLY)
        try:
            os.fsync(root_descriptor)
        finally:
            os.close(root_descriptor)
        # Receipt is written last. A crash preserves partial files for inspection.
        for name, data in artifacts.items():
            _write_new(directory / name, data)
        receipt = {"schema": "EPI-NEXT-LOCAL-RECEIPT-1", "run_id": run_id,
                   "artifact_hashes": hashes}
        _write_new(directory / "receipt.json", canonical_json(receipt))
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return reconcile_run(root, run_id)
