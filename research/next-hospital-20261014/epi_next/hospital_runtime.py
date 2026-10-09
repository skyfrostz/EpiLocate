"""Admission and immutable receipts for explicitly registered local algorithms.

No checkpoint discovery, remote submission, process termination or automatic
retry. Device locks are shared across worktrees; MPS is reserved for ENCODER.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import time
from typing import Callable

import numpy as np

from .artifacts import canonical_json, persist_run, reconcile_run, sha256, _safe_name
from .hospital_contract import (ALGORITHMS, ExecutionStatus, request_hash,
                                validate_result, validate_request)


QUEUE_ROOT = Path.home() / ".codex" / "epi-next-device-queue"
STATUS_MAP = {
    "OK": "SUCCESS", "SUCCESS": "SUCCESS", "COMPLETE": "SUCCESS",
    "NO_FEASIBLE_MASK": "NO_RELIABLE_RESPONSE", "NO_RELIABLE_RESPONSE": "NO_RELIABLE_RESPONSE",
    "NO_MULTISCALE_SUPPORT": "NO_RELIABLE_RESPONSE", "PARTIAL_BUDGET": "PARTIAL_BUDGET",
    "TIMEOUT": "PARTIAL_BUDGET", "FAILED": "FAILED", "MODEL_FAILURE": "FAILED",
    "NUMERICAL_FAILURE": "FAILED", "MODEL_UNAVAILABLE": "BLOCKED",
    "INPUT_UNSUPPORTED": "BLOCKED", "GEOMETRY_INVALID": "BLOCKED",
    "BLOCKED": "BLOCKED", "NOT RUN": "NOT RUN",
}


@contextmanager
def device_lease(device, *, owner="INTEGRATION"):
    if device not in {"cpu", "mps"}:
        raise RuntimeError("REMOTE_GPU_PAUSED")
    if device == "mps" and owner != "ENCODER":
        raise RuntimeError("MPS_RESERVED_FOR_ENCODER")
    QUEUE_ROOT.mkdir(parents=True, exist_ok=True)
    path = QUEUE_ROOT / f"{device}.lock"
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a+b") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("DEVICE_QUEUE_BUSY") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


@dataclass(frozen=True)
class RegisteredRuntime:
    """Coordinator-provided exact binding; does not certify clinical validity.

    Function receives request and a budget checkpoint. It MUST call checkpoint
    immediately before every forward. Returned candidates already use the
    hospital spatial contract; validators rederive their mappings.
    """
    algorithm_id: str
    algorithm_version: str
    model_id: str
    model_version: str
    model_sha256: str
    preprocessing_version: str
    preprocessing_sha256: str
    device: str
    function: Callable

    def matches(self, request):
        return all(getattr(self, key) == request[key] for key in (
            "algorithm_id", "algorithm_version", "model_id", "model_version",
            "model_sha256", "preprocessing_version", "preprocessing_sha256")) and self.device == request["resource_budget"]["device"]


class BudgetStop(Exception):
    pass


class CallBudget:
    def __init__(self, request):
        self.limits = request["resource_budget"]
        self.started = time.monotonic()
        self.calls = 0
        self.stopped = False

    def before_forward(self):
        if (self.calls >= self.limits["max_model_calls"]
                or time.monotonic() - self.started >= self.limits["max_seconds"]):
            self.stopped = True
            raise BudgetStop("RESOURCE_BUDGET_EXHAUSTED")
        self.calls += 1  # attempts, including failures


def output_envelope(request, raw, *, calls=0, seconds=0., artifacts=None):
    original_status = raw.get("status", "NOT RUN")
    status = STATUS_MAP.get(original_status, "FAILED")
    logits = raw.get("logits", [])
    values = np.asarray(logits, dtype=float)
    prediction = None
    if values.size:
        probs = np.exp(values - values.max()); probs /= probs.sum()
        prediction = {"class_index": int(values.argmax()), "scores": probs.tolist(),
                      "calibration_status": "UNCALIBRATED"}
    candidates = raw.get("candidate_regions", []) if status in {"SUCCESS", "PARTIAL_BUDGET"} else []
    result = {"schema": "EPI-NEXT-HOSPITAL-OUTPUT-1", "run_id": request["run_id"],
              "request_sha256": request_hash(request), "algorithm_id": request["algorithm_id"],
              "status": status, "algorithm_status": original_status,
              "reason": raw.get("reason") or original_status,
              "evidence_type": ALGORITHMS[request["algorithm_id"]]["evidence_type"],
              "logits": logits, "raw_prediction": prediction, "candidate_regions": candidates,
              "geometry_status": "INVALID" if original_status == "GEOMETRY_INVALID" else "MATHEMATICAL_ONLY",
              "runtime_seconds": seconds, "actual_model_calls": calls, "artifacts": artifacts or [],
              "hospital_candidate": False, "clinical_validation": "NOT RUN"}
    validate_result(request, result)
    return result


def execute_registered(request, runtime, output_root, *, owner="INTEGRATION"):
    """Reconcile before invoking the runtime. Crash intent persists globally.

    Unknown/rejected requests return BLOCKED without overwriting evidence.
    Existing identical results replay from disk, including after browser refresh.
    Unknown intents are NEVER retried even when no PID is visible.
    """
    validate_request(request)
    run_id = _safe_name(request["run_id"])
    digest = request_hash(request)
    output_root = Path(output_root).resolve()
    observed = reconcile_run(output_root, run_id)
    if observed["state"] == "COMMITTED":
        saved = json.loads((output_root / run_id / "request.json").read_bytes())
        if request_hash(saved) != digest:
            return output_envelope(request, {"status": "BLOCKED", "reason": "RESULT_CONFLICT"})
        result = json.loads((output_root / run_id / "result.json").read_bytes())
        validate_result(request, result)
        return result
    if observed["state"] != "ABSENT":
        return output_envelope(request, {"status": "BLOCKED", "reason": observed["state"]})
    if request["source"] == "LIVE_CASE":
        # Native DATA v3 and the standalone first-real preparer are available.
        # Hospital endpoint wiring/accepted runtime is still a separate gate.
        return output_envelope(request, {"status": "BLOCKED", "reason": "BLOCKED_BY_HOSPITAL_RUNTIME_HANDOFF"})
    if runtime is None:
        return output_envelope(request, {"status": "NOT RUN", "reason": "NO_ACCEPTED_RUNTIME_REGISTERED"})
    if not runtime.matches(request):
        return output_envelope(request, {"status": "BLOCKED", "reason": "RUNTIME_VERSION_MISMATCH"})
    try:
        with device_lease(request["resource_budget"]["device"], owner=owner):
            return _execute_leased(request, runtime, output_root, run_id, digest)
    except RuntimeError as exc:
        if str(exc) not in {"DEVICE_QUEUE_BUSY", "MPS_RESERVED_FOR_ENCODER", "REMOTE_GPU_PAUSED"}:
            raise
        return output_envelope(request, {"status": "BLOCKED", "reason": str(exc)})


def _execute_leased(request, runtime, output_root, run_id, digest):
    intent_root = QUEUE_ROOT / "intents"
    intent_root.mkdir(exist_ok=True)
    intent = intent_root / f"{run_id}.json"
    if intent.exists() or intent.is_symlink():
        return output_envelope(request, {"status": "BLOCKED", "reason": "UNKNOWN_TRANSACTION_RECONCILE_REQUIRED"})
    try:
        descriptor = os.open(intent, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return output_envelope(request, {"status": "BLOCKED", "reason": "UNKNOWN_TRANSACTION_RECONCILE_REQUIRED"})
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(canonical_json({"run_id": run_id, "request_sha256": digest,
                                    "output_root": str(output_root), "state": "STARTED"}))
        stream.flush(); os.fsync(stream.fileno())
    # A completed intent is deliberately retained. Replay is possible only with
    # the verified original output root; changing roots must not recompute.
    budget = CallBudget(request)
    try:
        raw, artifacts = runtime.function(request, budget.before_forward)
        if not isinstance(artifacts, dict) or not all(isinstance(v, bytes) for v in artifacts.values()):
            raise ValueError("runtime must return run-local bytes artifacts")
        if set(artifacts) & {"request.json", "result.json", "raw_result.json", "receipt.json"}:
            raise ValueError("runtime used reserved artifact name")
        if budget.stopped or time.monotonic() - budget.started >= budget.limits["max_seconds"]:
            raw = dict(raw, status="PARTIAL_BUDGET", reason="RESOURCE_BUDGET_EXHAUSTED")
        descriptors = [{"path": name, "sha256": sha256(data)} for name, data in artifacts.items()]
        result = output_envelope(request, raw, calls=budget.calls,
                                 seconds=time.monotonic()-budget.started, artifacts=descriptors)
    except BudgetStop:
        raw, artifacts = {"status": "PARTIAL_BUDGET", "reason": "RESOURCE_BUDGET_EXHAUSTED"}, {}
        result = output_envelope(request, raw, calls=budget.calls, seconds=time.monotonic()-budget.started)
    except Exception:
        # Private exceptions may include DICOM identifiers or paths. Keep a
        # closed public reason; no raw exception text enters hospital records.
        raw, artifacts = {"status": "FAILED", "reason": "RUNTIME_OR_CONTRACT_FAILURE"}, {}
        result = output_envelope(request, raw, calls=budget.calls, seconds=time.monotonic()-budget.started)
    artifacts.update({"request.json": canonical_json(request), "result.json": canonical_json(result),
                      "raw_result.json": canonical_json(raw)})
    persist_run(output_root, run_id, artifacts)
    return result
