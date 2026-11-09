# Spec Delta

## Purpose
Lets a person keep several conversations on the chat page, return to them after a reload, rename them and delete them.

## ADDED Requirements

### Requirement: Session list
The chat page SHALL show the stored sessions, most recently used first, each with its title, and a New chat button. On narrow screens the list SHALL be behind a button above the conversation. An empty list SHALL say there are no saved chats yet. A failed load SHALL show an error state with Retry, and the conversation SHALL still work.

#### Scenario: List shown
- **GIVEN** three stored sessions
- **WHEN** the person opens `/chat`
- **THEN** the three titles are listed, the most recently used first

#### Scenario: No sessions
- **GIVEN** no sessions
- **WHEN** the person opens `/chat`
- **THEN** the list says there are no saved chats yet

#### Scenario: List fails
- **GIVEN** the list request fails
- **WHEN** the page loads
- **THEN** an error state with Retry is shown and a question can still be asked

### Requirement: Questions are saved as they are asked
When the person asks a question in a chat with no open session, the page SHALL create a session, put its id in the address as `?session=<id>`, and send the question with that id. Later questions SHALL use the same session. The list SHALL show the new session at the top, titled from the question, as soon as it is created, and SHALL be refreshed when the answer ends. New chat SHALL clear the open session, the conversation and the address.

#### Scenario: First question creates a session
- **GIVEN** an empty new chat
- **WHEN** the person asks a question
- **THEN** a session is created, the address holds its id, and the list shows it at the top with the question as title

#### Scenario: New chat
- **GIVEN** an open session
- **WHEN** the person presses New chat
- **THEN** the conversation is empty, the address has no session, and nothing is deleted

### Requirement: Opening a saved conversation
Opening a session from the list, or loading a page whose address holds `?session=<id>`, SHALL show every saved message in order. Each answer SHALL look as it did when it was given: the text with citation chips, the numbered source list beside it, the follow-up buttons on the last answer, the stand-alone question when there was one. An answer with status `stopped` SHALL be marked as stopped and one with status `failed` SHALL show its error with Retry. A session that does not exist SHALL show a not-found state with a link to New chat. Asking a question in an opened session SHALL continue it.

#### Scenario: Reload keeps the conversation
- **GIVEN** a session with two answered questions
- **WHEN** the person reloads the page
- **THEN** both questions and answers are shown with their chips and source lists

#### Scenario: Continue
- **GIVEN** an opened session
- **WHEN** the person asks a follow-up
- **THEN** the new answer appears below the saved ones and the session is the same

#### Scenario: Stopped answer
- **GIVEN** a saved answer with status `stopped`
- **WHEN** the session is opened
- **THEN** its text is shown with a note that it was stopped

#### Scenario: Unknown session
- **WHEN** the address holds a session id that does not exist
- **THEN** a not-found state is shown with a link to start a new chat

### Requirement: Rename a session
Each session in the list SHALL be renameable in place. Choosing rename shows an input with the current title; Enter saves, Escape cancels, and a blank or unchanged title saves nothing. A title longer than 100 characters SHALL NOT be accepted by the input. A failed save SHALL keep the old title and show an error.

#### Scenario: Rename
- **WHEN** the person renames a session to "Hosting invoices" and presses Enter
- **THEN** the list and the page show the new title and the order is unchanged

#### Scenario: Cancel
- **WHEN** the person presses Escape while renaming
- **THEN** the old title stays and nothing is sent

#### Scenario: Rename fails
- **GIVEN** the API rejects the rename
- **WHEN** the person saves
- **THEN** the old title stays and an error is shown

### Requirement: Delete a session
Each session SHALL have a delete action that asks for confirmation in the page before sending the request. After deletion the session leaves the list; if it was open, the page returns to an empty new chat.

#### Scenario: Confirmed delete
- **WHEN** the person deletes a session and confirms
- **THEN** it leaves the list, and if it was open the conversation is cleared

#### Scenario: Not confirmed
- **WHEN** the person deletes a session and then cancels
- **THEN** nothing is sent and the session stays

### Requirement: Switching while an answer is streaming
Opening another session or pressing New chat while an answer is streaming SHALL stop that answer first, so its text so far is saved as stopped, and then switch.

#### Scenario: Switch during a stream
- **GIVEN** an answer is streaming
- **WHEN** the person opens another session
- **THEN** the stream is stopped and the other session is shown
