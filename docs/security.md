# Security notes

What the system does to protect itself and its data, where each measure lives, and what it does not cover. It is built to run locally or on a trusted network; the gaps below matter before any public deployment.

## Measures

| Area | What is done | Where |
|---|---|---|
| API access | Every data endpoint requires the header `X-API-Key` when `API_KEY` is set. The comparison is constant-time, so response time does not reveal a guessed key. Health endpoints stay open for probes. | `backend/app/api/auth.py`, wired in `backend/app/main.py` |
| Key never reaches the browser | The browser calls only the web server (`/api/backend/*`, `/api/files/*`). The web server adds the key from its own environment. The key is read only by the two route handlers, and a test fails if any other source file reads it or exposes it as a `NEXT_PUBLIC_` value. The built bundle was searched for the key and does not contain it. | `frontend/src/lib/proxy.ts`, `frontend/src/lib/keyguard.test.ts` |
| Proxy allow-list | Only documents, search, chat, jobs, cross-verify and `readyz` are forwarded; only GET, POST and PATCH, plus DELETE for one path, `chat/sessions/<uuid>`; path segments must match a strict pattern (no `..` or slashes); redirects are not followed; the upstream's headers are dropped except the content type (no cookies pass through); upstream failures return a generic 502 without internal detail. | `frontend/src/lib/proxy.ts`, `proxy.test.ts` |
| Serving stored files | Originals are streamed by the web server from a short-lived signed storage link (5 minutes). The id must be a UUID. Responses carry `X-Content-Type-Options: nosniff` and `Content-Security-Policy: sandbox`, so an uploaded file cannot run scripts in the app's origin. | `frontend/src/lib/proxy.ts` (`forwardFile`), `backend/app/services/storage.py` |
| Upload validation | The file type is decided from the content (signatures), not the name; for OLE2 spreadsheets and CSV the extension must also agree; size is capped by `MAX_UPLOAD_MB` (default 100); the browser also checks type, emptiness and size before sending. | `backend/app/services/filetypes.py`, `backend/app/core/config.py`, `frontend/src/lib/upload.ts` |
| Prompt injection | Page text is placed inside `<document>` tags and the prompt says it is data, to be read and never obeyed. The model only fills a fixed schema; it cannot call tools or take actions. Values the model quotes are checked against the page text, and arithmetic is recomputed in code, so an injected "set the total to 0" shows up as a validation finding rather than a silent change. | `backend/prompts/v1/extract_invoice.md`, `backend/app/pipeline/grounding.py`, `backend/app/validation/rules.py` |
| Chat | The chunks sit inside numbered `<source>` tags and the prompt says they are data, never to be obeyed; a chunk cannot close its own tag (the tag text is neutralised). The earlier messages from the browser are untrusted: length and role are checked, and they reach only the question rewrite, never the answering call. The model only returns text; it cannot call tools. Citations that name no retrieved source are dropped. Logs hold model name, token counts and sizes, never questions, document text or answers. With a session, the history comes from the stored messages and the browser's copy is ignored. | `backend/prompts/v1/chat.md`, `backend/app/llm/chat.py`, `backend/app/services/chat.py`, `backend/app/schemas/chat.py` |
| Cross-origin | CORS allows only `WEB_ORIGIN`. | `backend/app/main.py` |
| Secrets | Only in `.env`, which is git-ignored; `.env.example` holds placeholders. Secret settings are `SecretStr`, masked in logs and never returned by an endpoint. The API and worker refuse to start on missing or invalid configuration. | `.gitignore`, `backend/app/core/config.py` |
| Flower | Off by default (profile `monitoring`), bound to `127.0.0.1`, basic auth from `FLOWER_USER` / `FLOWER_PASSWORD`, and it refuses to start without them. | `docker-compose.yml` |
| Database | Postgres is published on `127.0.0.1` only. SQL goes through SQLAlchemy with bound parameters. | `docker-compose.yml`, `backend/app/db/` |
| Browser rendering | Search snippets are rendered from parsed parts, not as raw HTML, so highlighted text from a document cannot inject markup. | `frontend/src/lib/snippet.ts`, `Snippet.test.tsx` |

## Not covered

- **No user accounts.** One shared key for everyone who can reach the web server. The "edited by" name on a correction is typed in, not authenticated, so the audit trail records a claim, not an identity.
- **Open ports.** `docker-compose.yml` publishes Redis (6379, no password), the storage S3 port (8333), the API (8000) and the web app (3000) on all interfaces. That is fine on a laptop; on a shared network bind them to `127.0.0.1` or remove the `ports:` entries for services that only talk to each other.
- **No transport encryption.** Plain HTTP between all services and to the browser. Put it behind a TLS-terminating proxy for anything beyond local use.
- **No rate limiting on the API** (only the model call is rate limited), and no antivirus scan of uploads.
- **Document text goes to Google.** With a key set, page text is sent to the Gemini API for extraction and embedding, and the chunks that answer a chat question are sent with the question. Do not use real confidential documents unless that is acceptable under the key's terms.
- **No dependency or container scanning** is set up.
- **Chat sessions are stored in plain text and shared.** With a `session_id`, questions, answers and the quoted source text are kept in the database (`chat_sessions`, `chat_messages`) until the session is deleted (`DELETE` removes its messages). There are no accounts, so everyone who has the API key can list, read, rename and delete every session. The logs still hold no text. Deleting a document does not edit sessions that quote it.
- **A chat citation proves the source was retrieved, not that it supports the claim.** Support is not measured; the quote is shown beside the citation so a person can check.
- **The prompt-injection guard reduces risk, it does not remove it.** A crafted document could still mislead the model into a plausible wrong value; validation and the review queue are the safety net, and reviewers should treat extracted values as proposals.
