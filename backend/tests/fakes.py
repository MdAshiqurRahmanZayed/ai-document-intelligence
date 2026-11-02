import uuid
from typing import BinaryIO


class FakeStorage:
    """In-memory stand-in for S3Storage."""

    def __init__(self, fail_put: bool = False) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.fail_put = fail_put

    async def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        if self.fail_put:
            raise RuntimeError("storage is down")
        self.objects[key] = (fileobj.read(), content_type)

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def presigned_url(self, key: str, expires: int = 300) -> str:
        return f"http://fake-storage/{key}?expires={expires}"


class RecordingEnqueue:
    """Records queued document ids instead of talking to a broker."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[uuid.UUID] = []
        self.fail = fail

    def __call__(self, document_id: uuid.UUID) -> None:
        if self.fail:
            raise ConnectionError("broker is down")
        self.calls.append(document_id)
