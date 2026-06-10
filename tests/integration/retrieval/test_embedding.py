"""Integration tests for the e5 embedding function — real model loaded.

These instantiate E5EmbeddingFunction with no injected encoder, so the pinned
intfloat/multilingual-e5-small model is downloaded (cached) and run on CPU.
They live under tests/integration/ (not unit) because they load a real model;
the default `make test` skips them, CI runs them with the HF cache warmed.

The key guard here is test_query_and_passage_embeddings_differ_for_same_text:
it fails if the prefixes are applied textually but the model treats them as
indistinguishable noise — the "technically correct but ineffective" failure
mode that a spy-based unit test cannot catch.
"""

import pytest

from src.retrieval.embedding import EMBEDDING_DIM, E5EmbeddingFunction


@pytest.fixture(scope="module")
def ef() -> E5EmbeddingFunction:
    return E5EmbeddingFunction()


def test_embeddings_have_expected_dimension(ef: E5EmbeddingFunction) -> None:
    [embedding] = ef.embed_documents(["Águas minerais e águas gaseificadas"])

    assert len(embedding) == EMBEDDING_DIM


def test_query_and_passage_embeddings_differ_for_same_text(
    ef: E5EmbeddingFunction,
) -> None:
    text = "Cervejas de malte"

    query_embedding = ef.embed_query(text)
    [passage_embedding] = ef.embed_documents([text])

    max_abs_diff = max(abs(q - p) for q, p in zip(query_embedding, passage_embedding, strict=True))
    assert max_abs_diff > 1e-6
