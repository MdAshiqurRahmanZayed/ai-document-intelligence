# Proposal

## Why

Manual testing showed a gap: when a document ends up `FAILED` (for example the queue was down at upload time), uploading the same file again returns `duplicate` pointing at the failed document and never retries it. The user has no way to recover except waiting for a reprocess endpoint planned for Phase 4.

## What Changes

- Uploading identical bytes whose existing document is `FAILED` now retries it: the error is cleared, the status goes back to `QUEUED`, a new job is queued, and the file is reported as `accepted` with the existing `document_id`.
- The retry is claimed atomically, so two simultaneous re-uploads queue exactly one job; the other is reported as `duplicate`.
- Documents in any other status are unchanged: still `duplicate`, nothing stored or queued.
- `docs/api.md` replaces its "limitation" note with this behavior.

**Out of scope:** a dedicated reprocess endpoint (Phase 4), retrying documents that are not `FAILED`, and changing the result status vocabulary.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `document-upload`: the duplicate detection requirement now retries a `FAILED` document instead of reporting it as a duplicate.

## Impact

- `backend/app/services/documents.py` (duplicate handling, shared queue step), tests in `backend/tests/integration/`, `docs/api.md`.
- No schema, dependency or API shape changes.
