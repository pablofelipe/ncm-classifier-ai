"""Unit tests for the e5 embedding function — prefix and pin logic.

These use an injected spy encoder, so they load no model and touch no network.
The two tests that require the real e5-small model (dimension and the
prefix-actually-changes-the-vector guard) live in
tests/integration/retrieval/test_embedding.py per the TDD layering rule.
"""

import pytest

from src.retrieval.embedding import EMBEDDING_DIM, E5EmbeddingFunction


class SpyEncoder:
    """Records the exact strings handed to encode; returns dummy vectors.

    Lets the prefix tests assert on what the model would actually receive,
    which is the only reliable guard against "prefix silently not applied".
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.seen: list[str] = []
        self._dim = dim

    def encode(self, sentences: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
        self.seen.extend(sentences)
        return [[0.0] * self._dim for _ in sentences]


def test_passage_prefix_applied_to_documents() -> None:
    spy = SpyEncoder()
    ef = E5EmbeddingFunction(encoder=spy)

    ef.embed_documents(["Cervejas de malte"])

    assert spy.seen == ["passage: Cervejas de malte"]


def test_query_prefix_applied_to_queries() -> None:
    spy = SpyEncoder()
    ef = E5EmbeddingFunction(encoder=spy)

    ef.embed_query("Cervejas de malte")

    assert spy.seen == ["query: Cervejas de malte"]


@pytest.mark.parametrize("bad_revision", [None, ""])
def test_revision_is_pinned(bad_revision: str | None) -> None:
    with pytest.raises(ValueError):
        E5EmbeddingFunction(revision=bad_revision)
