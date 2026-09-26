"""Configuration and local filesystem boundaries for one Worker node."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from algorithm.service import MODEL_SHA


@dataclass(frozen=True)
class WorkerConfig:
    worker_id: str
    backend_url: str
    token: str
    model_version: str
    frozen_root: Path
    data_root: Path
    poll_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not self.worker_id or not self.worker_id.startswith("node_") or len(self.worker_id) > 128:
            raise ValueError("WORKER_ID must be a pre-provisioned anonymous node_ ID")
        parts = urlsplit(self.backend_url)
        if parts.scheme != "https" or not parts.netloc or parts.username or parts.password or parts.path not in {"", "/"}:
            raise ValueError("BACKEND_URL must be an HTTPS origin without credentials or path")
        if not self.token or any(char.isspace() for char in self.token):
            raise ValueError("TOKEN must be a non-empty Worker Bearer token")
        if self.model_version != MODEL_SHA:
            raise ValueError("MODEL_VERSION does not match the frozen Baseline checkpoint SHA-256")
        if self.poll_seconds <= 0:
            raise ValueError("WORKER_POLL_SECONDS must be positive")
        frozen = self.frozen_root.resolve()
        data = self.data_root.resolve()
        if data == frozen or data.is_relative_to(frozen) or frozen.is_relative_to(data):
            raise ValueError("WORKER_DATA_ROOT must be separate from the frozen experiment root")

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        required = ("WORKER_ID", "BACKEND_URL", "TOKEN", "MODEL_VERSION", "EPILOCATE_FROZEN_ROOT", "WORKER_DATA_ROOT")
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise ValueError("Missing Worker configuration: " + ", ".join(missing))
        return cls(
            worker_id=os.environ["WORKER_ID"],
            backend_url=os.environ["BACKEND_URL"].rstrip("/"),
            token=os.environ["TOKEN"],
            model_version=os.environ["MODEL_VERSION"],
            frozen_root=Path(os.environ["EPILOCATE_FROZEN_ROOT"]),
            data_root=Path(os.environ["WORKER_DATA_ROOT"]),
            poll_seconds=float(os.getenv("WORKER_POLL_SECONDS", "5")),
        )
