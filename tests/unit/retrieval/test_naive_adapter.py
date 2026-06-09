from src.core.domain.ncm import ProductQuery
from src.core.ports import RetrievalPort
from src.retrieval.naive_adapter import NaiveRetrievalAdapter


def _entries(n: int) -> list[dict[str, object]]:
    return [
        {
            "ncm": f"2201.10.{i:02d}",
            "section": "IV",
            "chapter": "22",
            "heading": "22.01",
            "subheading": "2201.10",
            "description": f"bebida {i}",
            "ipi_rate": "2.6",
            "ex_tipi": None,
            "raw_row": 1900 + i,
        }
        for i in range(n)
    ]


def _query() -> ProductQuery:
    return ProductQuery(product_name="agua mineral", description="garrafa 500ml")


def test_returns_first_k_entries_in_json_order() -> None:
    adapter = NaiveRetrievalAdapter(_entries(5))
    result = adapter.retrieve_candidates(_query(), k=3)
    assert [c.ncm_code for c in result] == ["2201.10.00", "2201.10.01", "2201.10.02"]


def test_returns_all_when_k_exceeds_available() -> None:
    adapter = NaiveRetrievalAdapter(_entries(3))
    result = adapter.retrieve_candidates(_query(), k=10)
    assert len(result) == 3


def test_score_is_always_zero() -> None:
    adapter = NaiveRetrievalAdapter(_entries(4))
    result = adapter.retrieve_candidates(_query(), k=4)
    assert all(c.score == 0.0 for c in result)


def test_same_input_produces_same_output() -> None:
    adapter = NaiveRetrievalAdapter(_entries(5))
    first = adapter.retrieve_candidates(_query(), k=3)
    second = adapter.retrieve_candidates(_query(), k=3)
    assert [c.ncm_code for c in first] == [c.ncm_code for c in second]


def test_implements_retrieval_port() -> None:
    adapter = NaiveRetrievalAdapter(_entries(1))
    assert isinstance(adapter, RetrievalPort)
