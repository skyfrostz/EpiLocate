"""Static checks for the remote GPU transport templates.

These tests do not connect to ECS or Matrixcloud and do not inspect secrets.
They protect the common-origin and least-surprise defaults used by the later
approved transport test.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENV_TEMPLATE = ROOT / "deploy/remote_gpu_worker.env.example"
SSH_TEMPLATE = ROOT / "deploy/remote_gpu_worker_ssh_tunnel.example.conf"
MODEL_HASH = "548b39b9a799a4cbf56982c569d752c2e37ce4ac005089b0339a6194a3cad734"


def _values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_gpu_template_uses_frozen_hash_and_cuda_mode() -> None:
    values = _values(ENV_TEMPLATE)
    assert values["MODEL_HASH"] == MODEL_HASH
    assert values["MODEL_VERSION"] == MODEL_HASH
    assert values["WORKER_DEVICE"] == "CUDA"
    assert values["BACKEND_URL"] == "https://127.0.0.1:9443"
    assert values["WORKER_CA_CERT"].startswith("/")


def test_gpu_template_does_not_contain_a_credential() -> None:
    text = ENV_TEMPLATE.read_text(encoding="utf-8")
    assert "TOKEN=" not in text
    assert not re.search(r"(?i)(bearer|secret[_-]?key|private[_-]?key)\s*[:=]", text)


def test_tunnel_maps_only_the_two_tls_edges() -> None:
    text = SSH_TEMPLATE.read_text(encoding="utf-8")
    assert "LocalForward 127.0.0.1:9443 127.0.0.1:9443" in text
    assert "LocalForward 127.0.0.1:9444 127.0.0.1:9444" in text
    assert "LocalForward" in text and text.count("LocalForward") == 2
    assert "ExitOnForwardFailure yes" in text
    assert "StrictHostKeyChecking yes" in text
    assert "ClearAllForwardings yes" in text


def test_tunnel_template_has_no_public_application_forward() -> None:
    text = SSH_TEMPLATE.read_text(encoding="utf-8")
    assert "0.0.0.0" not in text
    assert "9000" not in text
    assert "5432" not in text
