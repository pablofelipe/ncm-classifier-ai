"""Integration tests for the bge-m3 embedding function — real model loaded (ADR-0008).

These instantiate BGEEmbeddingFunction with no injected encoder, so the pinned
BAAI/bge-m3 model is downloaded (cached, ~2.3 GB) and run on CPU. They live under
tests/integration/ (not unit) because they load a real model; the default
`make test` skips them, CI runs them with the HF cache warmed.

The key guard is test_query_and_passage_embeddings_match_for_same_text: it is the
inverse of the e5 guard. bge-m3 is symmetric, so the same text must yield the
SAME vector whether embedded as a query or a document — a difference would mean
an asymmetric prefix crept in (the silent quality bug the model card warns off).
"""

import pytest

from src.retrieval.embedding import BGE_EMBEDDING_DIM, BGEEmbeddingFunction


@pytest.fixture(scope="module")
def ef() -> BGEEmbeddingFunction:
    return BGEEmbeddingFunction()


def test_embeddings_have_expected_dimension(ef: BGEEmbeddingFunction) -> None:
    [embedding] = ef.embed_documents(["Águas minerais e águas gaseificadas"])

    assert len(embedding) == BGE_EMBEDDING_DIM


def test_query_and_passage_embeddings_match_for_same_text(
    ef: BGEEmbeddingFunction,
) -> None:
    text = "Cervejas de malte"

    query_embedding = ef.embed_query(text)
    [passage_embedding] = ef.embed_documents([text])

    max_abs_diff = max(abs(q - p) for q, p in zip(query_embedding, passage_embedding, strict=True))
    assert max_abs_diff < 1e-6
