"""Composition root tests (ADR-0004): build_classify_use_case wires the
Chroma retrieval adapter.

Uses an in-memory collection and a spy encoder — no real model, no persistent
client. The default (no-injection) path constructs the real PersistentClient
and is exercised by `make eval` / integration, not here.
"""

import json
from pathlib import Path
from uuid import uuid4

import chromadb
import pytest
from chromadb import Collection

from src.api.dependencies import build_classify_use_case
from src.core.domain.enrichment import EnrichStrategy
from src.core.domain.ncm import ProductQuery
from src.retrieval.chroma_client import _find_latest_tipi_json, index_entries
from src.retrieval.embedding import EMBEDDING_DIM, E5EmbeddingFunction


class SpyEncoder:
    def encode(self, sentences: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIM for _ in sentences]


def _empty_collection() -> Collection:
    return chromadb.EphemeralClient().create_collection(
        name=f"deps_empty_{uuid4().hex}", metadata={"hnsw:space": "cosine"}
    )


@pytest.fixture
def indexed_collection() -> Collection:
    entries = json.loads(
        _find_latest_tipi_json(Path("data/tipi"), "22").read_text(encoding="utf-8")
    )["entries"]
    collection = chromadb.EphemeralClient().create_collection(
        name=f"deps_indexed_{uuid4().hex}", metadata={"hnsw:space": "cosine"}
    )
    index_entries(
        collection, entries, E5EmbeddingFunction(encoder=SpyEncoder()), EnrichStrategy.OFF
    )
    return collection


def test_raises_actionable_error_when_index_is_empty() -> None:
    with pytest.raises(RuntimeError, match="make index"):
        build_classify_use_case(
            collection=_empty_collection(),
            embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
        )


def test_classifies_through_chroma_index_when_populated(
    indexed_collection: Collection,
) -> None:
    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    result = use_case.execute(ProductQuery(product_name="cerveja", description=""))
    assert all(c.metadata["chapter"] == "22" for c in result.top_candidates)
