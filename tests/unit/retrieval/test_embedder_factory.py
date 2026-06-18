"""Unit tests for the embedder factory (ADR-0008): EmbedderModel -> EmbeddingFunction.

The factory is the single place that maps the configured embedder enum to a
concrete embedding function, so the composition root and the indexer select the
embedder from settings rather than hardcoding a class.
"""

import pytest

from src.retrieval.embedding import (
    BGEEmbeddingFunction,
    E5EmbeddingFunction,
    EmbedderModel,
    make_embedding_function,
)


def test_factory_returns_e5_for_e5_small() -> None:
    assert isinstance(make_embedding_function(EmbedderModel.E5_SMALL), E5EmbeddingFunction)


def test_factory_returns_bge_for_bge_m3() -> None:
    assert isinstance(make_embedding_function(EmbedderModel.BGE_M3), BGEEmbeddingFunction)


def test_factory_rejects_unknown_model() -> None:
    with pytest.raises(ValueError):
        make_embedding_function("not-an-embedder")  # type: ignore[arg-type]
