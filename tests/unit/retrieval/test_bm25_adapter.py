from uuid import uuid4

import chromadb
import pytest
from chromadb import Collection

from src.core.domain.ncm import NCMCode, ProductQuery
from src.core.ports import RetrievalPort
from src.retrieval.bm25_adapter import BM25RetrievalAdapter


def _collection(docs: list[tuple[str, str]]) -> Collection:
    """Ephemeral Chroma collection from (ncm_dotted, document_text) pairs.

    Dummy embeddings — BM25 reads ``documents`` and never the vectors.
    """
    client = chromadb.EphemeralClient()
    col = client.create_collection(name=f"bm25_{uuid4().hex}", metadata={"hnsw:space": "cosine"})
    col.add(
        ids=[ncm.replace(".", "") for ncm, _ in docs],
        embeddings=[[0.1, 0.2, 0.3] for _ in docs],
        documents=[doc for _, doc in docs],
        metadatas=[{"ncm_dotted": ncm, "description": doc, "chapter": "22"} for ncm, doc in docs],
    )
    return col


@pytest.fixture
def collection() -> Collection:
    return _collection(
        [
            ("2208.60.00", "- Vodca | vodca, Smirnoff, Absolut"),
            ("2208.50.00", "- Gim e genebra | gin, Tanqueray"),
            ("2203.00.00", "Cervejas de malte."),
        ]
    )


def test_indexes_collection_documents_including_synonyms(collection: Collection) -> None:
    # "Smirnoff" lives only in the stored document (ADR-0010 synonym), never in
    # the source TIPI JSON. A hit on it proves BM25 indexed the collection docs.
    adapter = BM25RetrievalAdapter(collection)
    top = adapter.retrieve_candidates(ProductQuery(product_name="Smirnoff", description=""), k=1)
    assert top[0].ncm_code == NCMCode("2208.60.00")


def test_query_uses_raw_text_without_embedder_prefix(collection: Collection) -> None:
    # BM25 is lexical: the e5 "query: " prefix must not be prepended. A bare term
    # ranks its document first; were a "query" token prepended it would pollute.
    adapter = BM25RetrievalAdapter(collection)
    top = adapter.retrieve_candidates(ProductQuery(product_name="gin", description=""), k=1)
    assert top[0].ncm_code == NCMCode("2208.50.00")


def test_returns_candidates_sorted_by_score_desc(collection: Collection) -> None:
    adapter = BM25RetrievalAdapter(collection)
    hits = adapter.retrieve_candidates(ProductQuery(product_name="vodca", description=""), k=3)
    assert [c.score for c in hits] == sorted((c.score for c in hits), reverse=True)


def test_respects_k_limit(collection: Collection) -> None:
    adapter = BM25RetrievalAdapter(collection)
    hits = adapter.retrieve_candidates(ProductQuery(product_name="vodca", description=""), k=2)
    assert len(hits) == 2


def test_implements_retrieval_port(collection: Collection) -> None:
    assert isinstance(BM25RetrievalAdapter(collection), RetrievalPort)
