## Why

Search finds the page that holds an answer, but a person asking "which supplier invoiced hosting in October?" still has to open each hit and read it. The chunks are already embedded and searchable, so a model can read the best of them and answer in a sentence, with numbered citations that point back to the pages it used. This is also the clearest way to show what the stored data is good for.

## What Changes

- New endpoint `POST /api/v1/chat` that retrieves chunks with the existing hybrid search, asks the model to answer only from them, and streams the reply as server-sent events: `sources`, `token`, `done`, `error`.
- The answer carries inline `[n]` markers. Each `n` maps to a retrieved source (document, page, quote). Markers that match no source are not shown as citations.
- The same model call ends with up to three follow-up questions.
- When earlier turns are sent, the question is first rewritten into a standalone one, so a follow-up such as "and its tax?" retrieves something. The last three turns are kept by the client; nothing is stored on the server.
- The model reads little: only chunks that matched the words or are similar enough in meaning, at most 6 and 4000 characters, two per document; the answer call gets the stand-alone question and the chunks but no history; the answer is limited to 400 tokens; every call logs its token use.
- When retrieval keeps nothing, the answer says so and the model is not called.
- The search filters (status, supplier, dates, amounts, currency) narrow what the chat may read, reusing the existing filter parameters.
- New `/chat` page: streamed answer, citation chips, source cards that link to the document, follow-up buttons, the existing filter bar.
- The web server's proxy allows the `chat` resource and passes the event stream through unbuffered.
- Chat is unavailable (409 `chat_unavailable`) without a Google API key, as semantic search is.

## Capabilities

### New Capabilities
- `document-chat`: the API that answers a question from retrieved document text with citations, follow-ups and a streamed reply.
- `web-chat`: the page where a person asks, reads the streamed answer, follows citations and asks follow-ups.

### Modified Capabilities
- `web-api-access`: the proxy also forwards `chat` and keeps a server-sent event stream flowing.

## Impact

- Backend: new `app/llm/chat.py`, `app/services/chat.py`, `app/api/v1/chat.py`, `app/schemas/chat.py`, `prompts/v1/chat.md`; a chunk-level retrieval function added to `app/services/search.py`; router registered in `app/main.py`. No migration, no new setting, no new dependency (the extraction model and its fallback are reused).
- Frontend: new `app/chat/page.tsx`, chat components and a stream reader in `lib/`; a Nav link; `lib/proxy.ts` resource list and stream headers.
- Docs: `docs/api.md`, `docs/frontend.md`, `docs/security.md`, `docs/testing.md`, README (feature line, limits).
- Cost: one model call per question, and one more when a rewrite is needed, on a provider with a daily request limit.

## Out of Scope

- Stored conversations, accounts or per-person history.
- Answers about totals across many documents ("total spend per supplier"): chunk retrieval cannot see every row. Fixed aggregate queries over the invoice tables are a later change; free text-to-SQL is not planned.
- Searching the web.
- Opening the document at the cited page (the card shows the page number and links to the document).
- Measuring answer quality or whether a cited source supports its claim. The check only proves the source was retrieved. The README says so; the evaluation report is not extended.
- A new setting or model for chat, and any change to `.env.example`.
