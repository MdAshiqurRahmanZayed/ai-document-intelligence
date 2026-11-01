---
name: git-conventions
description: >
  Generate Conventional Commits messages, branch names, PR titles, and PR
  descriptions for this repository, and run commits that follow them. Works
  with or without a ticket/task key — when no ticket system applies, use plain
  `type(scope): description` instead of forcing an ID. Trigger on "commit", "commit
  message", "write a commit", "branch name", "PR description", "PR title",
  "conventional commits", "what should I commit this as", "help me with my
  PR", or when the user pastes a diff and asks what to write. Also trigger on
  "review/fix this commit message" and after an OpenSpec change is archived.
---

# Git Conventions

Generate commit messages, branch names, PR titles, and PR descriptions that
follow Conventional Commits. Every output must be usable as-is — no
placeholders left for the developer to fill in unless information genuinely
cannot be inferred from the diff/context given.

**Ticket keys are optional.** This project has no ticket tracker. Do not
invent one and do not leave a `<ticket-id>` placeholder — write
`type(scope): description` and skip ticket footers. OpenSpec change IDs play
the tracking role instead (see §6).

---

## 0. Hard rules

1. Never commit secrets: check staged files for `.env`, keys, tokens before
   committing. `.env.example` is fine.
2. Never `--no-verify`, never force-push, never amend a pushed commit
   unless the user explicitly asks.
3. **Never push by default.** Commit locally only. Run `git push` only when
   the user explicitly asks for a push in that message; even then, first
   state remote, branch, and the commits to be pushed
   (`git log @{u}..HEAD --oneline`, or all commits on a new branch) and wait
   for confirmation. Approval for one push does not carry over to the next.
4. **Protected branches: `main`, `development`, `production`.** Before
   committing directly on one of them, merging into one, rebasing one, or
   cherry-picking onto one: stop, tell the user which branch and what
   operation, and wait for explicit approval. Check the current branch with
   `git branch --show-current` before every commit. Exception: the very first
   commit in an empty repo still needs approval, but note it is expected.

---

## 1. Commit Messages

### Format

```
<type>(<scope>): <short description>

<optional body>

<optional footer(s)>
```

### Rules

1. **Type** — exactly one of these (nothing else is valid):

   | Type       | Use for |
   |------------|---------|
   | `feat`     | New feature visible to a user, API consumer, or another developer |
   | `fix`      | Bug fix |
   | `refactor` | Internal restructuring — no new features, no bug fixes |
   | `perf`     | Performance improvement. State the measured improvement in the body |
   | `test`     | Adding or updating tests only. No production code changes |
   | `docs`     | Documentation only — README, ADRs, specs, code comments, runbooks |
   | `build`    | Build system, dependencies, Dockerfiles, packaging |
   | `ci`       | CI/CD pipelines, deployment scripts |
   | `chore`    | Maintenance that doesn't fit above. Use sparingly |

   **Forbidden types:** `misc`, `update`, `wip`, `changes`, or anything not in
   the table above.

2. **Scope** — optional but strongly preferred. Use one from this project's
   scope list; pick the most specific that fits:

   | Scope | Area |
   |---|---|
   | `api` | FastAPI routes, request/response schemas, auth, rate limit |
   | `db` | SQLAlchemy models, Alembic migrations |
   | `storage` | S3-compatible storage adapter |
   | `worker` | Celery app, task orchestration, retries, queues |
   | `pdf` | PDF text/table extraction, scanned-page detection |
   | `ocr` | OCR, image preprocessing, vision fallback |
   | `spreadsheet` | XLSX/XLS/CSV parsing, column mapping |
   | `llm` | LangChain/Gemini client, chains, prompts, embeddings |
   | `extraction` | Invoice schema, segmentation, normalization, grounding |
   | `validation` | Validation rules, duplicates, cross-verification |
   | `search` | Keyword, semantic, hybrid search |
   | `web` | Next.js frontend |
   | `eval` | Evaluation dataset, harness, metrics, report |
   | `openspec` | Specs, change proposals, OpenSpec config |
   | `docker` | docker-compose, container setup |
   | `ci` | GitHub Actions |
   | `deps` | Dependency bumps (with `build`) |
   | `repo` | Repo-wide setup (gitignore, Makefile, editor config) |

   Changes spanning many areas: pick the dominant one, or omit scope.
   Do not invent new scopes casually — add to this table first.

3. **Description** (subject line after the colon):
   - Imperative mood: "add", not "added" or "adds"
   - Think: "If applied, this commit will ___"
   - Starts lowercase, no trailing period
   - Total line (type + scope + colon + space + description) ≤ 72 characters
   - Describes **what the change does**, not which files were touched

4. **Body** (blank line after the subject):
   - Required for any non-trivial change
   - Explains **why** the change was made — problem, approach chosen,
     alternatives considered, side effects, migration steps
   - Wrap lines at 72 characters
   - For `perf`: include measured before/after numbers

5. **Breaking changes**:
   - Inline: `feat(api)!: replace upload response shape`
   - Or footer: `BREAKING CHANGE: upload now returns 202 with job ids`
   - Prefer the footer form when migration steps are non-trivial

