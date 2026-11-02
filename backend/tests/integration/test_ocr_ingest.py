import threading
import time

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Page
from app.pipeline.ocr import OcrResult
from app.services import ocr_ingest
from app.services.ocr_ingest import ocr_pages
from tests import image_samples as samples
from tests.fakes import FakeStorage
from tests.helpers import make_document


async def document_with_pages(
    session: AsyncSession, storage: FakeStorage, pages: list[Page], images: dict[int, bytes]
) -> Document:
    document = make_document(source_type="image", mime="image/png")
    session.add(document)
    await session.commit()
    for page in pages:
        page.document_id = document.id
        if page.page_no in images:
            page.image_key = f"pages/{document.id}/{page.page_no}.png"
            storage.objects[page.image_key] = (images[page.page_no], "image/png")
        session.add(page)
    await session.commit()
    return document


async def pages_of(session: AsyncSession, document: Document) -> list[Page]:
    result = await session.scalars(
        select(Page)
        .where(Page.document_id == document.id)
        .order_by(Page.page_no)
        .execution_options(populate_existing=True)
    )
    return list(result)


async def test_scanned_pages_are_read_and_native_pages_are_left_alone(
    session: AsyncSession,
) -> None:
    storage = FakeStorage()
    document = await document_with_pages(
        session,
        storage,
        [Page(page_no=1, method="native", text="embedded"), Page(page_no=2, method="scanned")],
        {2: samples.encode(samples.text_image())},
    )

    await ocr_pages(session, storage, document)

    native, scanned = await pages_of(session, document)
    assert (native.text, native.method, native.ocr_confidence) == ("embedded", "native", None)
    assert scanned.method == "ocr" and "INVOICE" in (scanned.text or "")
    assert scanned.ocr_confidence is not None and scanned.ocr_confidence > 0.8


async def test_rerun_reads_only_the_pages_still_scanned(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await document_with_pages(
        session,
        storage,
        [
            Page(page_no=1, method="ocr", text="already done", ocr_confidence=0.5),
            Page(page_no=2, method="scanned"),
        ],
        {1: samples.encode(samples.text_image()), 2: samples.encode(samples.text_image())},
    )

    await ocr_pages(session, storage, document)

    done, fresh = await pages_of(session, document)
    assert (done.text, done.ocr_confidence) == ("already done", 0.5)
    assert "INVOICE" in (fresh.text or "")


async def test_blank_page_is_saved_empty_without_failing(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await document_with_pages(
        session,
        storage,
        [Page(page_no=1, method="scanned")],
        {1: samples.encode(samples.blank_image())},
    )

    await ocr_pages(session, storage, document)

    (page,) = await pages_of(session, document)
    assert (page.text, page.method, page.ocr_confidence) == ("", "ocr", None)


class ReadLog:
    """Counts how many reads overlap in time; fails the read of the page named in `fail_on`."""

    def __init__(self, fail_on: bytes | None = None) -> None:
        self.active = self.peak = 0
        self.fail_on = fail_on
        self._lock = threading.Lock()

    def read(self, png: bytes) -> OcrResult:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(0.05)  # long enough for reads to overlap
            if png == self.fail_on:
                raise RuntimeError("engine glitch")
            return OcrResult(f"text of {png.decode()}", 0.9)
        finally:
            with self._lock:
                self.active -= 1


def use_stub_engine(monkeypatch: pytest.MonkeyPatch, log: ReadLog) -> None:
    class StubEngine:
        def read(self, png: bytes) -> OcrResult:
            return log.read(png)

    monkeypatch.setattr(ocr_ingest, "OcrEngine", StubEngine)


async def twelve_scanned_pages(session: AsyncSession, storage: FakeStorage) -> Document:
    pages = [Page(page_no=n, method="scanned") for n in range(1, 13)]
    images = {n: f"page-{n}".encode() for n in range(1, 13)}
    return await document_with_pages(session, storage, pages, images)


async def test_reads_overlap_but_never_exceed_the_limit(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = ReadLog()
    use_stub_engine(monkeypatch, log)
    storage = FakeStorage()
    document = await twelve_scanned_pages(session, storage)

    await ocr_pages(session, storage, document, concurrency=4)

    assert 1 < log.peak <= 4
    assert {p.method for p in await pages_of(session, document)} == {"ocr"}


async def test_a_limit_of_one_gives_the_same_result(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_stub_engine(monkeypatch, ReadLog())
    results = []
    for limit in (1, 4):
        storage = FakeStorage()
        document = await twelve_scanned_pages(session, storage)
        await ocr_pages(session, storage, document, concurrency=limit)
        results.append(
            [(p.text, p.method, p.ocr_confidence) for p in await pages_of(session, document)]
        )

    assert results[0] == results[1]
    assert results[0][0] == ("text of page-1", "ocr", 0.9)


async def test_a_failed_read_keeps_the_batches_already_saved(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_stub_engine(monkeypatch, ReadLog(fail_on=b"page-12"))  # page 12 is in the second batch
    storage = FakeStorage()
    document = await twelve_scanned_pages(session, storage)

    with pytest.raises(RuntimeError):
        await ocr_pages(session, storage, document, concurrency=4)

    methods = [p.method for p in await pages_of(session, document)]
    assert methods == ["ocr"] * 10 + ["scanned"] * 2
