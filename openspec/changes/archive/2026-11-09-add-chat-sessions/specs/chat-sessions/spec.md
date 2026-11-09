# Spec Delta

## Purpose
Keeps chat conversations: named sessions that hold every question and answer, with what is needed to show them again, so a person can return to, rename and delete them.

## ADDED Requirements

### Requirement: Sessions
`POST /api/v1/chat/sessions` SHALL create a session and return its `id`, `title`, `created_at`, `updated_at` and `message_count` of 0. The body MAY hold a `title`; without one the title is "New chat". `GET /api/v1/chat/sessions` SHALL list sessions, most recently updated first, with `limit` (1 to 100, default 50) and `offset`, returning `items` (each with `id`, `title`, `created_at`, `updated_at`, `message_count`) and `total`. `GET /api/v1/chat/sessions/{id}` SHALL return the session with its `messages` in the order they were written. `DELETE /api/v1/chat/sessions/{id}` SHALL delete the session and all its messages and answer 204. An unknown id SHALL give 404 with reason `session_not_found`. Every path SHALL require the API key.

#### Scenario: Create and list
- **WHEN** a client creates two sessions
- **THEN** the list shows both, the later one first, each with `message_count` 0

#### Scenario: Read a session
- **GIVEN** a session with two answered questions
- **WHEN** a client reads it
- **THEN** `messages` holds four entries in order, user then assistant, twice

#### Scenario: Delete
- **WHEN** a client deletes a session
- **THEN** the response is 204, reading it gives 404 `session_not_found`, and its messages are gone

#### Scenario: Unknown session
- **WHEN** a client reads or deletes an id that does not exist
- **THEN** the response is 404 with reason `session_not_found`

#### Scenario: Wrong key
- **GIVEN** `API_KEY` is set
- **WHEN** a client lists sessions without the key
- **THEN** the response is 401

### Requirement: Rename
`PATCH /api/v1/chat/sessions/{id}` with `{"title": ...}` SHALL set the title after trimming it. A title of 1 to 100 characters is accepted; a blank or longer one SHALL give 422 and change nothing. Renaming SHALL NOT change the session's `updated_at`.

#### Scenario: Rename
- **WHEN** a client renames a session to "Hosting invoices"
- **THEN** reading it shows that title and the list order is unchanged

#### Scenario: Blank title
- **WHEN** a client sends a title of only spaces
- **THEN** the response is 422 and the title is unchanged

### Requirement: Saved messages
A message SHALL hold its `role`, `content` and `created_at`. An assistant message SHALL also hold the `sources` it was given (each with `n`, `document_id`, `filename`, `page_no`, `quote`), the `citations` that exist, the `suggestions`, the `rewritten_question` when there was one, and a `status` of `done`, `stopped` or `failed`. The sources SHALL be stored as they were sent, so a saved answer stays readable if its document is later deleted.

#### Scenario: Answer restored with its sources
- **GIVEN** an answer that cited sources 1 and 2
- **WHEN** the session is read
- **THEN** the assistant message holds the same text, both sources with file, page and quote, citations 1 and 2 and its suggestions

#### Scenario: Document deleted later
- **GIVEN** a saved answer that cites a document, and that document is deleted
- **WHEN** the session is read
- **THEN** the message still holds the sources unchanged

### Requirement: Chat saves into a session
`POST /api/v1/chat` SHALL accept an optional `session_id`. With it, the endpoint SHALL save the question as a user message before streaming and the answer as an assistant message when the stream ends, whichever way it ends: `done` gives status `done`, a model failure gives `failed` with the text produced so far, and a client that disconnects gives `stopped` with the text produced so far. A stopped answer with no text SHALL NOT be saved. Each saved message SHALL move the session to the top of the list. An unknown `session_id` SHALL give 404 `session_not_found` before anything is streamed. Without `session_id` nothing SHALL be stored. A failure to save SHALL NOT change the events sent.

#### Scenario: Question and answer saved
- **WHEN** a client asks with a `session_id` and the stream completes
- **THEN** the session holds the question and the answer with status `done`

#### Scenario: Stop keeps the partial answer
- **GIVEN** the client closes the connection after some tokens
- **THEN** the session holds the question and an assistant message with the received text and status `stopped`

#### Scenario: Model failure
- **GIVEN** the model fails after some tokens
- **THEN** the stream ends with `error` and the session holds an assistant message with that text and status `failed`

#### Scenario: Unknown session
- **WHEN** a client asks with a `session_id` that does not exist
- **THEN** the response is 404 `session_not_found` and nothing is stored

#### Scenario: No session
- **WHEN** a client asks without `session_id`
- **THEN** the answer streams as before and no session or message is created

### Requirement: Stored history feeds the rewrite
When `session_id` is given, the history used to make the question stand alone SHALL be read from the session: the last 6 stored messages made of complete question and answer pairs whose answer is `done` or `stopped` and not empty, each truncated to 2000 characters. The `history` in the request body SHALL be ignored. The answering model SHALL still receive no history.

#### Scenario: Follow-up in a session
- **GIVEN** a session whose first answer was about invoice EV-1011
- **WHEN** a client asks "and its tax?" in that session with an empty `history`
- **THEN** the rewrite is made from the stored messages and `rewritten_question` names the invoice

#### Scenario: Failed answer not used
- **GIVEN** a session whose last answer has status `failed`
- **WHEN** a client asks a new question in it
- **THEN** that question and answer are not part of the history given to the rewrite

### Requirement: A session's title starts from its first question
When a question is saved into a session still titled "New chat", the title SHALL become the first 60 characters of the question with whitespace collapsed. A title set by a person SHALL NOT be changed by a question.

#### Scenario: Auto title
- **GIVEN** a new session
- **WHEN** the first question is "Which supplier invoiced hosting in October?"
- **THEN** the session's title is that question

#### Scenario: Renamed title kept
- **GIVEN** a session renamed to "Hosting"
- **WHEN** another question is asked in it
- **THEN** the title is still "Hosting"
