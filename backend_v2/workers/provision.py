"""Provision one Worker identity and frozen model in the Backend database.

The Bearer token is written once to a mode-0600 local env file and never logged.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import secrets
import shlex
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend_v2.db.base import make_engine
from backend_v2.models.entities import ModelVersion, WorkerNode
from backend_v2.services.common import public_id


def provision(db: Session, *, model_id: str, model_hash: str, preprocessing_version: str,
              protocol_id: str, display_name: str, worker_id: str | None = None,
              token: str | None = None) -> tuple[str, str]:
    if not re.fullmatch(r"[a-f0-9]{64}", model_hash):
        raise ValueError("model_hash must be a lower-case SHA-256")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,96}", model_id):
        raise ValueError("invalid model_id")
    worker_id = worker_id or public_id("node")
    if not re.fullmatch(r"node_[a-f0-9]{32}", worker_id):
        raise ValueError("worker_id must be an anonymous node_ ID")
    token = token or secrets.token_urlsafe(48)
    if len(token) < 32 or any(char.isspace() for char in token):
        raise ValueError("worker token must be high entropy")
    model = db.scalar(select(ModelVersion).where(ModelVersion.model_id == model_id, ModelVersion.version == model_hash))
    active_versions = db.scalars(select(ModelVersion).where(ModelVersion.model_id == model_id,
                                                             ModelVersion.lifecycle_state == "ACTIVE")).all()
    if active_versions and (len(active_versions) != 1 or model is None or active_versions[0].id != model.id):
        raise ValueError("another active model version exists for this model_id")
    if model:
        if (model.checkpoint_sha256, model.preprocessing_version, model.protocol_id, model.lifecycle_state) != (model_hash, preprocessing_version, protocol_id, "ACTIVE"):
            raise ValueError("existing model version conflicts with frozen metadata")
    else:
        db.add(ModelVersion(model_id=model_id, version=model_hash, checkpoint_sha256=model_hash,
                            preprocessing_version=preprocessing_version, protocol_id=protocol_id))
    if db.scalar(select(WorkerNode).where(WorkerNode.node_id == worker_id)):
        raise ValueError("worker_id already exists; rotate credentials via a separate operation")
    db.add(WorkerNode(node_id=worker_id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                      display_name=display_name, supported_models=[]))
    db.flush()
    return worker_id, token


def write_worker_env(path: Path, *, worker_id: str, token: str, model_hash: str,
                     backend_url: str, frozen_root: Path, data_root: Path):
    if path.exists() or path.is_symlink():
        raise FileExistsError(path)
    parsed = urlsplit(backend_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("backend_url must be an HTTPS origin")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    values = {"WORKER_ID": worker_id, "TOKEN": token, "MODEL_VERSION": model_hash,
              "BACKEND_URL": backend_url.rstrip("/"), "EPILOCATE_FROZEN_ROOT": str(frozen_root),
              "WORKER_DATA_ROOT": str(data_root)}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for key, value in values.items():
                stream.write(f"export {key}={shlex.quote(value)}\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description="Provision a single EpiLocate Worker")
    parser.add_argument("--model-id", default="baseline_resnet18")
    parser.add_argument("--model-hash", required=True)
    parser.add_argument("--preprocessing-version", required=True)
    parser.add_argument("--protocol-id", required=True)
    parser.add_argument("--display-name", default="EpiLocate AI Worker")
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("output already exists; refusing to overwrite a credential")
    engine = make_engine()
    wrote_credential = False
    try:
        with Session(engine) as db:
            with db.begin():
                worker_id, token = provision(db, model_id=args.model_id, model_hash=args.model_hash,
                    preprocessing_version=args.preprocessing_version, protocol_id=args.protocol_id,
                    display_name=args.display_name)
                write_worker_env(args.output, worker_id=worker_id, token=token, model_hash=args.model_hash,
                    backend_url=args.backend_url, frozen_root=args.frozen_root, data_root=args.data_root)
                wrote_credential = True
    except Exception:
        if wrote_credential:
            args.output.unlink(missing_ok=True)
        raise
    print(f"worker_id={worker_id}")
    print(f"model_hash={args.model_hash}")
    print(f"bearer_token_file={args.output}")


if __name__ == "__main__":
    main()
