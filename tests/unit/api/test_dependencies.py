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
from src.config import RetrievalMode, Settings, settings
from src.core.domain.enrichment import EnrichStrategy
from src.core.domain.ncm import ProductQuery
from src.core.verification.deterministic import TIPIIndex
from src.retrieval.chroma_client import _find_latest_tipi_json, index_entries
from src.retrieval.embedding import EMBEDDING_DIM, E5EmbeddingFunction, EmbedderModel
from src.retrieval.hierarchical import ChromaRetrievalAdapter
from src.retrieval.hybrid import HybridRetrievalAdapter


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
        collection,
        entries,
        E5EmbeddingFunction(encoder=SpyEncoder()),
        EnrichStrategy.OFF,
        EmbedderModel.E5_SMALL,
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


# ---------------------------------------------------------------------------
# retrieval mode (ADR-0011): DENSE default keeps production unchanged; HYBRID
# wires BM25 + e5 fused by RRF. Selected at the composition root, no index change.
# ---------------------------------------------------------------------------


def test_retrieval_mode_defaults_to_dense() -> None:
    # No RETRIEVAL_MODE env var -> production stays dense-only.
    assert Settings().retrieval_mode is RetrievalMode.DENSE


def test_default_mode_wires_dense_only(indexed_collection: Collection) -> None:
    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    assert isinstance(use_case._retrieval, ChromaRetrievalAdapter)


def test_hybrid_mode_wires_hybrid_adapter(
    indexed_collection: Collection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "retrieval_mode", RetrievalMode.HYBRID)
    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    assert isinstance(use_case._retrieval, HybridRetrievalAdapter)


# ---------------------------------------------------------------------------
# verification gate (ADR-0014): the composition root builds a TIPIIndex from
# the same TIPI JSON used to populate the Chroma collection, and injects it
# into ClassifyProduct.
# ---------------------------------------------------------------------------


def test_wires_a_tipi_index_for_verification(indexed_collection: Collection) -> None:
    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    assert isinstance(use_case._verification, TIPIIndex)


def test_wired_verification_index_passes_a_real_indexed_ncm(
    indexed_collection: Collection,
) -> None:
    entries = json.loads(
        _find_latest_tipi_json(Path("data/tipi"), "22").read_text(encoding="utf-8")
    )["entries"]
    sample_dotless = entries[0]["ncm"].replace(".", "")

    use_case = build_classify_use_case(
        collection=indexed_collection,
        embedding_fn=E5EmbeddingFunction(encoder=SpyEncoder()),
    )
    assert use_case._verification is not None
    result = use_case._verification.verify(sample_dotless)
    assert result.passed
