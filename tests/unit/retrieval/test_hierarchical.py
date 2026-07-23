import pytest

from src.core.domain.enrichment import EnrichStrategy
from src.core.domain.ncm import NCMCode, ProductQuery
from src.retrieval.embedding import EMBEDDING_DIM, E5EmbeddingFunction, EmbedderModel
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
    agreement guards (embedder + enrich_strategy) can be exercised. Defaults to
    an OFF index built by e5 ({"enrich_strategy": "off", "embedder": "e5_small"});
    pass metadata=None to simulate a legacy pre-flag index (missing keys).
    """

    name = "fake_collection"

    def __init__(self, results: dict, metadata: object = _SENTINEL) -> None:
        self._results = results
        self.metadata = (
            {"enrich_strategy": "off", "embedder": "e5_small"}
            if metadata is _SENTINEL
            else metadata
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
        FakeCollection(results),
        embedding_fn,
        expected_strategy=EnrichStrategy.OFF,
        expected_embedder=EmbedderModel.E5_SMALL,
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
    assert codes == {NCMCode("2203.00.00"), NCMCode("2202.00.00")}


def test_description_comes_from_metadata() -> None:
    adapter = _adapter(BEER_RESULTS)
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    top = next(c for c in candidates if c.ncm_code == NCMCode("2203.00.00"))
    assert top.description == "Cervejas de malte"


def test_metadata_dict_is_preserved() -> None:
    adapter = _adapter(BEER_RESULTS)
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    top = next(c for c in candidates if c.ncm_code == NCMCode("2203.00.00"))
    assert top.metadata["chapter"] == "22"
    assert top.metadata["heading"] == "2203"


def test_passes_k_to_collection_query() -> None:
    fake = FakeCollection(BEER_RESULTS)
    adapter = ChromaRetrievalAdapter(
        fake,
        E5EmbeddingFunction(encoder=SpyEncoder()),
        expected_strategy=EnrichStrategy.OFF,
        expected_embedder=EmbedderModel.E5_SMALL,
    )
    query = ProductQuery(product_name="cerveja", description="")
    adapter.retrieve_candidates(query, k=3)
    assert fake.last_n_results == 3


# ---------------------------------------------------------------------------
# agreement guards (ADR-0005/0006 enrich_strategy; ADR-0008 embedder). The
# adapter refuses an index whose recorded provenance disagrees with config.
# The two fields are checked separately, embedder first (the more fundamental
# incompatibility: different model = incompatible vector space), each with a
# message naming the field that diverged for surgical diagnosis.
# ---------------------------------------------------------------------------


def test_adapter_raises_on_embedder_mismatch() -> None:
    # Index built by bge, config says e5: incompatible space. Message cites the
    # embedder, not the strategy (which agrees here).
    fake = FakeCollection(BEER_RESULTS, metadata={"enrich_strategy": "off", "embedder": "bge_m3"})
    with pytest.raises(RuntimeError, match="embedder"):
        ChromaRetrievalAdapter(
            fake,
            E5EmbeddingFunction(encoder=SpyEncoder()),
            expected_strategy=EnrichStrategy.OFF,
            expected_embedder=EmbedderModel.E5_SMALL,
        )


def test_adapter_raises_on_strategy_mismatch() -> None:
    # Embedder agrees, strategy diverges: message cites enrich_strategy, isolating
    # the cause to the document-text axis.
    fake = FakeCollection(
        BEER_RESULTS, metadata={"enrich_strategy": "full", "embedder": "e5_small"}
    )
    with pytest.raises(RuntimeError, match="enrich_strategy"):
        ChromaRetrievalAdapter(
            fake,
            E5EmbeddingFunction(encoder=SpyEncoder()),
            expected_strategy=EnrichStrategy.OFF,
            expected_embedder=EmbedderModel.E5_SMALL,
        )


def test_adapter_raises_on_legacy_index_missing_embedder_key() -> None:
    # ADR-0005/0006 index: enrich_strategy present, but no embedder key (it
    # predates ADR-0008). embedder -> None -> mismatch on the FIRST if.
    fake = FakeCollection(BEER_RESULTS, metadata={"enrich_strategy": "off"})
    with pytest.raises(RuntimeError, match="embedder"):
        ChromaRetrievalAdapter(
            fake,
            E5EmbeddingFunction(encoder=SpyEncoder()),
            expected_strategy=EnrichStrategy.OFF,
            expected_embedder=EmbedderModel.E5_SMALL,
        )


def test_adapter_accepts_matching_provenance() -> None:
    fake = FakeCollection(
        BEER_RESULTS, metadata={"enrich_strategy": "full", "embedder": "e5_small"}
    )
    adapter = ChromaRetrievalAdapter(
        fake,
        E5EmbeddingFunction(encoder=SpyEncoder()),
        expected_strategy=EnrichStrategy.FULL,
        expected_embedder=EmbedderModel.E5_SMALL,
    )
    candidates = adapter.retrieve_candidates(
        ProductQuery(product_name="cerveja", description=""), k=2
    )
    assert len(candidates) == 2


def test_adapter_raises_on_legacy_index_missing_enrich_key() -> None:
    # Pre-flag enrich index (embedder valid, enrich_strategy absent): loud
    # failure on the strategy guard, not a silent None==off treatment.
    fake = FakeCollection(BEER_RESULTS, metadata={"hnsw:space": "cosine", "embedder": "e5_small"})
    with pytest.raises(RuntimeError, match="enrich_strategy"):
        ChromaRetrievalAdapter(
            fake,
            E5EmbeddingFunction(encoder=SpyEncoder()),
            expected_strategy=EnrichStrategy.OFF,
            expected_embedder=EmbedderModel.E5_SMALL,
        )


def test_adapter_raises_on_legacy_bool_metadata() -> None:
    # ADR-0005 index recorded a bool key {"enrich_documents": False}; embedder
    # backfilled as e5 here so the strategy guard (not the embedder guard) fires.
    # enrich_strategy absent -> None -> mismatch -> raise.
    fake = FakeCollection(
        BEER_RESULTS, metadata={"enrich_documents": False, "embedder": "e5_small"}
    )
    with pytest.raises(RuntimeError, match="enrich_strategy"):
        ChromaRetrievalAdapter(
            fake,
            E5EmbeddingFunction(encoder=SpyEncoder()),
            expected_strategy=EnrichStrategy.OFF,
            expected_embedder=EmbedderModel.E5_SMALL,
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
