import io
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.services.storage import CHUNK_SIZE, S3Storage, build_s3_storage


async def test_put_sends_content_type_and_uses_chunk_size() -> None:
    client = MagicMock()
    await S3Storage(client, "documents").put(
        "raw/x/original.pdf", io.BytesIO(b"x"), "application/pdf"
    )

    args, kwargs = client.upload_fileobj.call_args
    assert args[1:] == ("documents", "raw/x/original.pdf")
    assert kwargs["ExtraArgs"] == {"ContentType": "application/pdf"}
    assert kwargs["Config"].multipart_threshold == CHUNK_SIZE
    assert kwargs["Config"].multipart_chunksize == CHUNK_SIZE


async def test_delete_removes_the_object() -> None:
    client = MagicMock()
    await S3Storage(client, "documents").delete("raw/x/original.pdf")
    client.delete_object.assert_called_once_with(Bucket="documents", Key="raw/x/original.pdf")


def test_presigned_url_is_requested_for_get_with_expiry() -> None:
    client = MagicMock()
    client.generate_presigned_url.return_value = "http://signed"

    assert S3Storage(client, "documents").presigned_url("raw/x/original.pdf", 60) == "http://signed"
    client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "documents", "Key": "raw/x/original.pdf"},
        ExpiresIn=60,
    )


def test_real_client_uses_path_style_addressing(valid_env: pytest.MonkeyPatch) -> None:
    storage = build_s3_storage(Settings(_env_file=None))
    config: Any = storage._client.meta.config
    assert config.s3["addressing_style"] == "path"
