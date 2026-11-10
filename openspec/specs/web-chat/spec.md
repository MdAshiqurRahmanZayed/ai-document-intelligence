# web-chat Specification

## Purpose
Gives a person a page to ask questions about their documents and read a streamed answer whose citations lead back to the pages it used.

## Requirements

### Requirement: Chat page
The web interface SHALL have a Chat page, reachable from the navigation, with a question box and the existing filter bar. A question SHALL be sent only when it is not blank, and not while an answer is still streaming. The conversation SHALL be kept in the page only: reloading the page starts a new one.

#### Scenario: Ask
- **WHEN** a person types a question and sends it
- **THEN** the question appears in the conversation and an answer starts to appear

#### Scenario: Blank question
- **WHEN** the question is empty or only spaces
- **THEN** nothing is sent

#### Scenario: While answering
- **WHEN** an answer is still streaming
- **THEN** sending another question is not possible until it ends or is stopped

### Requirement: Answer streams in
The page SHALL show the answer as it arrives, and a person SHALL be able to stop it. The source list SHALL be shown as soon as the sources arrive, before the first word of the answer.

#### Scenario: Streaming
- **WHEN** tokens arrive
- **THEN** the answer grows on the page without waiting for the end

#### Scenario: Sources first
- **WHEN** the sources arrive before any text
- **THEN** the list is shown with a "reading" state in the answer until it starts

#### Scenario: Stop
- **WHEN** a person stops a streaming answer
- **THEN** the request is cancelled and the text so far stays

### Requirement: Citations
The page SHALL show each `[n]` in the answer as a numbered chip that matches source card n, and show the quote of that source when a person hovers or focuses the chip. A marker that matches no source SHALL NOT be shown as a chip or as text. Each source card SHALL show the filename, the page number and the quote, and link to the document. Quotes and answers SHALL be shown as text; markup in them SHALL NOT run.

#### Scenario: Chip and card
- **WHEN** the answer contains `[2]` and source 2 exists
- **THEN** a chip 2 is shown, and focusing it shows the quote of source 2

#### Scenario: Unknown marker
- **WHEN** the answer contains `[9]` and there is no source 9
- **THEN** it is not shown

#### Scenario: Link to the document
- **WHEN** a person clicks a source card
- **THEN** the document page opens

#### Scenario: Markup in a document
- **GIVEN** a quote containing `<script>alert(1)</script>`
- **THEN** it is shown as text and nothing runs

### Requirement: Answer beside its sources
Each answer SHALL be shown with its sources as a list: on a wide screen the answer on the left and the sources in a numbered list on the right, beside it; on a narrow screen the answer first and the sources below it. While an answer is being written the list SHALL show every source the model is reading; when the answer is finished it SHALL show only the sources the answer cites, with their original numbers so the chips still match. A stopped or failed answer SHALL list the sources its text cites so far. When there is nothing to list (nothing found, or the answer cites nothing), the answer SHALL use the full width and no source list SHALL be shown. Hovering or focusing a citation chip SHALL highlight its source in the list, and moving away SHALL remove the highlight.

#### Scenario: Two columns
- **GIVEN** an answer with sources on a wide screen
- **THEN** the answer is in the left column and the numbered source list is in the right column

#### Scenario: One column
- **GIVEN** an answer with sources on a narrow screen
- **THEN** the sources are listed below the answer

#### Scenario: No sources
- **WHEN** the answer says nothing was found
- **THEN** no source list is shown

#### Scenario: Only cited sources
- **GIVEN** an answer that read 6 sources and cites only [1]
- **WHEN** the answer is finished
- **THEN** the list shows source 1 only, and its heading counts 1

#### Scenario: Reading shows everything
- **WHEN** the sources have arrived and the answer is still being written
- **THEN** all 6 are listed until the answer finishes

#### Scenario: Nothing cited
- **GIVEN** an answer that says the documents do not tell and cites nothing
- **WHEN** it is finished
- **THEN** no source list is shown

#### Scenario: Highlight
- **WHEN** a person hovers the chip 2
- **THEN** source 2 in the list is highlighted until the pointer leaves

### Requirement: Follow-ups and filters
When the answer ends, the page SHALL show the suggested follow-up questions as buttons that send them. The filters SHALL apply to the next question. Every question SHALL be sent with the id of its saved chat (see web-chat-sessions), and the page SHALL send no history of its own: the server reads the earlier messages from the chat.

#### Scenario: Follow-up button
- **WHEN** a person clicks a suggested question
- **THEN** it is sent as the next question in the same chat

#### Scenario: Filter applied
- **WHEN** a person sets a currency filter and asks
- **THEN** the request carries that filter

#### Scenario: No history from the page
- **WHEN** a conversation has several turns
- **THEN** each request carries the chat id and no history

### Requirement: Failures and unavailability
The page SHALL say when chat needs a model key (409 `chat_unavailable`), when the provider's limit was reached (`provider_limited`), and when the answer failed (`model_failed`), with a retry for the last two. It SHALL show loading, empty (no conversation yet, with example questions) and error states like the other screens.

#### Scenario: No key
- **WHEN** the API answers 409 `chat_unavailable`
- **THEN** the page explains that chat needs a model key

#### Scenario: Provider limit
- **WHEN** the stream ends with `provider_limited`
- **THEN** the page says the limit was reached and offers to try again later

#### Scenario: Nothing found
- **WHEN** the answer says nothing was found
- **THEN** it is shown as an answer with no source cards, and suggests another question or fewer filters
