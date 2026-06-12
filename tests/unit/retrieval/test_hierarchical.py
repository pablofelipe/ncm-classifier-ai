import pytest

from src.core.domain.ncm import ProductQuery
from src.retrieval.embedding import EMBEDDING_DIM, E5EmbeddingFunction
from src.retrieval.hierarchical import ChromaRetrievalAdapter

# ---------------------------------------------------------------------------
# Test doubles — no real model, no real DB
# ---------------------------------------------------------------------------


class SpyEncoder:
    """Records the exact strings handed to encode; returns dummy vectors.

    Wrapped by a real E5EmbeddingFunction so prefix logic is exercised: lets a
    test assert the adapter's query reached the model as "query: ...".
    """

    def __init__(self) -> None:
        self.seen: list[str] = []

    def encode(self, sentences: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
        self.seen.extend(sentences)
        return [[0.1] * EMBEDDING_DIM for _ in sentences]


_SENTINEL = object()


class FakeCollection:
    """Collection double: records the last query call, returns preset results.

    ``metadata`` mirrors a Chroma collection's metadata dict so the adapter's
    enrich-agreement guard can be exercised. Defaults to a non-enriched index
    ({"enrich_documents": False}); pass metadata=None to simulate a legacy
    pre-flag index (missing key).
    """

    name = "fake_collection"

    def __init__(self, results: dict, metadata: object = _SENTINEL) -> None:
        self._results = results
        self.metadata = (
            {"enrich_documents": False} if metadata is _SENTINEL else metadata
        )
        self.last_query_embeddings: object = None
        self.last_n_results: int = 0

    def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int,
        **_kwargs: object,
    ) -> dict:
        self.last_query_embeddings = query_embeddings
        self.last_n_results = n_results
        return self._results


def _make_results(
    ids: list[str],
    distances: list[float],
    ncm_dotteds: list[str],
    descriptions: list[str],
) -> dict:
    metadatas = [
        {
            "ncm_dotted": ncm,
            "description": desc,
            "chapter": ncm[:2],
            "heading": ncm[:4],
            "ipi_rate": "0",
        }
        for ncm, desc in zip(ncm_dotteds, descriptions, strict=True)
    ]
    return {
        "ids": [ids],
        "distances": [distances],
        "documents": [descriptions],
        "metadatas": [metadatas],
    }


BEER_RESULTS = _make_results(
    ids=["22030000", "22020000"],
    distances=[0.05, 0.42],
    ncm_dotteds=["2203.00.00", "2202.00.00"],
    descriptions=["Cervejas de malte", "Outras bebidas não alcoólicas"],
)


def _adapter(results: dict, encoder: SpyEncoder | None = None) -> ChromaRetrievalAdapter:
    embedding_fn = E5EmbeddingFunction(encoder=encoder or SpyEncoder())
    return ChromaRetrievalAdapter(
        FakeCollection(results), embedding_fn, expected_enrich=False
    )


# ---------------------------------------------------------------------------
# Candidate-building logic (deterministic via preset distances)
# ---------------------------------------------------------------------------


def test_returns_candidates_sorted_by_descending_score() -> None:
    adapter = _adapter(BEER_RESULTS)
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    assert candidates[0].score >= candidates[1].score


def test_score_equals_one_minus_cosine_distance() -> None:
    adapter = _adapter(BEER_RESULTS)
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    assert abs(candidates[0].score - (1.0 - 0.05)) < 1e-9
    assert abs(candidates[1].score - (1.0 - 0.42)) < 1e-9


def test_ncm_code_comes_from_metadata_ncm_dotted() -> None:
    adapter = _adapter(BEER_RESULTS)
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    codes = {c.ncm_code for c in candidates}
    assert codes == {"2203.00.00", "2202.00.00"}


def test_description_comes_from_metadata() -> None:
    adapter = _adapter(BEER_RESULTS)
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    top = next(c for c in candidates if c.ncm_code == "2203.00.00")
    assert top.description == "Cervejas de malte"


def test_metadata_dict_is_preserved() -> None:
    adapter = _adapter(BEER_RESULTS)
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    top = next(c for c in candidates if c.ncm_code == "2203.00.00")
    assert top.metadata["chapter"] == "22"
    assert top.metadata["heading"] == "2203"


def test_passes_k_to_collection_query() -> None:
    fake = FakeCollection(BEER_RESULTS)
    adapter = ChromaRetrievalAdapter(
        fake, E5EmbeddingFunction(encoder=SpyEncoder()), expected_enrich=False
    )
    query = ProductQuery(product_name="cerveja", description="")
    adapter.retrieve_candidates(query, k=3)
    assert fake.last_n_results == 3


# ---------------------------------------------------------------------------
# enrich-agreement guard (ADR-0005): adapter refuses an index whose recorded
# enrich flag disagrees with the configured one (injected as expected_enrich).
# ---------------------------------------------------------------------------


def test_adapter_raises_on_enrich_mismatch() -> None:
    fake = FakeCollection(BEER_RESULTS, metadata={"enrich_documents": True})
    with pytest.raises(RuntimeError, match="make index"):
        ChromaRetrievalAdapter(
            fake, E5EmbeddingFunction(encoder=SpyEncoder()), expected_enrich=False
        )


def test_adapter_accepts_matching_enrich() -> None:
    fake = FakeCollection(BEER_RESULTS, metadata={"enrich_documents": True})
    adapter = ChromaRetrievalAdapter(
        fake, E5EmbeddingFunction(encoder=SpyEncoder()), expected_enrich=True
    )
    candidates = adapter.retrieve_candidates(
        ProductQuery(product_name="cerveja", description=""), k=2
    )
    assert len(candidates) == 2


def test_adapter_raises_on_legacy_index_missing_key() -> None:
    # Pre-flag index: metadata has no enrich_documents key. Contract: loud
    # failure, not a silent None==False treatment.
    fake = FakeCollection(BEER_RESULTS, metadata={"hnsw:space": "cosine"})
    with pytest.raises(RuntimeError, match="make index"):
        ChromaRetrievalAdapter(
            fake, E5EmbeddingFunction(encoder=SpyEncoder()), expected_enrich=False
        )


# ---------------------------------------------------------------------------
# Query prefix — the asymmetric e5 contract on the query side
# ---------------------------------------------------------------------------


def test_retrieve_candidates_uses_query_prefix() -> None:
    spy = SpyEncoder()
    adapter = _adapter(BEER_RESULTS, encoder=spy)
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    adapter.retrieve_candidates(query, k=2)
    assert spy.seen == ["query: cerveja lata 350ml"]


def test_query_text_is_product_name_only_when_description_is_empty() -> None:
    spy = SpyEncoder()
    adapter = _adapter(BEER_RESULTS, encoder=spy)
    query = ProductQuery(product_name="cerveja", description="")
    adapter.retrieve_candidates(query, k=2)
    assert spy.seen == ["query: cerveja"]
