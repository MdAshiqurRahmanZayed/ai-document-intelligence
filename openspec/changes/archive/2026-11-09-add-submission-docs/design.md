# Design

## Context

The system runs end to end, and the web interface and Flower were just merged (PR #8). Docs today: `README.md` (run, health, tests, configuration), `docs/api.md`, `docs/database-schema.md`, `docs/frontend.md`, `docs/monitoring.md`, `docs/testing.md`, `docs/performance.md`. There is no diagram, disclosure or security page. `.env.example` is not readable by the assistant (a permission rule), so the user edits it. The `add-frontend-and-flower` change is merged but not archived; its tasks 1.4, 1.5 and 7.3 are the user's checks. See proposal.md for scope and motivation.

## Goals / Non-Goals

**Goals:**
- A reviewer with Docker and `make` can run it, test it and judge it from the docs alone.
- Every claim in the docs is checked against the repository, not written from memory.
- Honest limits, including the missing evaluation.

**Non-Goals:**
- No new runtime behaviour, endpoints or schema.
- No evaluation, ADRs or recorded video.

## Decisions

1. **Keep the README as the entry point and move detail out.** Quick start, config, tests and limits stay short in the README; the diagram goes in the README (Mermaid renders on GitHub, no image files to keep in sync). Longer material goes to `docs/`: `docs/security.md`, `docs/ai-disclosure.md`. Alternative: one long README. Rejected, it buries the quick start.
2. **Mermaid diagram, not an exported image.** It lives in text next to the code and reviewers see it without tools. Alternative: draw.io export. Rejected: binary file, drifts.
3. **Facts come from the repo.** For each doc, read the compose file, config and routes first (services, queues, env variables, endpoints). The diagram and security notes cite files, so each claim is traceable.
4. **`.env.example` is the user's edit.** The plan gives the exact text; the assistant cannot read or write the file. A check task compares the variables the code reads (`config.py`, `docker-compose.yml`, web env) with the file's contents pasted by the user.
5. **Clean-clone verification is a task for the user's machine.** Running Docker from a fresh clone is the only real proof of the quick start. Results go in the PR description.
6. **Password-protected PDF test.** `PdfViewer` is loaded with `react-pdf` in tests, which needs the browser PDF worker. The test mocks `react-pdf` so `Document` calls its `onPassword` prop, and asserts the message appears and no password prompt is raised. Alternative: a real encrypted PDF in a browser. Rejected: slow and already covered manually.
7. **Archive uses the existing workflow.** `/opsx:archive add-frontend-and-flower` after the user confirms tasks 1.4, 1.5 and 7.3 (or accepts archiving with them open).

## Risks / Trade-offs

- **Docs drift from the code.** Mitigated by reading the source for each fact and keeping the diagram small.
- **Missing evaluation.** The brief asks for one; the README says it was not done and why. This is a known gap, not hidden.
- **Clean-clone run may reveal setup bugs late.** Reserve time for fixes after the clean-clone run.

## Open Questions

- None open. `add-frontend-and-flower` was archived with tasks 1.4, 1.5 and 7.3 still unticked, at the user's choice.
