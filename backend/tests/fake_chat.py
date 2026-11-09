"""A stand-in for the chat model: scripted answers, no network, and a record of every call."""

from collections.abc import Iterator, Sequence

from app.llm.chat import Source, Turn


class FakeChatModel:
    def __init__(
        self,
        pieces: Sequence[str] = (),
        rewritten: str = "",
        fail_rewrite: bool = False,
        error: Exception | None = None,
    ) -> None:
        self.pieces = list(pieces)
        self.rewritten = rewritten
        self.fail_rewrite = fail_rewrite
        self.error = error  # raised after the pieces have been given
        self.rewrite_calls: list[tuple[list[Turn], str]] = []
        self.stream_calls: list[tuple[str, list[Source]]] = []

    def rewrite(self, history: Sequence[Turn], question: str) -> str:
        self.rewrite_calls.append((list(history), question))
        if self.fail_rewrite:
            raise RuntimeError("the model is down")
        return self.rewritten

    def stream(self, question: str, sources: Sequence[Source]) -> Iterator[str]:
        self.stream_calls.append((question, list(sources)))
        yield from self.pieces
        if self.error is not None:
            raise self.error
