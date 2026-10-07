from __future__ import annotations

import os
import secrets
from datetime import timedelta

import boto3
from botocore.config import Config

from backend_v2.services.common import aware, fail, now


class ObjectStore:
    """Private S3 compatible object storage; no public bucket URLs."""

    def __init__(self):
        self.bucket = os.environ.get("EPILOCATE_V2_S3_BUCKET")
        if not self.bucket:
            fail("STORAGE_NOT_CONFIGURED", 503)
        endpoint = os.environ.get("EPILOCATE_V2_S3_ENDPOINT") or None
        public_endpoint = os.environ.get("EPILOCATE_V2_S3_PUBLIC_ENDPOINT") or endpoint
        region = os.environ.get("EPILOCATE_V2_S3_REGION", "us-east-1")
        access_key = os.environ.get("EPILOCATE_V2_S3_ACCESS_KEY")
        secret_key = os.environ.get("EPILOCATE_V2_S3_SECRET_KEY")
        if endpoint and not endpoint.startswith(("http://", "https://")):
            fail("INVALID_STORAGE_ENDPOINT", 503)
        if public_endpoint and not public_endpoint.startswith(("http://", "https://")):
            fail("INVALID_STORAGE_PUBLIC_ENDPOINT", 503)
        if endpoint and (not access_key or not secret_key):
            fail("STORAGE_CREDENTIALS_NOT_CONFIGURED", 503)
        addressing = os.environ.get("EPILOCATE_V2_S3_ADDRESSING_STYLE", "path")
        if addressing not in {"path", "virtual"}:
            fail("INVALID_STORAGE_ADDRESSING_STYLE", 503)
        self.server_side_encryption = os.environ.get("EPILOCATE_V2_S3_SERVER_SIDE_ENCRYPTION", "true").lower() == "true"
        client_config = Config(signature_version="s3v4", s3={"addressing_style": addressing})
        client_args = {"region_name": region, "aws_access_key_id": access_key, "aws_secret_access_key": secret_key, "config": client_config}
        self.client = boto3.client("s3", endpoint_url=endpoint, **client_args)
        self.presign_client = boto3.client("s3", endpoint_url=public_endpoint, **client_args)

    def put(self, body: bytes, content_type: str, prefix: str) -> str:
        key = f"{prefix}/{secrets.token_hex(24)}"
        kwargs = {"Bucket": self.bucket, "Key": key, "Body": body, "ContentType": content_type}
        if self.server_side_encryption:
            kwargs["ServerSideEncryption"] = "AES256"
        self.client.put_object(**kwargs)
        return key

    def delete(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_get(self, sl):
        if not sl.staging_object_key or not sl.staging_expires_at or aware(sl.staging_expires_at) <= now():
            fail("INPUT_EXPIRED", 410)
        seconds = min(300, int((aware(sl.staging_expires_at) - now()).total_seconds()))
        if seconds <= 0:
            fail("INPUT_EXPIRED", 410)
        return self.signed_key_get(sl.staging_object_key, seconds)

    def signed_asset_get(self, asset):
        if not asset.object_key:
            fail("ASSET_NOT_FOUND", 404)
        seconds = 300
        if asset.retention_until:
            seconds = min(seconds, int((aware(asset.retention_until) - now()).total_seconds()))
        if seconds <= 0:
            fail("ASSET_EXPIRED", 410)
        return self.signed_key_get(asset.object_key, seconds)

    def signed_key_get(self, key: str, seconds: int = 300):
        if not key or not 1 <= seconds <= 300:
            fail("INVALID_SIGNED_URL_REQUEST")
        return self.presign_client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=seconds)

    def read(self, key: str) -> tuple[bytes, str]:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")
