"""Authenticated HTTPS transport for the frozen Worker Protocol v1."""
from __future__ import annotations

import json
import uuid
from urllib.parse import urlsplit

import httpx


class BackendUnavailable(RuntimeError):
    pass


class WorkerAPIError(RuntimeError):
    def __init__(self, status: int, code: str, retryable: bool = False):
        self.status = status
        self.code = code
        self.retryable = retryable
        super().__init__(f"Backend returned {status} {code}")


class WorkerClient:
    def __init__(self, base_url: str, token: str, transport: httpx.BaseTransport | None = None,
                 verify: bool | str = True):
        if urlsplit(base_url).scheme != "https":
            raise ValueError("Worker API requires HTTPS")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.transport = transport
        self.verify = verify

    def _request(self, path: str, *, key: str | None = None, **kwargs) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token}", "X-Request-ID": str(uuid.uuid4())}
        if key is not None:
            headers["Idempotency-Key"] = key
        try:
            with httpx.Client(base_url=self.base_url, transport=self.transport, timeout=30,
                              trust_env=False, follow_redirects=False, verify=self.verify) as client:
                response = client.post(path, headers=headers, **kwargs)
        except httpx.RequestError as exc:
            raise BackendUnavailable("Backend connection unavailable") from exc
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {}
            raise WorkerAPIError(response.status_code, str(body.get("code", "HTTP_ERROR")),
                                 bool(body.get("retryable", response.status_code >= 500)))
        return response

    def register(self, worker_id: str, model_hash: str, hardware: dict) -> dict:
        return self._request("/api/v2/workers/register", json={
            "worker_id": worker_id, "worker_version": "1.0.0", "hardware": hardware,
            "supported_model_versions": [{"model_id": "baseline_resnet18", "checkpoint_sha256": model_hash}],
            "max_concurrent_jobs": 1,
        }).json()

    def heartbeat(self, worker_id: str, activity: str, active_attempt: dict | None) -> dict:
        return self._request("/api/v2/workers/heartbeat", json={
            "worker_id": worker_id, "activity_state": activity, "active_attempt": active_attempt,
        }).json()

    def claim(self, worker_id: str, model_hash: str, key: str, capacity: int) -> dict | None:
        response = self._request("/api/v2/workers/jobs/claim", key=key, json={
            "worker_id": worker_id, "available_capacity": capacity,
            "supported_model_versions": [{"model_id": "baseline_resnet18", "checkpoint_sha256": model_hash}],
        })
        return None if response.status_code == 204 else response.json()

    def submit(self, job_id: str, manifest: dict, assets: dict[str, tuple[bytes, str]]) -> dict:
        encoded_manifest = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)
        parts = [("manifest", (None, encoded_manifest))]
        parts.extend(("assets[]", (part_name, data, media_type))
                     for part_name, (data, media_type) in sorted(assets.items()))
        response = self._request(f"/api/v2/workers/jobs/{job_id}/result",
                                 files=parts)
        return response.json()
