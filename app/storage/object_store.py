"""S3-compatible object storage with local fallback."""
from __future__ import annotations

import importlib
import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Optional, Union


class ObjectStore:
    """Unified artifact storage — ``local`` or ``s3`` backend."""

    def __init__(
        self,
        *,
        backend: str = "local",
        local_root: Path | str = "uploads",
        bucket: str = "ai-grader",
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = "us-east-1",
    ) -> None:
        self.backend = backend.strip().lower()
        self.local_root = Path(local_root)
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self._client = None

    def _s3(self):
        if self._client is not None:
            return self._client
        try:
            boto3 = importlib.import_module("boto3")
        except ImportError as exc:
            raise RuntimeError(
                "boto3 required for S3 object store — pip install boto3"
            ) from exc
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )
        return self._client

    def _local_path(self, key: str) -> Path:
        key = key.lstrip("/").replace("\\", "/")
        if ".." in key.split("/"):
            raise ValueError(f"invalid object key: {key}")
        return self.local_root / key

    def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        if self.backend == "s3":
            self._s3().put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            return f"s3://{self.bucket}/{key}"
        path = self._local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def put_file(self, key: str, source: Union[str, Path]) -> str:
        src = Path(source)
        if self.backend == "s3":
            extra = {}
            suffix = src.suffix.lower()
            if suffix in (".json",):
                extra["ContentType"] = "application/json"
            elif suffix in (".png",):
                extra["ContentType"] = "image/png"
            elif suffix in (".jpg", ".jpeg"):
                extra["ContentType"] = "image/jpeg"
            with open(src, "rb") as fh:
                self._s3().put_object(Bucket=self.bucket, Key=key, Body=fh, **extra)
            return f"s3://{self.bucket}/{key}"
        dest = self._local_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return str(dest)

    def get_bytes(self, key: str) -> bytes:
        if self.backend == "s3":
            obj = self._s3().get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()
        return self._local_path(key).read_bytes()

    def exists(self, key: str) -> bool:
        if self.backend == "s3":
            try:
                self._s3().head_object(Bucket=self.bucket, Key=key)
                return True
            except Exception:
                return False
        return self._local_path(key).is_file()

    def uri(self, key: str) -> str:
        if self.backend == "s3":
            return f"s3://{self.bucket}/{key}"
        return str(self._local_path(key))

    def ensure_bucket(self) -> None:
        if self.backend != "s3":
            self.local_root.mkdir(parents=True, exist_ok=True)
            return
        client = self._s3()
        try:
            client.head_bucket(Bucket=self.bucket)
        except Exception:
            params: dict = {"Bucket": self.bucket}
            if self.endpoint_url and "amazonaws.com" not in (self.endpoint_url or ""):
                params["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
            try:
                client.create_bucket(**params)
            except Exception:
                pass


@lru_cache(maxsize=1)
def get_object_store() -> ObjectStore:
    backend = os.environ.get("AI_GRADER_OBJECT_STORE", "local").strip().lower()
    return ObjectStore(
        backend=backend,
        local_root=os.environ.get("AI_GRADER_UPLOAD_ROOT", "uploads"),
        bucket=os.environ.get("AI_GRADER_S3_BUCKET", "ai-grader"),
        endpoint_url=os.environ.get("AI_GRADER_S3_ENDPOINT") or None,
        access_key=os.environ.get("AI_GRADER_S3_ACCESS_KEY") or None,
        secret_key=os.environ.get("AI_GRADER_S3_SECRET_KEY") or None,
        region=os.environ.get("AI_GRADER_S3_REGION", "us-east-1"),
    )
