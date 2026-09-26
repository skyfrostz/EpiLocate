"""Configuration and local filesystem boundaries for one Worker node."""
from __future__ import annotations

import os
import re
import math
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
    model_hash: str
    tls_ca_file: Path | None = None
    poll_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not re.fullmatch(r"node_[A-Za-z0-9_-]{1,123}", self.worker_id):
            raise ValueError("WORKER_ID must be a pre-provisioned anonymous node_ ID")
        parts = urlsplit(self.backend_url)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.path not in {"", "/"} or parts.query or parts.fragment):
            raise ValueError("BACKEND_URL must be an HTTPS origin without credentials or path")
        if not self.token or any(char.isspace() for char in self.token):
            raise ValueError("TOKEN must be a non-empty Worker Bearer token")
        if not re.fullmatch(r"[a-f0-9]{64}", self.model_hash) or self.model_hash != MODEL_SHA:
            raise ValueError("MODEL_HASH does not match the frozen Baseline checkpoint SHA-256")
        if self.model_version != self.model_hash:
            raise ValueError("MODEL_VERSION must equal MODEL_HASH under Worker Protocol v1")
        if not math.isfinite(self.poll_seconds) or self.poll_seconds <= 0:
            raise ValueError("WORKER_POLL_SECONDS must be positive")
        if self.tls_ca_file is not None:
            ca_file = self.tls_ca_file.expanduser().resolve()
            if not ca_file.is_file():
                raise ValueError("WORKER_CA_CERT must point to a readable CA certificate file")
        frozen = self.frozen_root.resolve()
        data = self.data_root.resolve()
        if data == frozen or data.is_relative_to(frozen) or frozen.is_relative_to(data):
            raise ValueError("WORKER_DATA_ROOT must be separate from the frozen experiment root")

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        required = ("WORKER_ID", "BACKEND_URL", "TOKEN", "MODEL_HASH", "MODEL_VERSION", "EPILOCATE_FROZEN_ROOT", "WORKER_DATA_ROOT")
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
            model_hash=os.environ["MODEL_HASH"],
            tls_ca_file=Path(os.environ["WORKER_CA_CERT"]) if os.getenv("WORKER_CA_CERT") else None,
        )
