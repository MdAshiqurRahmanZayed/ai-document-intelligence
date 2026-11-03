# web-search Specification

## Purpose
Lets a person find previously processed documents by what their text says, choosing keyword, semantic or hybrid search and narrowing results with the same filters as the document list.

## Requirements

### Requirement: Search page
The search page SHALL take a query and a mode (keyword, semantic or hybrid, hybrid by default) and show results with filename, status badge, page number, a snippet with the matched words highlighted, and the invoice summary, each linking to the document. It SHALL send a search only for a non-blank query. The query and mode SHALL be kept in the page address so a search can be shared and the back button restores it.

#### Scenario: Results
- **WHEN** a person searches "payment terms"
- **THEN** results show filename, status, page and a snippet with the matched words highlighted, each linking to its document

#### Scenario: Blank query
- **WHEN** the query is empty or only spaces
- **THEN** no request is sent

#### Scenario: Address holds the search
- **WHEN** a person searches and then reloads the page
- **THEN** the same query and mode are shown with the same results

#### Scenario: No results
- **WHEN** the API returns no results
- **THEN** the page says nothing matched and suggests another mode or fewer filters

### Requirement: Snippet display is safe
The page SHALL display a snippet with only the highlight marks active. Any other markup in the snippet text SHALL be shown as text and SHALL NOT run.

#### Scenario: Script in a document
- **GIVEN** a snippet containing `&lt;script&gt;alert(1)&lt;/script&gt;` around a `<mark>` word
- **THEN** the script text is shown as text, nothing runs, and the word is highlighted

### Requirement: Mode availability and fallback
When the API answers 409 `semantic_unavailable`, the page SHALL tell the person semantic search needs a configured model key and offer keyword search. When the API reports `mode_used` different from the chosen mode, the page SHALL say which mode was actually used.

#### Scenario: Semantic unavailable
- **WHEN** the API answers 409 `semantic_unavailable`
- **THEN** the page explains it and offers to search by keyword instead

#### Scenario: Hybrid falls back
- **GIVEN** hybrid was chosen and the response has `mode_used` `keyword`
- **THEN** the page says the results are keyword results

### Requirement: Filters on search
The search page SHALL offer the same filters as the document list (status, supplier, invoice number, date range, amount range, currency) and apply them together with the query.

#### Scenario: Filter with query
- **WHEN** a person searches "freight" with status `COMPLETED`
- **THEN** the request carries both and only completed documents are listed
