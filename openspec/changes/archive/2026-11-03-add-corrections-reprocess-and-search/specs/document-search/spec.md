# Spec Delta

## Purpose

Makes the text of processed documents searchable by words, by meaning, or both, so previously processed documents can be found again.

## ADDED Requirements

### Requirement: Text is indexed when it is ready
When all pages of a document have their text (at the end of the ingest job when no OCR is needed, otherwise at the end of the OCR job), the system SHALL split the text of each page into overlapping chunks of about 1000 characters (overlap about 150), save them with their page number and a full-text vector, and replace any chunks the document had before. A page without text SHALL produce no chunk. The chunks SHALL exist whether or not a Google API key is configured.

#### Scenario: Chunks of a text document
- **GIVEN** a two-page PDF with text on both pages
- **WHEN** the ingest job succeeds
- **THEN** the document has chunks for both pages, each with its page number

#### Scenario: Long page
- **GIVEN** a page of 2500 characters
- **WHEN** the document is indexed
- **THEN** it is split into several chunks that overlap

#### Scenario: Reprocessing
- **GIVEN** a document that was indexed before
- **WHEN** its text is ready again
- **THEN** its chunks are replaced, not duplicated

#### Scenario: Blank page
- **GIVEN** a page with no text
- **WHEN** the document is indexed
- **THEN** that page has no chunk

### Requirement: Embeddings
When a Google API key is configured, the system SHALL queue an `embed` job on the `embed` queue after a document is indexed, and the job SHALL store an embedding on each chunk that has none. A failure of the embedding job SHALL be retried under the normal retry policy and, when retries are exhausted, recorded as a failed event for stage `embed`; it SHALL NOT change the status of the document. Without a key no embedding job SHALL be queued.

#### Scenario: Embeddings are added
- **GIVEN** a configured key and an indexed document
- **WHEN** the embedding job runs
- **THEN** every chunk has an embedding and the history shows a succeeded event for stage `embed`

#### Scenario: Embedding failure
- **GIVEN** the embedding model raises an error on every attempt
- **WHEN** the retry limit is reached
- **THEN** a failed event for stage `embed` is recorded
- **AND** the document keeps its status and stays searchable by keyword

#### Scenario: No key
- **GIVEN** no Google API key
- **WHEN** a document is indexed
- **THEN** no embedding job is queued

### Requirement: Keyword search
`GET /api/v1/search?q=…&mode=keyword` SHALL find documents whose chunks match the words of the query (all words, any order, no stemming) and return one result per document, ranked by the best matching chunk, with the page number of that chunk and a short snippet in which the matched words are marked with `<mark>` tags. All other characters of the snippet SHALL be HTML-escaped, so the snippet is safe to show as HTML even though it contains text from uploaded documents.

#### Scenario: Words found
- **GIVEN** a document whose page 2 contains "Acme Industries invoice"
- **WHEN** a client searches for "industries acme"
- **THEN** the document is returned with page 2 and a snippet marking both words

#### Scenario: Not found
- **WHEN** a client searches for words that appear in no document
- **THEN** the response is 200 with an empty list

#### Scenario: One result per document
- **GIVEN** a document with three matching chunks
- **WHEN** a client searches
- **THEN** the document appears once, with its best chunk

#### Scenario: Markup in a document
- **GIVEN** a page that contains `<script>alert(1)</script> invoice`
- **WHEN** a client searches for "invoice"
- **THEN** the snippet contains no `<script>` tag (the database may leave HTML tags out of the snippet; any markup characters it keeps are escaped), and only the `<mark>` tags are markup

### Requirement: Semantic search
`GET /api/v1/search?q=…&mode=semantic` SHALL embed the query and return the documents with the nearest chunks by cosine similarity, one result per document with the page number and the text of the nearest chunk as snippet. Only chunks that have an embedding SHALL be considered. When no Google API key is configured the response SHALL be 409 with reason `semantic_unavailable`.

#### Scenario: Meaning, not words
- **GIVEN** a document about "payment is due within thirty days"
- **WHEN** a client searches "when must I pay" with semantic mode
- **THEN** that document is ranked above documents about other topics

#### Scenario: Not available
- **GIVEN** no Google API key
- **WHEN** a client searches in semantic mode
- **THEN** the response is 409 with reason `semantic_unavailable`

#### Scenario: Chunks without embeddings
- **GIVEN** a document whose embedding job has not run yet
- **WHEN** a client searches in semantic mode
- **THEN** the document is not returned

### Requirement: Hybrid search
`mode=hybrid` (the default) SHALL combine the keyword ranking and the semantic ranking of chunks with reciprocal rank fusion (score is the sum of 1 / (60 + rank) over the rankings that contain the chunk) and return one result per document with its best chunk. When no Google API key is configured, hybrid SHALL behave as keyword search. Every response SHALL state the mode that was used (`mode_used`).

#### Scenario: Found by both
- **GIVEN** a chunk that matches the words and is also semantically close
- **WHEN** a client searches in hybrid mode
- **THEN** its score is higher than that of a chunk found by only one of the two

#### Scenario: Hybrid without a key
- **GIVEN** no Google API key
- **WHEN** a client searches without a mode
- **THEN** the results are those of keyword search and `mode_used` is `keyword`

### Requirement: Search filters and response
Search SHALL accept the same filters as the document list (`status`, `supplier`, `invoice_number`, `date_from`, `date_to`, `amount_min`, `amount_max`, `currency`) and a `limit` (default 10, at most 50). Each result SHALL hold the document id, filename, status, page number, snippet, score and the short summary of the document's current invoices. A missing or blank `q`, an unknown mode or a limit above 50 SHALL give 422.

#### Scenario: Filtered search
- **GIVEN** two documents that contain the word "invoice", one `COMPLETED` and one `NEEDS_REVIEW`
- **WHEN** a client searches "invoice" with `status=NEEDS_REVIEW`
- **THEN** only the second is returned

#### Scenario: Blank query
- **WHEN** a client searches with an empty `q`
- **THEN** the response is 422
