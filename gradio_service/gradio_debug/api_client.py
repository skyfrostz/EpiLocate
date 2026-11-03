"""HTTP client for the verified P0 single-slice API. No model or storage access."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import httpx


class APIError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class P0Client:
    def __init__(self, base_url: str | None = None, transport=None, token: str | None = None):
        self.base_url = (base_url or os.getenv("EPILOCATE_API_BASE_URL", "http://127.0.0.1:8877")).rstrip("/")
        # Read only in the Gradio server process; never return this value to components.
        self._token = token if token is not None else os.getenv("EPILOCATE_API_BEARER_TOKEN")
        self.transport = transport

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            with httpx.Client(base_url=self.base_url, timeout=60, transport=self.transport, trust_env=False) as client:
                response = client.request(method, path, headers=headers, **kwargs)
        except httpx.RequestError as exc:
            raise APIError("NETWORK_UNAVAILABLE", "无法连接算法 API；请检查本机服务后重试或用 Job ID 恢复查询。") from exc
        if response.status_code == 401:
            raise APIError("AUTH_REQUIRED", "算法 API 认证失败；请检查 Gradio 服务端 Bearer Token 配置。")
        if response.status_code == 403:
            raise APIError("ACCESS_DENIED", "当前服务端凭据无权访问此资源。")
        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            if isinstance(payload.get("detail"), dict):
                payload = payload["detail"]
            code = payload.get("code", f"HTTP_{response.status_code}")
            message = payload.get("message", "请求失败，请查看服务状态。")
            raise APIError(str(code), str(message))
        return response

    def capabilities(self):
        return self._request("GET", "/api/v1/capabilities").json()

    def upload(self, path: str, key: str | None = None):
        # The browser's original filename must not be sent to the API.
        with Path(path).open("rb") as stream:
            return self._request("POST", "/api/v1/cases", headers={"Idempotency-Key": key or uuid.uuid4().hex},
                                 data={"input_kind": "dicom_series"},
                                 files={"files": ("slice.dcm", stream, "application/dicom")}).json()

    def case(self, case_id: str):
        return self._request("GET", f"/api/v1/cases/{case_id}").json()

    def slices(self, case_id: str):
        return self._request("GET", f"/api/v1/cases/{case_id}/slices").json()

    def preview(self, slice_id: str):
        return self._request("GET", f"/api/v1/slices/{slice_id}/preview").content

    def predict(self, case_id: str, slice_id: str, key: str | None = None):
        return self._request("POST", "/api/v1/predictions", headers={"Idempotency-Key": key or uuid.uuid4().hex},
                             json={"case_id": case_id, "slice_id": slice_id, "unit": "slice",
                                   "model_id": "baseline_resnet18"}).json()

    def occlude(self, case_id: str, slice_id: str, key: str | None = None):
        return self._request("POST", "/api/v1/jobs/occlusion", headers={"Idempotency-Key": key or uuid.uuid4().hex},
                             json={"case_id": case_id, "slice_id": slice_id, "model_id": "baseline_resnet18",
                                   "scales": [16, 32, 64], "protocol_id": "stage1-occlusion-instability-v1"}).json()

    def job(self, job_id: str):
        return self._request("GET", f"/api/v1/jobs/{job_id}").json()

    def result(self, job_id: str):
        return self._request("GET", f"/api/v1/jobs/{job_id}/result").json()

    def positions(self, result_id: str, scale: int, cursor: int = 0):
        return self._request("GET", f"/api/v1/occlusion-results/{result_id}/positions",
                             params={"scale": scale, "cursor": cursor, "limit": 1000}).json()

    def asset(self, result_id: str, asset_id: str):
        return self._request("GET", f"/api/v1/assets/{asset_id}", params={"result_id": result_id}).content
