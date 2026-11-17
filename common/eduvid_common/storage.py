"""S3-compatible object storage (MinIO) via boto3, path-style addressing."""
import mimetypes
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from .settings import get_settings


@lru_cache
def client():
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 5}),
    )


def _bucket() -> str:
    return get_settings().s3_bucket


def put_file(key: str, path: Path, content_type: str | None = None) -> None:
    ct = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    client().upload_file(str(path), _bucket(), key, ExtraArgs={"ContentType": ct})


def put_bytes(key: str, data: bytes, content_type: str) -> None:
    client().put_object(Bucket=_bucket(), Key=key, Body=data, ContentType=content_type)


def get_bytes(key: str) -> bytes:
    return client().get_object(Bucket=_bucket(), Key=key)["Body"].read()


def get_file(key: str, dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    client().download_file(_bucket(), key, str(dest))
    return dest


def exists(key: str) -> bool:
    try:
        client().head_object(Bucket=_bucket(), Key=key)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def delete(key: str) -> None:
    client().delete_object(Bucket=_bucket(), Key=key)


def delete_prefix(prefix: str) -> int:
    """Delete every object under `prefix` (must end in '/'). Returns how many were deleted."""
    if not prefix or not prefix.endswith("/"):
        raise ValueError(f"refusing to delete a prefix that does not end in '/': {prefix!r}")
    n = 0
    for page in client().get_paginator("list_objects_v2").paginate(Bucket=_bucket(), Prefix=prefix):
        keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if keys:
            client().delete_objects(Bucket=_bucket(), Delete={"Objects": keys, "Quiet": True})
            n += len(keys)
    return n


def presigned_url(key: str, expires_s: int = 3600) -> str:
    return client().generate_presigned_url(
        "get_object", Params={"Bucket": _bucket(), "Key": key}, ExpiresIn=expires_s
    )
