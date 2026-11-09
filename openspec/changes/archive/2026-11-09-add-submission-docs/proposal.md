# Proposal

## Why

The system works end to end, but the submission is not yet usable by a reviewer: the README predates the web interface, there is no architecture diagram, AI disclosure or security notes, `.env.example` is out of date (Flower lines, API key, model IDs), and the merged `add-frontend-and-flower` change is not archived. The deadline is close and no real labelled data is available for an evaluation, so the work is cut to what the brief requires and a reviewer can verify.

## What Changes

- Archive the merged `add-frontend-and-flower` change and sync its specs into `openspec/specs/`.
- Rewrite the README so a stranger can run, test and understand the system: quick start, configuration, how to test, design choices, known limits.
- Add one architecture diagram (Mermaid, in the README) showing upload to search.
- Add a half-page AI disclosure stating what was AI-assisted and how it was checked.
- Add short security notes (API key, server-side proxy, file serving, prompt-injection guard, secrets).
- State plainly in the README that the evaluation (dataset, report, `make eval`) was not done and why.
- Make `.env.example` complete and current: Flower variables, `API_KEY`, current model IDs, no `NEXT_PUBLIC_API_URL`.
- Add the missing test for the password-protected PDF message in the viewer.
- Verify from a clean clone: `make up`, `make migrate`, `make check`, `make e2e`.

Out of scope: the evaluation dataset, `run_eval.py`, `eval/results/report.md`, ADRs, a heavy security checklist, new features, UI polish, a recorded video.

## Capabilities

### New Capabilities
- `submission-documentation`: the documents a reviewer needs (README, diagram, AI disclosure, security notes, honest limits) and a documented, reproducible setup.

### Modified Capabilities

## Impact

- Files: `README.md`, `.env.example`, new `docs/` pages, `frontend/src/components/PdfViewer.test.tsx` (new), `openspec/` (archive and sync).
- No API, schema or runtime behaviour changes. `docs/api.md` and `docs/database-schema.md` are only checked for accuracy.
- `.env.example` is edited by the user (the assistant has no access to it).
