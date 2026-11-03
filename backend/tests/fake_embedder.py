"""A stand-in for the embedding model: deterministic, no network, and just enough 'meaning'."""

import math
import re
import zlib
from collections.abc import Sequence

from app.db.types import EMBEDDING_DIM

# Words that count as the same thing, so a test can check "meaning, not words".
SYNONYMS = {
    word: "payment" for word in ("pay", "paid", "payment", "due", "owe", "owed", "settle")
} | {word: "delivery" for word in ("deliver", "delivery", "shipping", "shipped", "ship")}


def embed(text: str) -> list[float]:
    """Each word (or its synonym group) adds weight to one fixed position of the vector."""
    vector = [0.0] * EMBEDDING_DIM
    for word in re.findall(r"[a-z0-9]+", text.casefold()):
        vector[zlib.crc32(SYNONYMS.get(word, word).encode()) % EMBEDDING_DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # the vectors have length 1


class FakeEmbedder:
    def __init__(self) -> None:
        self.embedded: list[str] = []  # every text that was embedded, in order

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.embedded += texts
        return [embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return embed(text)
