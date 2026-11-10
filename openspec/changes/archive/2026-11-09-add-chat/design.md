## Context

See proposal.md for why. What exists and shapes the approach:

- `services/search.py` ranks chunks by keyword (`keyword_hits`) and by meaning (`semantic_hits`) and fuses them (`fuse`, RRF). It then reduces them to one hit per document with an escaped snippet. Chat needs the chunks themselves and their full text, so it reuses the three ranking pieces, not `search()`.
- `llm/extract.py` builds a LangChain chain from a prompt file, with retry and a fallback model. `Embedder` is a Protocol with a fake in tests. Chat follows the same shape.
- `app.state.embedder` is `None` without a Google API key; the endpoint can use the same fact to answer 409.
- The browser reaches the API only through `lib/proxy.ts`, which copies the response body through but only a few headers, and allows a fixed list of resources. A stream must survive that.
- The document filters are a query-parameter dependency (`document_filters`), so a POST can reuse them unchanged.
- Tests never call the real model.

## Goals / Non-Goals

**Goals:**
- One model call per question (two when a rewrite is needed), with the answer streaming and the sources shown first.
- Citations that can only point at chunks that were retrieved.
- Everything testable without the real model and without a browser stream.

**Non-Goals:**
- Server-side conversation storage, aggregates over many invoices, web search, answer-quality measurement (see proposal, Out of Scope).
- A second retrieval path: chat must not rank differently from search.

## Decisions

**Server-sent events over POST, read with `fetch`.** The reply is a `text/event-stream` produced by a streaming response. The browser cannot use `EventSource` (it only does GET and cannot carry the JSON body or history), so the page reads the response body with `fetch` and a small event parser. Alternatives: WebSocket (needs a second proxy path and upgrade handling in Next for no gain), and a non-streamed JSON answer (simplest, but the wait for a full answer is the thing a person notices; rejected).

**Event contract: `sources`, `token`\*, `done` | `error`.** `sources` first because retrieval is done before the model starts, so the cards appear while the model thinks. `error` replaces `done`; text already sent stays. Errors after the stream has started cannot change the HTTP status, which is why the failure is an event; failures before it (validation, no key) are ordinary 422 and 409 answers.

**Retrieve chunks with the search ranking, keep only the relevant ones, within a character budget.** `search.py` gets a `retrieve_chunks(session, query, filters, embedder)` that runs `keyword_hits` and, when an embedder exists, `semantic_hits`, fuses them, and loads the chunk rows with their full text. Chat then keeps a chunk only if it matched the question's words, or its semantic similarity (1 minus cosine distance, which `semantic_hits` already returns as `score`) is at least `MIN_SIMILARITY`. It walks the fused order and stops at 6 chunks, at most two per document, and `CONTEXT_CHARS = 4000` characters of chunk text; the best chunk is always kept whole, and a later chunk that would pass the limit is skipped. The fused RRF score cannot be the floor: it depends only on rank (1/(60+rank)), so it says nothing about whether a chunk is relevant. A question about one invoice then sends one or two chunks (about 500 tokens) instead of always six, which is also less noise for the model. Without an embedder chat is unavailable anyway, so retrieval is hybrid in practice; the function still degrades to keyword like `search()`. `MIN_SIMILARITY` starts at a guess and is calibrated in task 7.1 (see Open Questions).

**Streaming and follow-ups from one call, with a delimiter.** Structured output does not stream. The prompt asks for the answer as plain text with `[n]` markers, then a line `---FOLLOW-UPS---`, then up to three questions, one per line. A small splitter reads the token stream, holds back any text that could be the start of the delimiter, forwards everything before it as `token`, and parses what follows into `suggestions` when the model finishes. If the delimiter never appears, there are no suggestions and the answer is unchanged. Alternatives: a second call for suggestions (doubles the daily quota use), or JSON streaming (fragile partial parsing).

**Markers are checked after the fact, and the page filters them.** Tokens are already sent when the model writes `[9]`, so the server cannot remove it. The server computes `citations` (markers that match a source, in order of first use) for `done` and logs how many did not; the page renders a chip only for a marker that matches a source and drops the others. This proves only that the cited source was retrieved, not that it supports the claim; the README says so.

**Rewrite only when there is history, and history goes nowhere else.** A cheap call turns "and its tax?" plus the last turns into one standalone question. That question is used for retrieval and as the question of the answer call, which receives no history at all: its input is the system prompt, the question and the numbered chunks. History can be up to 6 messages of 2000 characters (about 3000 tokens), more than the chunks themselves, and once the question stands alone the answer does not need it. The rewritten text is sent in `sources` so it is visible and testable. With no history there is no call. If the rewrite fails, retrieval and the answer use the original question rather than failing the request.

**No documents, no model call.** Empty retrieval (after the relevance filter) returns a fixed sentence. This saves a request and removes the case where a model answers from its own knowledge.

