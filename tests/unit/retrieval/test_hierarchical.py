from src.core.domain.ncm import ClassificationCandidate, ProductQuery
from src.retrieval.hierarchical import ChromaRetrievalAdapter


# ---------------------------------------------------------------------------
# Fake ChromaDB Collection — test double, no real DB
# ---------------------------------------------------------------------------

class FakeCollection:
    """Minimal Collection double: records the last query call and returns preset results."""

    def __init__(self, results: dict) -> None:
        self._results = results
        self.last_query_texts: list[str] = []
        self.last_n_results: int = 0

    def query(
        self,
        query_texts: list[str],
        n_results: int,
        **_kwargs: object,
    ) -> dict:
        self.last_query_texts = query_texts
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
            "aliquota": "0",
        }
        for ncm, desc in zip(ncm_dotteds, descriptions)
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_candidates_sorted_by_descending_score() -> None:
    adapter = ChromaRetrievalAdapter(FakeCollection(BEER_RESULTS))
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    assert candidates[0].score >= candidates[1].score


def test_score_equals_one_minus_cosine_distance() -> None:
    adapter = ChromaRetrievalAdapter(FakeCollection(BEER_RESULTS))
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    assert abs(candidates[0].score - (1.0 - 0.05)) < 1e-9
    assert abs(candidates[1].score - (1.0 - 0.42)) < 1e-9


def test_ncm_code_comes_from_metadata_ncm_dotted() -> None:
    adapter = ChromaRetrievalAdapter(FakeCollection(BEER_RESULTS))
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    codes = {c.ncm_code for c in candidates}
    assert "2203.00.00" in codes
    assert "2202.00.00" in codes


def test_description_comes_from_metadata() -> None:
    adapter = ChromaRetrievalAdapter(FakeCollection(BEER_RESULTS))
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    top = next(c for c in candidates if c.ncm_code == "2203.00.00")
    assert top.description == "Cervejas de malte"


def test_metadata_dict_is_preserved() -> None:
    adapter = ChromaRetrievalAdapter(FakeCollection(BEER_RESULTS))
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    candidates = adapter.retrieve_candidates(query, k=2)
    top = next(c for c in candidates if c.ncm_code == "2203.00.00")
    assert top.metadata["chapter"] == "22"
    assert top.metadata["heading"] == "2203"


def test_passes_k_to_collection_query() -> None:
    fake = FakeCollection(BEER_RESULTS)
    adapter = ChromaRetrievalAdapter(fake)
    query = ProductQuery(product_name="cerveja", description="")
    adapter.retrieve_candidates(query, k=3)
    assert fake.last_n_results == 3


def test_combines_product_name_and_description_as_query_text() -> None:
    fake = FakeCollection(BEER_RESULTS)
    adapter = ChromaRetrievalAdapter(fake)
    query = ProductQuery(product_name="cerveja", description="lata 350ml")
    adapter.retrieve_candidates(query, k=2)
    assert fake.last_query_texts == ["cerveja lata 350ml"]


def test_query_text_is_product_name_only_when_description_is_empty() -> None:
    fake = FakeCollection(BEER_RESULTS)
    adapter = ChromaRetrievalAdapter(fake)
    query = ProductQuery(product_name="cerveja", description="")
    adapter.retrieve_candidates(query, k=2)
    assert fake.last_query_texts == ["cerveja"]
