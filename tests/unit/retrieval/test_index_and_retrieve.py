"""Round-trip unit tests: index the real TIPI entries into an in-memory
ChromaDB collection, then retrieve through the adapter.

Embeddings come from a spy encoder (no model loaded), so these assert the
plumbing — entry count, k results, metadata round-tripping — not ranking
quality. Ranking against the real model is an integration concern.
"""

import json
from pathlib import Path
from uuid import uuid4

import chromadb
import pytest
from chromadb import Collection

from src.core.domain.ncm import ProductQuery
from src.retrieval.chroma_client import _find_latest_tipi_json, index_entries
from src.retrieval.embedding import EMBEDDING_DIM, E5EmbeddingFunction
from src.retrieval.hierarchical import ChromaRetrievalAdapter


class SpyEncoder:
    def encode(self, sentences: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIM for _ in sentences]


@pytest.fixture
def indexed_adapter() -> ChromaRetrievalAdapter:
    entries = json.loads(
        _find_latest_tipi_json(Path("data/tipi"), "22").read_text(encoding="utf-8")
    )["entries"]
    collection: Collection = chromadb.EphemeralClient().create_collection(
        name=f"roundtrip_{uuid4().hex}", metadata={"hnsw:space": "cosine"}
    )
    embedding_fn = E5EmbeddingFunction(encoder=SpyEncoder())
    index_entries(collection, entries, embedding_fn)
    return ChromaRetrievalAdapter(collection, embedding_fn)


def test_retrieve_candidates_returns_k_results(
    indexed_adapter: ChromaRetrievalAdapter,
) -> None:
    query = ProductQuery(product_name="cerveja", description="")
    candidates = indexed_adapter.retrieve_candidates(query, k=3)
    assert len(candidates) == 3


def test_retrieve_candidates_preserves_ncm_metadata(
    indexed_adapter: ChromaRetrievalAdapter,
) -> None:
    query = ProductQuery(product_name="água mineral", description="")
    top = indexed_adapter.retrieve_candidates(query, k=3)[0]
    assert top.ncm_code.count(".") == 2  # dotted NCM, e.g. 2201.10.00
    assert set(top.metadata) >= {"ncm_dotted", "description", "chapter", "heading"}