**Keep the fixed cost small and bounded.** The system prompt is short and the same text on every call, placed first, so the provider's automatic prefix caching can apply when it does (no explicit cache is created; the prompt is far below the size where that pays). The answer is limited to `max_output_tokens = 400`; a longer answer is cut, `done` is still sent, and follow-ups are then absent because the delimiter was never reached. Each model call logs its model, input and output tokens (`usage_metadata`, as extraction does), chunk count and character count, never the text, so the saving is measured and not assumed.

**Prompt-injection guard as in extraction.** Chunk text is placed between fixed tags with its number; the earlier messages are given only to the rewrite call, as data; the system prompt in `prompts/v1/chat.md` says everything inside the tags is document text, never instructions, to answer only from it, to cite with `[n]`, and to say "I can't tell from these documents" otherwise. The prompt is a versioned file like the extraction prompt.

**Model: the configured extraction model with the fallback behind it, temperature 0.** No new setting, so `.env.example` does not change. A separate chat model is easy to add later.

**History stays in the browser.** The page keeps the conversation in React state and sends the last 3 turns (6 messages). The API trusts nothing in it: length limits, role check, and it is passed as data. Server-side storage would need a table, identity and retention rules that the system does not have.

**Layout like a research answer: text left, sources right.** Each turn is a two-column grid on wide screens (answer, then a 22rem list of numbered sources that stays in view while scrolling) and one column below that width, answer first. The list is vertical, one source per row (number, file, page, quote), so a long quote reads easily; a card grid would not. A chip that is hovered or focused marks its row, which needs the chip to tell its turn which number is active (a callback, no global state). With no sources the answer takes the full width.

**Filters reuse `document_filters` as query parameters** on the POST, so the chat and the search page share `FilterBar` and the same semantics, and the proxy needs no body inspection.

**Proxy.** `chat` joins the allowed resources. For a `text/event-stream` response the proxy also sets `cache-control: no-cache, no-transform` and `x-accel-buffering: no`, and passes the body through without reading it; the existing code already returns `upstream.body` as a stream, so no buffering is added. The request's abort signal is already passed on, which is how Stop cancels the model call.

**Sync model in a thread.** LangChain's stream is a blocking iterator; the endpoint wraps it with `iterate_in_threadpool`, as search runs the embedding in a thread, so the event loop stays free.

## Risks / Trade-offs

- [The daily request limit of the free tier is small (about 20 per model)] → One call per question, none when nothing is found, one extra only with history; the provider limit is reported as `provider_limited`, and the README tells how many questions a demo can ask. Fewer input tokens do not raise this limit (it counts requests); they lower latency, paid-tier cost and the per-minute token limit.
- [The relevance floor drops a chunk that held the answer] → The floor keeps any chunk that matched the words, the best chunk is always kept, and the cost of a miss is "I can't tell from these documents", not a wrong answer; calibrated in 7.1.
- [Dropping history from the answer call loses wording the answer needed] → The rewrite carries what the question needs; a test shows the answer input holds no history.
- [A citation can name a real source that does not support the claim] → Not measurable here; stated in the README and docs as unmeasured, and the quote is shown beside the chip so a person can check.
- [The model ignores the delimiter or writes it differently] → The splitter tolerates a missing delimiter (no suggestions); a test covers a delimiter split across tokens.
- [A proxy or browser buffers the stream] → Headers set, and a proxy test shows the first event is available before the upstream ends; verified once by hand in the running stack.
- [Chunk retrieval cannot answer questions about totals across documents] → Out of scope and documented; the model is told to say it cannot tell when the text is not enough.
- [A document's text asks the model to misbehave] → Delimited data, system rule, a test with an instruction inside a chunk (checks the prompt contains it only inside the tags; real behaviour is not tested with the model).
- [Chat quality was never measured] → No claim is made; the evaluation report is unchanged.

## Open Questions

- The exact limits (6 chunks, 2 per document, 4000 characters, 400 output tokens, `MIN_SIMILARITY`, 300-character quote) may need adjusting after trying real invoices. They are constants and do not change the specs. `MIN_SIMILARITY` is 0.62, set in task 7.1 from nine real questions on the sample invoices (embedding model `gemini-embedding-001`): the best chunk of an answerable question scored 0.642 to 0.742 ("bakery products" lowest) and of an off-topic one 0.491 to 0.607 ("hello" highest), so 0.62 sits in the gap of 0.035. That is a small set on one dataset, so the value is a starting point: too high and answerable questions get "nothing found", too low and noise comes back. Another observation: no natural-language question had a word match (keyword search needs every word in one chunk), so the similarity floor decides alone in practice; an OR-style match would change that and is not planned.
- Skipping near-identical chunks (shared footers and terms across bulk invoices) is not planned; add it if testing shows duplicates in `sources`.
- The input saving is not measured before the build. The token log (task 3.2) gives the numbers in 7.1.
