import asyncio
import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO, Literal

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, DocumentStatus
from app.services.filetypes import detect_type
from app.services.storage import CHUNK_SIZE, Storage

log = structlog.get_logger()

Outcome = Literal["accepted", "duplicate", "rejected"]


@dataclass
class UploadResult:
    filename: str
    status: Outcome
    document_id: uuid.UUID | None = None
    reason: str | None = None


def _rejected(filename: str, reason: str, document_id: uuid.UUID | None = None) -> UploadResult:
    return UploadResult(filename, "rejected", document_id, reason)


async def ingest_upload(
    *,
    session: AsyncSession,
    storage: Storage,
    enqueue: Callable[[uuid.UUID], None],
    filename: str,
    fileobj: BinaryIO,
    max_bytes: int,
) -> UploadResult:
    """Validate one uploaded file, store it, record it and queue its processing job.

    Order matters: the object is written before the row exists, so a storage failure can
    never leave a document record pointing at nothing.
    """
    # Read in CHUNK_SIZE pieces so memory stays flat however large the file is. The hash and
    # the size limit are handled in the same pass.
    digest = hashlib.sha256()
    size = 0
    head = b""
    while chunk := await asyncio.to_thread(fileobj.read, CHUNK_SIZE):
        if not head:
            head = chunk
        size += len(chunk)
        if size > max_bytes:
            return _rejected(filename, "file_too_large")
        digest.update(chunk)

    if size == 0:
        return _rejected(filename, "empty_file")

    # Detection may seek (zip check) and always rewinds, so the upload below starts at byte 0.
    detected = detect_type(head, filename, fileobj)
    if detected is None:
        return _rejected(filename, "unsupported_type")
    fileobj.seek(0)

    sha256 = digest.hexdigest()
    existing = await _find_by_hash(session, sha256)
    if existing is not None:
        return UploadResult(filename, "duplicate", existing)

    document_id = uuid.uuid4()
    # Key is built from the id and a type-derived extension only; the client filename never
    # reaches the storage layer, which rules out path tricks like "../../x".
    key = f"raw/{document_id}/original{detected.extension}"

    try:
        await storage.put(key, fileobj, detected.mime)
    except Exception:
        log.exception("storage_put_failed", key=key)
        return _rejected(filename, "storage_error")

    document = Document(
        id=document_id,
        filename=filename[:255],
        mime=detected.mime,
        size=size,
        sha256=sha256,
        storage_key=key,
        status=DocumentStatus.UPLOADED,
        source_type=detected.source_type,
    )
    session.add(document)
    try:
        await session.commit()
    except IntegrityError:
        # Another request stored identical bytes between our lookup and this insert. The unique
        # hash constraint picked the winner; drop our copy and point at theirs.
        await session.rollback()
        await _discard(storage, key)
        winner = await _find_by_hash(session, sha256)
        if winner is None:
            raise
        return UploadResult(filename, "duplicate", winner)

    # QUEUED is committed before enqueueing: otherwise a fast worker could set PROCESSING
    # and this request would then overwrite it.
    document.status = DocumentStatus.QUEUED
    await session.commit()
    try:
        # .delay() is blocking network I/O, so it runs off the event loop.
        await asyncio.to_thread(enqueue, document_id)
    except Exception:
        log.exception("enqueue_failed", document_id=str(document_id))
        document.status = DocumentStatus.FAILED
        document.error_code = "queue_unavailable"
        document.error_message = "Could not hand the document to the processing queue."
        await session.commit()
        return _rejected(filename, "queue_unavailable", document_id)

    return UploadResult(filename, "accepted", document_id)


async def get_document(session: AsyncSession, document_id: uuid.UUID) -> Document | None:
    return await session.scalar(
        select(Document).where(Document.id == document_id).options(selectinload(Document.events))
    )


async def _find_by_hash(session: AsyncSession, sha256: str) -> uuid.UUID | None:
    return await session.scalar(select(Document.id).where(Document.sha256 == sha256))


async def _discard(storage: Storage, key: str) -> None:
    # Best effort: a leftover object is harmless garbage, not a reason to fail the request.
    try:
        await storage.delete(key)
    except Exception:
        log.warning("storage_delete_failed", key=key, exc_info=True)
