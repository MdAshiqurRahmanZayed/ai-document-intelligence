# Tasks

## 1. Retry on re-upload

- [x] 1.1 In `app/services/documents.py`, extract the enqueue-and-handle-failure step into one helper and add an atomic claim (`UPDATE ... WHERE status = 'FAILED' RETURNING id`) used wherever an existing document is found (initial lookup and the unique-constraint race), with a comment explaining why it must be atomic; verify `ruff` and `mypy` are clean
- [x] 1.2 Add service tests for: failed document re-uploaded is `accepted` with the same id, `QUEUED`, error cleared, one new job, no new object; retry that fails to queue is `rejected` `queue_unavailable` and stays `FAILED`; a non-failed document is still `duplicate`; a second claim on the same failed document gets `duplicate`; and one API test for the re-upload after a queue failure; verify `make test` passes
- [x] 1.3 Replace the limitation note in `docs/api.md` with the new behavior, and verify by re-uploading a failed document against the running stack (stop Redis, upload, start Redis, upload again, expect `accepted` and `COMPLETED`)

## Workflow follow-up

- Archive with `/opsx:archive`, commit on `feat/storage-add-upload-and-storage`, push only when asked.
