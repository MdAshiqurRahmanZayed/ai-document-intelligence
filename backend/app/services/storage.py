import asyncio
from typing import TYPE_CHECKING, BinaryIO, Protocol

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config

from app.core.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

# One chunk size for reading uploads and for S3 multipart parts, so they always agree.
CHUNK_SIZE = 8 * 1024 * 1024

# Files up to CHUNK_SIZE go in a single request; larger ones are sent in CHUNK_SIZE parts.
_TRANSFER = TransferConfig(multipart_threshold=CHUNK_SIZE, multipart_chunksize=CHUNK_SIZE)


class Storage(Protocol):
    async def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    def presigned_url(self, key: str, expires: int = 300) -> str: ...


class S3Storage:
    def __init__(self, client: "S3Client", bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        # boto3 is blocking, so it runs in a worker thread to keep the event loop free.
        await asyncio.to_thread(
            self._client.upload_fileobj,
            fileobj,
            self._bucket,
            key,
            ExtraArgs={"ContentType": content_type},
            Config=_TRANSFER,
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    def presigned_url(self, key: str, expires: int = 300) -> str:
        # The host comes from S3_ENDPOINT_URL (a Docker-internal name). A browser-facing URL
        # needs a public endpoint; that is a concern for the document viewer, not this change.
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires,
        )


def build_s3_storage(settings: Settings) -> S3Storage:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        region_name=settings.s3_region,
        # Longer read timeout than the readiness check: uploads legitimately take a while.
        config=Config(
            connect_timeout=5,
            read_timeout=60,
            retries={"max_attempts": 0},
            s3={"addressing_style": "path"},  # required by SeaweedFS (no bucket subdomains)
        ),
    )
    return S3Storage(client, settings.s3_bucket)
