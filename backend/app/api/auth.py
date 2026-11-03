import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request


async def require_api_key(
    request: Request, x_api_key: Annotated[str | None, Header()] = None
) -> None:
    """Reject a request that lacks the shared API key. Does nothing when no key is configured."""
    expected = request.app.state.settings.api_key
    if expected is None:
        return
    # compare_digest takes the same time wherever the strings differ, so the response time
    # does not leak how much of a guessed key was right.
    if x_api_key is None or not secrets.compare_digest(
        x_api_key.encode(), expected.get_secret_value().encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
