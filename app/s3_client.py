import os
import uuid
from typing import Optional

import boto3


def _client():
    region = os.getenv("AWS_REGION")
    if not region:
        raise RuntimeError("AWS_REGION is not configured")
    return boto3.client("s3", region_name=region)


def _bucket() -> str:
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        raise RuntimeError("S3_BUCKET is not configured")
    return bucket


def upload_image(file_obj, folder: str, filename: Optional[str] = None) -> str:
    bucket = _bucket()
    key_name = filename or f"{uuid.uuid4().hex}.jpg"
    key = f"{folder.rstrip('/')}/{key_name}"
    client = _client()
    client.upload_fileobj(
        file_obj,
        bucket,
        key,
        ExtraArgs={"ContentType": "image/jpeg"},
    )
    return key


def upload_raw(content: str, folder: str, filename: str) -> str:
    bucket = _bucket()
    key = f"{folder.rstrip('/')}/{filename}.json"
    client = _client()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="application/json",
    )
    return key


def presigned_url(key: str, expires_seconds: int = 3600) -> str:
    bucket = _bucket()
    client = _client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_seconds,
    )
