"""Unit tests for evaluate_suite — top-1/top-3 accounting over an EvalSuite.

Uses a locally-declared FakeUseCase so these tests never load the TIPI JSON
nor touch the real adapters: the measurement logic is exercised in isolation.
"""

from eval.run_eval import evaluate_suite
from eval.schema import EvalCase, EvalSuite
from src.core.domain.ncm import (
    ClassificationCandidate,
    ClassificationResult,
    NCMCode,
    ProductQuery,
)


class FakeUseCase:
    """Returns canned predictions keyed by product_name.

    Each value is a list of 3 NCM codes (the v1 top-3), in rank order.
    """

    def __init__(self, predictions: dict[str, list[str]]) -> None:
        self._predictions = predictions

    def execute(self, query: ProductQuery) -> ClassificationResult:
        ncms = self._predictions[query.product_name]
        candidates = [
            ClassificationCandidate(ncm_code=NCMCode(ncm), description="x", score=0.0)
            for ncm in ncms
        ]
        return ClassificationResult(top_candidates=candidates, confidence_label="needs_review")


def _case(case_id: str, product_name: str, ncm: str) -> EvalCase:
    return EvalCase(
        id=case_id,
        query=product_name,
        product_description="descricao do produto",
        expected_ncm=ncm,
        answer_chapter=int(ncm[:2]),
        chapter=int(ncm[:2]),
        difficulty="easy",
        mode="direct",
        rationale="rationale com mais de vinte caracteres",
        source="synthetic",
    )


def _suite(*cases: EvalCase) -> EvalSuite:
    return EvalSuite(version="test", corpus_chapters=[22], cases=list(cases))


def test_evaluate_suite_counts_top_1_hits_correctly() -> None:
    suite = _suite(
        _case("case-001", "cerveja", "2203.00.00"),
        _case("case-002", "vinho", "2204.21.00"),
    )
    use_case = FakeUseCase(
        {
            # top-1 hit: expected in position 0
            "cerveja": ["2203.00.00", "2202.10.00", "2201.10.00"],
            # not a top-1 hit: expected absent
            "vinho": ["2202.10.00", "2201.10.00", "2206.00.90"],
        }
    )
    report = evaluate_suite(suite, use_case)
    assert report.top_1_hits == 1


def test_evaluate_suite_counts_top_3_hits_correctly() -> None:
    suite = _suite(
        _case("case-001", "cerveja", "2203.00.00"),
        _case("case-002", "vinho", "2204.21.00"),
    )
    use_case = FakeUseCase(
        {
            # top-3 hit but not top-1: expected in position 2
            "cerveja": ["2202.10.00", "2201.10.00", "2203.00.00"],
            # top-3 hit at position 1
            "vinho": ["2202.10.00", "2204.21.00", "2201.10.00"],
        }
    )
    report = evaluate_suite(suite, use_case)
    assert report.top_3_hits == 2
    assert report.top_1_hits == 0


def test_evaluate_suite_reports_zero_hits_when_no_match() -> None:
    suite = _suite(_case("case-001", "cerveja", "2203.00.00"))
    use_case = FakeUseCase({"cerveja": ["2202.10.00", "2201.10.00", "2206.00.90"]})
    report = evaluate_suite(suite, use_case)
    assert report.top_1_hits == 0
    assert report.top_3_hits == 0


def test_evaluate_suite_reports_per_case_details() -> None:
    suite = _suite(_case("case-001", "cerveja", "2203.00.00"))
    predicted = ["2202.10.00", "2203.00.00", "2201.10.00"]
    use_case = FakeUseCase({"cerveja": predicted})

    report = evaluate_suite(suite, use_case)

    assert report.total == 1
    assert len(report.per_case) == 1
    detail = report.per_case[0]
    assert detail.case_id == "case-001"
    assert detail.expected_ncm == "2203.00.00"
    assert detail.predicted_ncms == predicted
    assert detail.top_1_hit is False
    assert detail.top_3_hit is True