6. **Footers** — only include the ones that apply:
   ```
   Refs openspec/changes/<change-id>   (when commit implements an OpenSpec change)
   Reviewed-by: Name
   BREAKING CHANGE: description of what breaks
   ```

### Atomic commits

- One logical change per commit. Don't mix refactor + feature, or
  formatting + logic.
- Tests for a feature go in the same commit as the feature (`feat`), not a
  separate `test` commit. Use `test` only for test-only changes.
- Migrations go with the model change that needs them.

### Forbidden commit messages

Never produce: `fix`, `wip`, `updates`, `asdf`, `merge branch '...'`,
`fix bug`, `review changes`, `address comments`, or any commit with no
type prefix.

### Examples

**Straightforward fix:**
```
fix(spreadsheet): detect semicolon delimiter in latin-1 csv files
```

**Feature with body:**
```
feat(ocr): add opencv preprocessing before tesseract

Low-quality scans produced OCR confidence below 40% on skewed and noisy
pages. Deskew, denoise, CLAHE, and adaptive thresholding run before
Tesseract; pages still below threshold fall back to Gemini vision.

Refs openspec/changes/add-image-ocr
```

**Performance:**
```
perf(worker): fan out pdf pages with celery chord

1000-page PDFs were processed sequentially in one task. Per-page tasks
in a chord cut wall time from 14m to 3m20s on 4 workers.
```

**Breaking change:**
```
feat(api)!: change document list pagination to cursor-based

All list endpoints now require a `cursor` parameter instead of
`page`/`page_size`. Offset-based pagination is removed.

BREAKING CHANGE: clients using offset pagination must migrate to
cursor-based pagination.
```

---

## 2. Branch Names

### Format

```
<type>/<scope>-<short-slug>
```

When the branch implements an OpenSpec change, the slug should match the
change ID:

```
feat/storage-add-upload-and-storage     ← change: add-upload-and-storage
feat/ocr-add-image-ocr                  ← change: add-image-ocr
```

### Examples

```
feat/extraction-invoice-segmentation
fix/spreadsheet-csv-delimiter-detection
refactor/worker-task-retry-policy
docs/repo-architecture-diagram
chore/deps-upgrade-langchain
```

### Forbidden branch names

- Person's name: `zayed-stuff`
- Unstructured: `new-auth-flow-v2-final`
- Type missing: `upload-endpoint`

---

## 3. PR Titles

Same Conventional Commits format as the commit subject.

- Single-commit PR: title and commit subject should match.
- Squash-merged PR: title becomes the final commit subject — get it right.

### Forbidden PR titles

- Restating the branch name as a sentence
- Vague: `Update X` or `Fix X` without saying what

---

## 4. PR Description

Five-section template. Trivial PRs (typo fixes, dependency bumps) may
collapse to a single sentence under **What**.

```markdown
## What
One paragraph: what this PR changes, written for a reviewer who
hasn't seen any prior discussion.

## Why
One paragraph: the problem this solves or the goal it advances.
Link the OpenSpec change (`openspec/changes/<id>/proposal.md`) when
one exists — otherwise state the motivation directly.

## How
Bullet list of the technical approach. Note any non-obvious choices,
deviations from convention, or trade-offs accepted.

## Verification
How to confirm this works: test commands run (with results), manual
steps taken, screenshots, before/after behavior.

## Risks & Follow-up
Known limitations, deferred work, anything reviewer/maintainer
should watch for after merge.
```


---

## 5. How to Use This Skill

**Diff or change description given:**
1. Run `git status` and `git diff --staged` (or `git diff`) to see the change.
2. Identify the correct type from the change content.
3. Infer scope from the scope table in §1.
4. Write the subject in imperative mood, ≤72 chars.
5. Write a body explaining why (skip only for truly trivial changes).
6. Add footers only for what actually applies.

**Asked to commit:**
1. Check staged/untracked files for secrets and junk (`.env`, `node_modules`,
   data dumps). Stage explicit paths, not `git add -A`, when unsure.
2. Split into atomic commits if the diff mixes concerns.
3. Commit with a HEREDOC so formatting survives:
   ```bash
   git commit -F - <<'EOF'
   feat(api): add multi-file document upload endpoint

   Body here.
   EOF
   ```
4. Verify with `git log -1 --format=%B` that the message landed as intended.

**PR description requested:**
1. Read the commits in the PR (`git log main..HEAD`).
2. Fill in all five sections.
3. Flag any section where you're guessing and tell the user to verify.

**Review/fix existing commits:**
1. Identify what's wrong (missing type, vague description, no body,
   etc).
2. Provide the corrected version.
3. Briefly explain what was fixed and why.

**Output format:**
- Always output the commit message / branch name / PR description in a
  fenced code block so it's easy to copy.
- Number multiple commits when generating a series.
- For PR descriptions, use the markdown template directly.

---

## 6. OpenSpec Integration

Workflow per change: `/opsx:propose` → `/opsx:apply` → verify → tests →
`/opsx:archive` → commit.

- Commit after archive so specs and code land together.
- Proposal-only commits (spec work before implementation):
  `docs(openspec): propose add-image-ocr change`
- Implementation commit: type from the change content, footer
  `Refs openspec/changes/<change-id>` (archived path is fine too).
- Large changes may span several atomic commits; each references the
  same change ID.
