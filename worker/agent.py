"""One-attempt-at-a-time Worker Agent with lease-aware polling."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .client import BackendUnavailable, WorkerAPIError, WorkerClient
from .config import WorkerConfig
from .inference import (
    FrozenRunner, InvalidWorkerInput, ModelHashMismatch,
    manifest_for_failure, manifest_for_success,
)


LOG = logging.getLogger("epilocate.worker")
MAX_INPUT_BYTES = 20 * 1024 * 1024
MAX_RESULT_BYTES = 64 * 1024 * 1024


class InputDownloadFailed(RuntimeError):
    pass


class InputHashMismatch(RuntimeError):
    pass


class LeaseExpired(RuntimeError):
    pass


class WorkerAgent:
    def __init__(self, config: WorkerConfig, *, client: WorkerClient | None = None,
                 runner: FrozenRunner | None = None, download_transport: httpx.BaseTransport | None = None):
        self.config = config
        self.client = client or WorkerClient(config.backend_url, config.token)
        self.runner = runner or FrozenRunner(config.frozen_root, config.model_hash)
        self.download_transport = download_transport
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._active: dict | None = None
        self._lease_deadline = 0.0
        self._stale = False
        self._fatal = False
        self._connected = False
        self._register_again = False
        self._heartbeat_thread: threading.Thread | None = None
        self.data_root = config.data_root.resolve()
        self.data_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.temp_root = self.data_root / "temp"
        self.temp_root.mkdir(mode=0o700, exist_ok=True)
        if self.temp_root.is_symlink() or not self.temp_root.resolve().is_relative_to(self.data_root):
            raise ValueError("Worker temp root must stay inside WORKER_DATA_ROOT")
        self.claim_key_file = self.data_root / "pending_claim.json"
        if self.claim_key_file.is_symlink():
            raise ValueError("Worker claim state must not be a symlink")
        self._cleanup_old_attempts()

    def _cleanup_old_attempts(self) -> None:
        """Remove only this Worker's expired attempt directories after a crash."""
        cutoff = time.time() - 24 * 60 * 60
        for path in self.temp_root.glob("attempt-*"):
            if not path.is_dir() or path.is_symlink() or path.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(path)

    def _claim_key(self) -> tuple[str, bool]:
        if self.claim_key_file.exists():
            data = json.loads(self.claim_key_file.read_text(encoding="utf-8"))
            return str(uuid.UUID(data["key"])), True
        key = str(uuid.uuid4())
        temporary = self.claim_key_file.with_suffix(".partial")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"key": key}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.claim_key_file)
        return key, False

    @staticmethod
    def _validate_claim(claim: dict) -> None:
        try:
            fields = (claim["job_id"], claim["case_id"], claim["attempt_id"], claim["lease_token"],
                      claim["job_parameters"]["slice_id"], claim["input_reference"]["url"],
                      claim["input_reference"]["expires_at"], claim["lease_expire_time"])
            input_hash = claim["input_reference"]["sha256"]
            model_hash = claim["model_version"]["checkpoint_sha256"]
            kind = claim["job_parameters"]["kind"]
            uuid.UUID(claim["attempt_id"])
            if (not all(isinstance(value, str) and value for value in fields)
                    or not all(re.fullmatch(r"[a-f0-9]{64}", value) for value in (input_hash, model_hash))
                    or kind not in {"PREDICTION", "OCCLUSION"}):
                raise ValueError("Invalid Claim fields")
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkerAPIError(502, "CLAIM_RESPONSE_INVALID") from exc

    def _clear_claim_key(self) -> None:
        self.claim_key_file.unlink(missing_ok=True)

    def register(self) -> dict:
        response = self.client.register(self.config.worker_id, self.config.model_hash, self.runner.hardware)
        if response.get("worker_id") != self.config.worker_id or response.get("registered") is not True:
            raise WorkerAPIError(502, "REGISTER_RESPONSE_INVALID")
        if response.get("heartbeat_interval_seconds") != 15 or response.get("lease_seconds") != 90:
            raise WorkerAPIError(502, "PROTOCOL_VERSION_MISMATCH")
        self._register_again = False
        return response

    def _set_lease(self, response: dict) -> None:
        expires = response.get("lease_expire_time")
        if not expires:
            return
        try:
            expiry = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            server_time = response.get("server_time")
            # Claim omits server_time. Use the frozen 90-second lease only until
            # the immediate Heartbeat supplies the authoritative server clock.
            reference = datetime.fromisoformat(server_time.replace("Z", "+00:00")) if server_time else None
            remaining = (expiry - reference).total_seconds() if reference else 90.0
        except (TypeError, ValueError) as exc:
            raise WorkerAPIError(502, "LEASE_RESPONSE_INVALID") from exc
        with self._lock:
            self._lease_deadline = time.monotonic() + max(0.0, remaining - 2.0)
            if remaining <= 2:
                self._stale = True

    def _lease_valid(self) -> bool:
        with self._lock:
            return not self._stale and self._active is not None and time.monotonic() < self._lease_deadline

    def heartbeat_once(self) -> dict:
        with self._lock:
            active = self._active
            stale = self._stale
        activity = "RUNNING" if active and not stale else "IDLE"
        attempt = ({"job_id": active["job_id"], "attempt_id": active["attempt_id"],
                    "lease_token": active["lease_token"]} if activity == "RUNNING" else None)
        try:
            response = self.client.heartbeat(self.config.worker_id, activity, attempt)
        except BackendUnavailable:
            self._connected = False
            raise
        except WorkerAPIError as exc:
            self._connected = False
            if exc.code == "STALE_ATTEMPT":
                with self._lock:
                    self._stale = True
            elif exc.code == "WORKER_NOT_REGISTERED":
                self._register_again = True
            elif exc.status in {401, 403}:
                self._fatal = True
            raise
        if activity == "RUNNING":
            if not response.get("server_time") or not response.get("lease_expire_time"):
                self._connected = False
                raise WorkerAPIError(502, "HEARTBEAT_RESPONSE_INVALID")
            self._set_lease(response)
        self._connected = True
        return response

    def _heartbeat_loop(self) -> None:
        delay = 15.0
        while not self.stop_event.wait(delay):
            try:
                self._heartbeat_tick()
                delay = 15.0
            except (BackendUnavailable, WorkerAPIError) as exc:
                LOG.warning("Heartbeat unavailable: %s", type(exc).__name__)
                if isinstance(exc, WorkerAPIError) and (
                    (exc.status in {401, 403} and exc.code != "WORKER_NOT_REGISTERED")
                    or exc.code == "PROTOCOL_VERSION_MISMATCH"
                ):
                    self._fatal = True
                if self._fatal:
                    self.stop_event.set()
                    return
                delay = min(15.0, 1.0 if delay == 15.0 else delay * 2)

    def _heartbeat_tick(self) -> None:
        if self._register_again:
            self.register()
        self.heartbeat_once()

    def start_heartbeats(self) -> None:
        if self._heartbeat_thread is None:
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="worker-heartbeat", daemon=True)
            self._heartbeat_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2)

    def _download(self, claim: dict, path: Path) -> str:
        reference = claim["input_reference"]
        url = reference["url"]
        if urlsplit(url).scheme != "https":
            raise InputDownloadFailed("Input reference is not HTTPS")
        expires = datetime.fromisoformat(reference["expires_at"].replace("Z", "+00:00"))
        if expires <= datetime.now(timezone.utc):
            raise InputDownloadFailed("Input reference expired")
        digest = hashlib.sha256()
        size = 0
        try:
            with httpx.Client(transport=self.download_transport, timeout=30, trust_env=False,
                              follow_redirects=False) as client:
                with client.stream("GET", url, headers={"Cache-Control": "no-store"}) as response:
                    if response.status_code != 200:
                        raise InputDownloadFailed("Input transfer failed")
                    with path.open("xb") as stream:
                        for chunk in response.iter_bytes(64 * 1024):
                            size += len(chunk)
                            if size > MAX_INPUT_BYTES:
                                raise InputDownloadFailed("Input exceeds P0 limit")
                            digest.update(chunk)
                            stream.write(chunk)
        except httpx.RequestError as exc:
            raise InputDownloadFailed("Input transfer failed") from exc
        if digest.hexdigest() != reference["sha256"]:
            raise InputHashMismatch("Downloaded input hash mismatch")
        return digest.hexdigest()

    def _submit_with_retry(self, claim: dict, manifest: dict, assets: dict[str, tuple[bytes, str]]) -> dict:
        size = len(json.dumps(manifest).encode()) + sum(len(data) for data, _ in assets.values())
        if size > MAX_RESULT_BYTES:
            raise InvalidWorkerInput("Result exceeds 64 MiB limit")
        last_error = None
        replayed_after_loss = False
        for delay in (0, 1, 2, 4, 8, 15, 15, 15):
            if delay:
                if self.stop_event.wait(delay):
                    break
            if last_error is not None and not self._lease_valid():
                if replayed_after_loss:
                    break
                replayed_after_loss = True
            try:
                response = self.client.submit(claim["job_id"], manifest, assets)
                if response.get("accepted") is not True or response.get("job_id") != claim["job_id"] or response.get("attempt_id") != claim["attempt_id"]:
                    raise WorkerAPIError(502, "RESULT_RESPONSE_INVALID")
                return response
            except BackendUnavailable as exc:
                last_error = exc
                self._connected = False
            except WorkerAPIError as exc:
                if exc.code in {"STALE_ATTEMPT", "RESULT_CONFLICT", "MODEL_HASH_MISMATCH"} or not exc.retryable:
                    raise
                last_error = exc
            # An uncertain upload may already have been accepted. One replay
            # can recover its saved response after local lease loss.
            if replayed_after_loss:
                break
        raise BackendUnavailable("Result submission could not be confirmed") from last_error

    def process_claim(self, claim: dict, claim_key: str | None = None) -> dict | None:
        with self._lock:
            if self._active is not None:
                raise WorkerAPIError(409, "WORKER_BUSY")
            self._active = claim
            self._stale = False
        self._set_lease(claim)
        try:
            # Claim has no server_time. Do not begin inference until Backend
            # confirms this Attempt and its lease using the server clock.
            self.heartbeat_once()
            if not self._lease_valid():
                raise LeaseExpired("Lease expired before execution")
            if claim.get("model_version", {}).get("checkpoint_sha256") != self.config.model_hash:
                manifest = manifest_for_failure(self.config.worker_id, claim, "MODEL_HASH_MISMATCH")
                return self._submit_with_retry(claim, manifest, {})
            with tempfile.TemporaryDirectory(prefix="attempt-", dir=self.temp_root) as directory:
                root = Path(directory)
                input_path = root / "input.dcm"
                try:
                    try:
                        input_hash = self._download(claim, input_path)
                    except InputDownloadFailed:
                        if claim_key is None or not self._lease_valid():
                            raise
                        # Replay the same Claim key at capacity zero to refresh
                        # a short-lived signed URL without taking another Job.
                        input_path.unlink(missing_ok=True)
                        try:
                            refreshed = self.client.claim(self.config.worker_id, self.config.model_hash,
                                                          claim_key, 0)
                        except WorkerAPIError as exc:
                            if exc.code in {"STALE_ATTEMPT", "CLAIM_ALREADY_FINISHED"}:
                                raise LeaseExpired("Claim is no longer active") from exc
                            raise
                        if (not refreshed or refreshed.get("job_id") != claim["job_id"]
                                or refreshed.get("attempt_id") != claim["attempt_id"]
                                or refreshed.get("lease_token") != claim["lease_token"]):
                            raise InputDownloadFailed("Claim replay did not return the same Attempt")
                        claim = refreshed
                        with self._lock:
                            self._active = claim
                        self._set_lease(claim)
                        input_hash = self._download(claim, input_path)
                    if not self._lease_valid():
                        raise LeaseExpired("Lease expired before inference")
                    output = self.runner.run(claim, input_path, root / "assets")
                    manifest = manifest_for_success(self.config.worker_id, claim, input_hash, output)
                    assets = output.assets
                except InputDownloadFailed:
                    manifest = manifest_for_failure(self.config.worker_id, claim, "INPUT_DOWNLOAD_FAILED")
                    assets = {}
                except InputHashMismatch:
                    manifest = manifest_for_failure(self.config.worker_id, claim, "INPUT_HASH_MISMATCH")
                    assets = {}
                except ModelHashMismatch:
                    manifest = manifest_for_failure(self.config.worker_id, claim, "MODEL_HASH_MISMATCH")
                    assets = {}
                except (BackendUnavailable, WorkerAPIError, LeaseExpired):
                    raise
                except (InvalidWorkerInput, ValueError):
                    manifest = manifest_for_failure(self.config.worker_id, claim, "PREPROCESSING_FAILED")
                    assets = {}
                except Exception:
                    LOG.error("Inference failed for job %s", claim["job_id"])
                    manifest = manifest_for_failure(self.config.worker_id, claim, "INFERENCE_FAILED")
                    assets = {}
                if not self._lease_valid():
                    raise LeaseExpired("Lease expired before result submission")
                return self._submit_with_retry(claim, manifest, assets)
        finally:
            with self._lock:
                self._active = None
                self._lease_deadline = 0.0
                self._stale = False

    def run_once(self) -> dict | None:
        key, recovering = self._claim_key()
        try:
            claim = self.client.claim(self.config.worker_id, self.config.model_hash, key, 0 if recovering else 1)
        except BackendUnavailable:
            self._connected = False
            LOG.warning("Backend unavailable during claim")
            return None
        except WorkerAPIError as exc:
            if exc.code in {"CLAIM_ALREADY_FINISHED", "CLAIM_KEY_CONFLICT"}:
                self._clear_claim_key()
            if exc.status in {401, 403}:
                if exc.code == "WORKER_NOT_REGISTERED":
                    self._register_again = True
                    self._connected = False
                else:
                    self._fatal = True
            raise
        self._clear_claim_key()
        if claim is None:
            return None
        self._validate_claim(claim)
        if claim.get("model_version", {}).get("checkpoint_sha256") != self.config.model_hash:
            LOG.warning("Claimed model hash differs from local frozen checkpoint")
        return self.process_claim(claim, key)

    def run_forever(self) -> None:
        delay = 1.0
        while not self.stop_event.is_set():
            try:
                self.register()
                self.heartbeat_once()
                break
            except BackendUnavailable:
                LOG.warning("Backend unavailable during registration")
            except WorkerAPIError as exc:
                if (exc.status in {401, 403} and exc.code != "WORKER_NOT_REGISTERED") or exc.code == "PROTOCOL_VERSION_MISMATCH":
                    raise
                LOG.warning("Registration rejected: %s", exc.code)
            if self.stop_event.wait(delay):
                return
            delay = min(delay * 2, 30)
        self.start_heartbeats()
        while not self.stop_event.is_set() and not self._fatal:
            try:
                if self._connected:
                    self.run_once()
            except LeaseExpired:
                LOG.warning("Attempt lease expired; no result uploaded")
            except BackendUnavailable:
                self._connected = False
                LOG.warning("Backend unavailable; claim or result will be retried by Backend lease policy")
            except WorkerAPIError as exc:
                if exc.code == "WORKER_NOT_REGISTERED":
                    self._register_again = True
                    self._connected = False
                elif exc.status in {401, 403}:
                    self._fatal = True
                LOG.warning("Worker API rejected request: %s", exc.code)
            if self.stop_event.wait(self.config.poll_seconds):
                break
        self.stop()
