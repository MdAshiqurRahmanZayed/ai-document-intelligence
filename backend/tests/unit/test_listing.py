import base64
import uuid
from datetime import UTC, datetime

import pytest

from app.services.listing import InvalidCursor, decode_cursor, encode_cursor


def test_a_cursor_round_trips() -> None:
    when = datetime(2026, 1, 5, 10, 30, 15, 123456, tzinfo=UTC)
    document_id = uuid.uuid4()

    assert decode_cursor(encode_cursor(when, document_id)) == (when, document_id)


def test_a_cursor_is_safe_to_put_in_a_url() -> None:
    cursor = encode_cursor(datetime(2026, 1, 5, tzinfo=UTC), uuid.uuid4())

    assert all(c.isalnum() or c in "-_=" for c in cursor)


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "not base64!!",
        base64.urlsafe_b64encode(b"not json").decode(),
        base64.urlsafe_b64encode(b'["only one item"]').decode(),
        base64.urlsafe_b64encode(b'["not a date", "not a uuid"]').decode(),
        base64.urlsafe_b64encode(b'{"a": 1}').decode(),
        base64.urlsafe_b64encode(b"[1, 2]").decode(),
    ],
)
def test_a_malformed_cursor_is_rejected(cursor: str) -> None:
    with pytest.raises(InvalidCursor):
        decode_cursor(cursor)
