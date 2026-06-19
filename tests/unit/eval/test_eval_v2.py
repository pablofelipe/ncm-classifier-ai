"""v2 eval flow: version detection, multi-chapter cross-validation, and the
v2 measurement path.

The v2 cross-validation drops the single `chapter_scope` coupling: the corpus
is multi-chapter, so every case is in-scope and `expected_ncm` must simply
exist in the loaded corpus. The prefix invariant (answer_chapter == first two
digits of expected_ncm) is still enforced defensively.
"""
import json
from pathlib import Path

import pytest

from eval.run_eval import (
    cross_validate_v2,
    detect_suite_version,
    evaluate_suite_v2,
    load_eval_suite_v2,
    main,
)
from eval.schema import EvalCaseV2, EvalSuiteV2
from src.core.domain.ncm import (
    ClassificationCandidate,
    ClassificationResult,
    ProductQuery,
)

ROOT = Path(__file__).resolve().parents[3]
V1_PATH = ROOT / "eval" / "v1_cases.json"
V2_PATH = ROOT / "eval" / "v2_cases.json"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _case(case_id: str, ncm: str, query: str = "produto", mode: str = "direct") -> EvalCaseV2:
    return EvalCaseV2(
        id=case_id,
        query=query,
        expected_ncm=ncm,
        difficulty="easy",
        mode=mode,
        chapter=int(ncm[:2]),
        answer_chapter=int(ncm[:2]),
    )


def _suite(*cases: EvalCaseV2) -> EvalSuiteV2:
    return EvalSuiteV2(
        version="v2", description="t", corpus_chapters=[20, 21, 22], cases=list(cases)
    )


class _FakeUseCase:
    def __init__(self, predictions: dict[str, list[str]]) -> None:
        self._predictions = predictions

    def execute(self, query: ProductQuery) -> ClassificationResult:
        ncms = self._predictions[query.product_name]
        candidates = [
            ClassificationCandidate(ncm_code=ncm, description="x", score=0.0) for ncm in ncms
        ]
        return ClassificationResult(top_candidates=candidates, confidence_label="needs_review")


# ---------------------------------------------------------------------------
# detect_suite_version — routes v1 vs v2 by file content
# ---------------------------------------------------------------------------


def test_detects_v1_file() -> None:
    assert detect_suite_version(V1_PATH) == "v1"


def test_detects_v2_file() -> None:
    assert detect_suite_version(V2_PATH) == "v2"


# ---------------------------------------------------------------------------
# load_eval_suite_v2
# ---------------------------------------------------------------------------


def test_load_v2_suite() -> None:
    suite = load_eval_suite_v2(V2_PATH)
    assert len(suite.cases) == 350


# ---------------------------------------------------------------------------
# cross_validate_v2 — corpus membership, no chapter_scope coupling
# ---------------------------------------------------------------------------


def test_all_present_is_ok() -> None:
    report = cross_validate_v2(
        _suite(_case("c001", "2201.10.00"), _case("c002", "2009.12.00")),
        {"2201.10.00", "2009.12.00"},
    )
    assert report.missing == []
    assert report.ok is True


def test_missing_ncm_fails() -> None:
    report = cross_validate_v2(_suite(_case("c001", "2299.99.99")), {"2201.10.00"})
    assert report.missing == ["c001"]
    assert report.ok is False


def test_multichapter_membership() -> None:
    # A Ch.20 case and a Ch.22 case both validate against one multi-chapter corpus.
    report = cross_validate_v2(
        _suite(_case("c001", "2009.12.00"), _case("c002", "2203.00.00")),
        {"2009.12.00", "2203.00.00"},
    )
    assert report.present == 2
    assert report.ok is True


def test_prefix_mismatch_raises() -> None:
    case = _case("c001", "2203.00.00")
    case.answer_chapter = 20  # corrupt after construction to bypass the schema
    with pytest.raises(ValueError, match="answer_chapter"):
        cross_validate_v2(_suite(case), {"2203.00.00"})


# ---------------------------------------------------------------------------
# evaluate_suite_v2 — maps query -> ProductQuery, counts top-1/top-3
# ---------------------------------------------------------------------------


def test_evaluate_v2_counts_hits() -> None:
    suite = _suite(
        _case("c001", "2203.00.00", query="cerveja"),
        _case("c002", "2204.21.00", query="vinho"),
    )
    use_case = _FakeUseCase(
        {
            "cerveja": ["2203.00.00", "2202.10.00", "2201.10.00"],  # top-1 hit
            "vinho": ["2202.10.00", "2204.21.00", "2201.10.00"],  # top-3 hit only
        }
    )
    report = evaluate_suite_v2(suite, use_case)
    assert report.top_1_hits == 1
    assert report.top_3_hits == 2


# ---------------------------------------------------------------------------
# main() routes to the v2 flow and gates on corpus membership
# ---------------------------------------------------------------------------


def _write_corpus(tmp_path: Path, ncms: list[str]) -> Path:
    payload = {
        "tipi_version": "test-beverage",
        "chapter": "multi",
        "entries": [
            {
                "ncm": n,
                "chapter": n[:2],
                "heading": f"{n[:2]}.{n[2:4]}",
                "subheading": n[:7],
                "description": "x",
                "ipi_rate": "0",
            }
            for n in ncms
        ],
    }
    p = tmp_path / "tipi_beverage_20260618.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _write_v2_suite(tmp_path: Path, cases: list[dict]) -> Path:
    payload = {"version": "v2", "corpus_chapters": [20, 21, 22], "cases": cases}
    p = tmp_path / "v2_cases.json"
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


def test_main_v2_exits_zero_when_all_present(tmp_path, capsys) -> None:
    suite_path = _write_v2_suite(
        tmp_path,
        [
            {
                "id": "c001",
                "query": "cerveja",
                "expected_ncm": "2203.00.00",
                "difficulty": "easy",
                "mode": "direct",
                "chapter": 22,
                "answer_chapter": 22,
            }
        ],
    )
    _write_corpus(tmp_path, ["2203.00.00"])

    code = main(
        eval_path=suite_path,
        tipi_dir=tmp_path,
        use_case_factory=lambda: _FakeUseCase({"cerveja": ["2203.00.00", "2202.10.00", "2201.10.00"]}),
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Status: OK" in out


def test_main_v2_exits_one_when_missing(tmp_path, capsys) -> None:
    suite_path = _write_v2_suite(
        tmp_path,
        [
            {
                "id": "c001",
                "query": "fantasma",
                "expected_ncm": "2299.99.99",
                "difficulty": "easy",
                "mode": "direct",
                "chapter": 22,
                "answer_chapter": 22,
            }
        ],
    )
    _write_corpus(tmp_path, ["2203.00.00"])

    code = main(
        eval_path=suite_path,
        tipi_dir=tmp_path,
        use_case_factory=lambda: _FakeUseCase({"fantasma": ["2203.00.00", "2202.10.00", "2201.10.00"]}),
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "Status: FAIL" in out
    assert "c001" in out
