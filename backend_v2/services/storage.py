from __future__ import annotations

import os
import secrets
from datetime import timedelta

import boto3

from backend_v2.services.common import aware, fail, now


class ObjectStore:
    """Private S3 compatible object storage; no public bucket URLs."""

    def __init__(self):
        self.bucket = os.environ.get("EPILOCATE_V2_S3_BUCKET")
        if not self.bucket:
            fail("STORAGE_NOT_CONFIGURED", 503)
        self.client = boto3.client("s3", endpoint_url=os.environ.get("EPILOCATE_V2_S3_ENDPOINT") or None)

    def put(self, body: bytes, content_type: str, prefix: str) -> str:
        key = f"{prefix}/{secrets.token_hex(24)}"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type, ServerSideEncryption="AES256")
        return key

    def delete(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_get(self, sl):
        if not sl.staging_object_key or not sl.staging_expires_at or aware(sl.staging_expires_at) <= now():
            fail("INPUT_EXPIRED", 410)
        seconds = min(300, int((aware(sl.staging_expires_at) - now()).total_seconds()))
        if seconds <= 0:
            fail("INPUT_EXPIRED", 410)
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": sl.staging_object_key}, ExpiresIn=seconds)

    def read(self, key: str) -> tuple[bytes, str]:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")
