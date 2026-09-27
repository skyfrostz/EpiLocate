from __future__ import annotations

import os

import pytest
from sqlalchemy import inspect

from backend_v2.db.base import make_engine
from backend_v2.services.storage import ObjectStore


@pytest.mark.production_like
def test_postgres_schema_and_minio_round_trip():
    database_url = os.environ.get("EPILOCATE_V2_PRODUCTION_DATABASE_URL")
    endpoint = os.environ.get("EPILOCATE_V2_S3_ENDPOINT")
    if not database_url or not endpoint:
        pytest.skip("Set EPILOCATE_V2_PRODUCTION_DATABASE_URL and MinIO storage variables")
    engine = make_engine(database_url)
    expected = {"cases", "slices", "inference_jobs", "inference_results", "assets", "worker_nodes", "model_versions"}
    with engine.connect() as connection:
        assert expected <= set(inspect(connection).get_table_names())
    store = ObjectStore()
    payload = b"production-like-object"
    key = store.put(payload, "application/octet-stream", "integration")
    try:
        data, media_type = store.read(key)
        assert data == payload and media_type == "application/octet-stream"
        signed_url = store.signed_key_get(key)
        assert "X-Amz-Signature" in signed_url
    finally:
        store.delete(key)
