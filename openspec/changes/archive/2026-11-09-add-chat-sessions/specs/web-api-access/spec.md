# Spec Delta

## ADDED Requirements

### Requirement: Chat sessions can be deleted through the web server
The web server SHALL forward a `DELETE` request only when the path is `chat/sessions/<uuid>`. `DELETE` to any other path SHALL be answered 404 and not forwarded. All other methods and rules are unchanged.

#### Scenario: Session delete forwarded
- **WHEN** the browser sends `DELETE /api/backend/chat/sessions/<uuid>`
- **THEN** the API receives it with `X-API-Key` and the browser receives its status

#### Scenario: Other deletes refused
- **WHEN** the browser sends `DELETE /api/backend/documents/<uuid>`
- **THEN** the response is 404 and nothing reaches the API
