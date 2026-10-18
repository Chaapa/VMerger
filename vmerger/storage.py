import hashlib
from pathlib import Path

import boto3
from botocore.config import Config

from .config import settings


def client():
    s = settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=60,
            proxies={},
            retries={"max_attempts": 3},
            s3={"addressing_style": "path"},
        ),
    )


def ensure_bucket():
    s3 = client()
    if settings().s3_bucket not in [x["Name"] for x in s3.list_buckets()["Buckets"]]:
        s3.create_bucket(Bucket=settings().s3_bucket)


def upload_verified(path: Path, key: str, content_type: str) -> dict:
    s3 = client()
    bucket = settings().s3_bucket
    with path.open("rb") as stream:
        expected = hashlib.file_digest(stream, "sha256").hexdigest()
    s3.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": content_type})
    # ETag is not a checksum for multipart objects. Read back and hash actual S3 bytes.
    response = s3.get_object(Bucket=bucket, Key=key)
    digest = hashlib.sha256()
    size = 0
    with response["Body"] as body:
        for chunk in iter(lambda: body.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    if digest.hexdigest() != expected or size != path.stat().st_size:
        raise ValueError("S3 verification failed")
    return {"sha256": expected, "byte_size": size, "etag": response.get("ETag", "")}


def download(key: str, path: Path):
    client().download_file(settings().s3_bucket, key, str(path))


def delete(key: str):
    client().delete_object(Bucket=settings().s3_bucket, Key=key)
