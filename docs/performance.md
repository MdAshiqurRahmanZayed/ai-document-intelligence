# Performance

Measured results for large documents and concurrent OCR. They come from `make bench`, which runs the slow tests in `backend/tests/integration/test_large_documents.py` inside the backend test container (Linux, Python 3.12, real PostgreSQL, Tesseract). The evaluation phase extends this with full end-to-end numbers.

## Measurements

Run on 2026-11-03 in Docker on the developer's laptop (host core count not recorded; the OCR speedup depends on it).

| Measurement | Result |
|---|---|
| Ingest 100 text pages (PDF) | 0.1 s |
| Ingest 1000 text pages (PDF) | 0.6 s (about 0.1 s per 100 pages) |
| Peak memory after 100 pages | 161 MB |
| Peak memory after 1000 pages | 165 MB |
| **Memory growth for 10x the pages** | **4 MB** (test fails above 50 MB) |
| OCR of 40 generated scanned pages, 1 page at a time | 6.6 s |
| OCR of the same 40 pages, 4 at a time | 2.8 s (**2.4x faster**, identical text and confidence) |

What they show:
- Ingest reads and saves pages incrementally, so memory stays flat as page count grows: ten times the pages cost 4 MB of peak memory.
- Concurrent OCR returns exactly the same pages as sequential OCR and finishes in well under half the time on this machine.

Limits of these numbers:
- The scanned pages are small generated images with one line of text, so a real 300 DPI invoice page takes longer than the 0.17 s per page seen here. Phase 6 measures real, degraded pages.
- Ingest used an in-memory storage double, so network time to the object store is not included.

## Sizing OCR

OCR concurrency is set by `OCR_CONCURRENCY` (default 4): the number of pages one OCR job reads at the same time. Each page read uses one core (Tesseract and OpenCV are pinned to one thread per call). Total parallelism is the number of worker processes (`celery worker --concurrency`) times `OCR_CONCURRENCY`, so keep that product near the number of cores available to the worker. Several documents on several worker processes, each reading 4 pages at once, can otherwise oversubscribe the machine.

## Rerunning

```
make bench
```

It prints lines starting with `[bench]` and fails if memory growth exceeds the bound. Update the table above when you rerun on different hardware.
