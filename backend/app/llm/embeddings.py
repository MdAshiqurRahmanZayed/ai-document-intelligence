"""Turns text into vectors for semantic search. No FastAPI imports."""

from collections.abc import Sequence
from typing import Protocol

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.config import Settings
from app.db.types import EMBEDDING_DIM

__all__ = ["EMBEDDING_DIM", "Embedder", "GoogleEmbedder", "build_embedder"]


class Embedder(Protocol):
    """What indexing and search need from an embedding model."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class _Client(Protocol):
    """The two calls of LangChain's Google embeddings that are used here."""

    def embed_documents(
        self, texts: list[str], *, task_type: str | None = None
    ) -> list[list[float]]: ...

    def embed_query(self, text: str, *, task_type: str | None = None) -> list[float]: ...


class GoogleEmbedder:
    """Gemini embeddings. The model is told whether a text is stored or searched for, which
    gives better matches than treating both alike."""

    def __init__(self, client: _Client) -> None:
        self._client = client

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._client.embed_documents(list(texts), task_type="RETRIEVAL_DOCUMENT")
        for vector in vectors:
            self._check(vector)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._check(self._client.embed_query(text, task_type="RETRIEVAL_QUERY"))

    @staticmethod
    def _check(vector: list[float]) -> list[float]:
        # A wrong size would otherwise surface as an obscure database error on insert.
        if len(vector) != EMBEDDING_DIM:
            raise ValueError(f"the model returned {len(vector)} numbers, expected {EMBEDDING_DIM}")
        return vector


def build_embedder(settings: Settings) -> Embedder:
    if settings.google_api_key is None:
        raise ValueError("GOOGLE_API_KEY is not set")
    client = GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.google_api_key,
        output_dimensionality=EMBEDDING_DIM,
    )
    return GoogleEmbedder(client)
