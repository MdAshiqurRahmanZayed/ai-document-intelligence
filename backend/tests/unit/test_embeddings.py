import pytest
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.config import Settings
from app.llm.embeddings import EMBEDDING_DIM, GoogleEmbedder, build_embedder
from tests.fake_embedder import FakeEmbedder, cosine, embed


def test_the_fake_embedder_is_deterministic_and_has_the_right_size() -> None:
    first, second = embed("payment is due"), embed("payment is due")

    assert first == second and len(first) == EMBEDDING_DIM == 768
    assert FakeEmbedder().embed_documents(["a", "b"]) == [embed("a"), embed("b")]


def test_similar_texts_are_closer_than_unrelated_ones() -> None:
    question = embed("when must I pay")
    related = embed("payment is due within thirty days")
    unrelated = embed("bananas are yellow fruit")

    assert cosine(question, related) > cosine(question, unrelated)
    assert cosine(question, unrelated) == pytest.approx(0.0)


def test_a_vector_has_length_one_and_empty_text_does_not_break() -> None:
    assert cosine(embed("some words here"), embed("some words here")) == pytest.approx(1.0)
    assert embed("") == [0.0] * EMBEDDING_DIM


class StubClient:
    """What GoogleGenerativeAIEmbeddings would return, with a size of our choosing."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.task_types: list[str | None] = []

    def embed_documents(
        self, texts: list[str], *, task_type: str | None = None
    ) -> list[list[float]]:
        self.task_types.append(task_type)
        return [[0.0] * self.size for _ in texts]

    def embed_query(self, text: str, *, task_type: str | None = None) -> list[float]:
        self.task_types.append(task_type)
        return [0.0] * self.size


def test_the_google_embedder_marks_stored_texts_and_queries_differently() -> None:
    client = StubClient(EMBEDDING_DIM)
    embedder = GoogleEmbedder(client)

    embedder.embed_documents(["a"])
    embedder.embed_query("q")

    assert client.task_types == ["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]


def test_a_vector_of_the_wrong_size_is_an_error_not_a_database_failure() -> None:
    embedder = GoogleEmbedder(StubClient(3))

    with pytest.raises(ValueError, match="expected 768"):
        embedder.embed_documents(["a"])
    with pytest.raises(ValueError, match="expected 768"):
        embedder.embed_query("q")


def test_build_embedder_needs_a_key_and_builds_offline_with_one(
    valid_env: pytest.MonkeyPatch,
) -> None:
    valid_env.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError):
        build_embedder(Settings(_env_file=None))

    valid_env.setenv("GOOGLE_API_KEY", "not-a-real-key")
    embedder = build_embedder(Settings(_env_file=None))  # constructing makes no network call

    assert isinstance(embedder, GoogleEmbedder)
    assert isinstance(embedder._client, GoogleGenerativeAIEmbeddings)
    assert embedder._client.output_dimensionality == EMBEDDING_DIM
