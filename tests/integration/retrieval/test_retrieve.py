"""Integration smoke test: index the real TIPI Chapter 22 entries with the real
e5-small model and retrieve through the adapter.

This is NOT the eval suite (that lives in eval/). Two cases only:

- a near-verbatim match that must pass — it validates the plumbing (indexing,
  passage/query prefixes, retrieval);
- a colloquial product name marked xfail — the first documented evidence of the
  core RAG-fiscal gap (brand/colloquial input vs. TIPI descriptive language),
  to be quantified in ADR-0004 and closed by future ADRs (hybrid dense+sparse,
  LLM rerank, query expansion).
"""

import json
from pathlib import Path
from uuid import uuid4

import chromadb
import pytest

from src.core.domain.enrichment import EnrichStrategy
from src.core.domain.ncm import ProductQuery
from src.retrieval.chroma_client import _find_latest_tipi_json, index_entries
from src.retrieval.embedding import E5EmbeddingFunction, EmbedderModel
from src.retrieval.hierarchical import ChromaRetrievalAdapter


@pytest.fixture(scope="module")
def real_adapter() -> ChromaRetrievalAdapter:
    entries = json.loads(
        _find_latest_tipi_json(Path("data/tipi"), "22").read_text(encoding="utf-8")
    )["entries"]
    collection = chromadb.EphemeralClient().create_collection(
        name=f"int_{uuid4().hex}", metadata={"hnsw:space": "cosine"}
    )
    embedding_fn = E5EmbeddingFunction()  # real e5-small at the pinned revision
    index_entries(collection, entries, embedding_fn, EnrichStrategy.OFF, EmbedderModel.E5_SMALL)
    return ChromaRetrievalAdapter(
        collection,
        embedding_fn,
        expected_strategy=EnrichStrategy.OFF,
        expected_embedder=EmbedderModel.E5_SMALL,
    )


def test_retrieves_near_verbatim_match(real_adapter: ChromaRetrievalAdapter) -> None:
    """Plumbing smoke test: a product worded like the TIPI entry is found."""
    query = ProductQuery(product_name="água mineral natural", description="sem gás")
    top3 = [c.ncm_code for c in real_adapter.retrieve_candidates(query, k=3)]
    assert "2201.10.00" in top3


@pytest.mark.xfail(
    reason="Colloquial product names vs TIPI descriptive language: "
    "e5-small dense retrieval has known limitation on this gap. "
    "First empirical evidence of the problem RAG-fiscal must "
    "address. To be discussed in ADR-0004 and addressed in "
    "future ADRs (hybrid dense+sparse, LLM rerank, query expansion).",
    strict=False,
)
def test_retrieves_colloquial_product_name(
    real_adapter: ChromaRetrievalAdapter,
) -> None:
    """Documented limitation: a brand/colloquial name should map to 2202.10.00
    (sweetened/flavoured waters — soft drinks) but does not yet rank top-3."""
    query = ProductQuery(product_name="Coca-Cola", description="lata 350ml")
    top3 = [c.ncm_code for c in real_adapter.retrieve_candidates(query, k=3)]
    assert "2202.10.00" in top3
