"""Schema tests for the unified eval suite (single EvalCase / EvalSuite).

v1 and v2 share one schema: identical field set, only the corpus they run
against differs (detected on the suite via ``corpus_chapters``). v1 carries the
rich text fields (product_description / rationale / source); v2 leaves them
empty. The ``id`` pattern accepts both ``case-NNN`` (v1) and ``cNNN`` (v2).
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.schema import CaseResult, EvalCase, EvalReport, EvalSuite

ROOT = Path(__file__).resolve().parents[3]
V1_PATH = ROOT / "eval" / "v1_cases.json"
V2_PATH = ROOT / "eval" / "v2_cases.json"

# ---------------------------------------------------------------------------
# Fixture: reusable valid fields (v1-style, with all rich fields populated)
# ---------------------------------------------------------------------------

VALID_FIELDS: dict = {
    "id": "case-001",
    "query": "Cerveja Pilsen Lata 350ml",
    "product_description": "Cerveja tipo Pilsen, lata de alumínio 350ml, teor alcoólico 4,9% vol.",
    "expected_ncm": "2203.00.00",
    "difficulty": "easy",
    "mode": "direct",
    "answer_chapter": 22,
    "chapter": 22,
    "confusion_chapters": [],
    "rationale": "Produto claramente identificado como cerveja de malte pelo fabricante",
    "source": "ecommerce",
}

VALID_SUITE_KWARGS: dict = {
    "version": "v1",
    "description": "test suite",
    "corpus_chapters": [22],
    "cases": [],
}


# ---------------------------------------------------------------------------
# EvalSuite — happy path
# ---------------------------------------------------------------------------


def test_loads_valid_minimal_suite() -> None:
    suite = EvalSuite(**VALID_SUITE_KWARGS)
    assert suite.version == "v1"
    assert suite.corpus_chapters == [22]
    assert suite.cases == []


def test_loads_valid_suite_with_one_case() -> None:
    suite = EvalSuite(**{**VALID_SUITE_KWARGS, "cases": [EvalCase(**VALID_FIELDS)]})
    assert len(suite.cases) == 1
    assert suite.cases[0].expected_ncm == "2203.00.00"


def test_description_and_corpus_chapters_default_empty() -> None:
    suite = EvalSuite(version="v1", cases=[])
    assert suite.description == ""
    assert suite.corpus_chapters == []


# ---------------------------------------------------------------------------
# expected_ncm format
# ---------------------------------------------------------------------------


def test_rejects_invalid_ncm_format() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "expected_ncm": "22030000"})


def test_rejects_ncm_with_wrong_grouping() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "expected_ncm": "2203.0.00"})


def test_accepts_ncm_with_correct_dotted_format() -> None:
    case = EvalCase(**VALID_FIELDS)
    assert case.expected_ncm == "2203.00.00"


# ---------------------------------------------------------------------------
# EvalSuite — duplicate IDs
# ---------------------------------------------------------------------------


def test_rejects_duplicate_case_ids() -> None:
    case = EvalCase(**VALID_FIELDS)
    with pytest.raises(ValidationError, match="unique"):
        EvalSuite(**{**VALID_SUITE_KWARGS, "cases": [case, case]})


def test_accepts_two_cases_with_distinct_ids() -> None:
    case_a = EvalCase(**VALID_FIELDS)
    case_b = EvalCase(**{**VALID_FIELDS, "id": "case-002"})
    suite = EvalSuite(**{**VALID_SUITE_KWARGS, "cases": [case_a, case_b]})
    assert len(suite.cases) == 2


# ---------------------------------------------------------------------------
# EvalCase — id field (accepts both v1 and v2 formats)
# ---------------------------------------------------------------------------


def test_accepts_v1_style_id() -> None:
    assert EvalCase(**{**VALID_FIELDS, "id": "case-042"}).id == "case-042"


def test_accepts_v2_style_id() -> None:
    assert EvalCase(**{**VALID_FIELDS, "id": "c001"}).id == "c001"


def test_rejects_id_with_wrong_format() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "id": "cap22-001"})


def test_rejects_v1_id_without_leading_zeros() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "id": "case-1"})


def test_rejects_v2_id_without_three_digits() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "id": "c1"})


# ---------------------------------------------------------------------------
# EvalCase — query and optional rich fields
# ---------------------------------------------------------------------------


def test_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "query": ""})


def test_rejects_query_too_long() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "query": "x" * 301})


def test_rich_fields_default_to_empty() -> None:
    minimal = {
        "id": "c001",
        "query": "água mineral com gás",
        "expected_ncm": "2201.10.00",
        "difficulty": "easy",
        "mode": "direct",
        "answer_chapter": 22,
        "chapter": 22,
    }
    case = EvalCase(**minimal)
    assert case.product_description == ""
    assert case.rationale == ""
    assert case.source == ""
    assert case.confusion_chapters == []


def test_rejects_product_description_too_long() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "product_description": "x" * 301})


def test_accepts_arbitrary_source_string() -> None:
    # source is no longer a Literal (v2 uses ""); any string is valid.
    assert EvalCase(**{**VALID_FIELDS, "source": ""}).source == ""
    assert EvalCase(**{**VALID_FIELDS, "source": "ecommerce"}).source == "ecommerce"


# ---------------------------------------------------------------------------
# EvalCase — mode (required, six-valued)
# ---------------------------------------------------------------------------


def test_mode_is_required() -> None:
    fields = {k: v for k, v in VALID_FIELDS.items() if k != "mode"}
    with pytest.raises(ValidationError):
        EvalCase(**fields)


@pytest.mark.parametrize(
    "mode", ["direct", "colloquial", "poverty", "negation", "frontier", "multi_attr"]
)
def test_accepts_all_six_modes(mode: str) -> None:
    assert EvalCase(**{**VALID_FIELDS, "mode": mode}).mode == mode


def test_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "mode": "sarcastic"})


# ---------------------------------------------------------------------------
# EvalCase — answer_chapter (int, must match expected_ncm prefix)
# ---------------------------------------------------------------------------


def test_answer_chapter_is_required() -> None:
    fields = {k: v for k, v in VALID_FIELDS.items() if k != "answer_chapter"}
    with pytest.raises(ValidationError):
        EvalCase(**fields)


def test_answer_chapter_is_int() -> None:
    case = EvalCase(**VALID_FIELDS)
    assert isinstance(case.answer_chapter, int)
    assert isinstance(case.chapter, int)


def test_rejects_answer_chapter_not_matching_ncm_prefix() -> None:
    # The c161 bug class: vinegar 2209.00.00 (Ch.22) tagged answer_chapter 20.
    with pytest.raises(ValidationError, match="answer_chapter"):
        EvalCase(**{**VALID_FIELDS, "expected_ncm": "2009.12.00", "answer_chapter": 22})


def test_accepts_answer_chapter_matching_ncm_prefix() -> None:
    case = EvalCase(
        **{**VALID_FIELDS, "expected_ncm": "2009.12.00", "chapter": 20, "answer_chapter": 20}
    )
    assert case.answer_chapter == 20


# ---------------------------------------------------------------------------
# EvalCase — confusion_chapters (list[int])
# ---------------------------------------------------------------------------


def test_confusion_chapters_defaults_to_empty_list() -> None:
    assert EvalCase(**VALID_FIELDS).confusion_chapters == []


def test_confusion_chapters_default_is_not_shared_between_instances() -> None:
    a = EvalCase(**VALID_FIELDS)
    b = EvalCase(**{**VALID_FIELDS, "id": "case-002"})
    a.confusion_chapters.append(20)
    assert b.confusion_chapters == []


def test_accepts_confusion_chapters_list() -> None:
    case = EvalCase(**{**VALID_FIELDS, "confusion_chapters": [20, 21]})
    assert case.confusion_chapters == [20, 21]


def test_rejects_confusion_chapter_containing_answer_chapter() -> None:
    with pytest.raises(ValidationError, match="answer_chapter"):
        EvalCase(**{**VALID_FIELDS, "answer_chapter": 22, "confusion_chapters": [22]})


def test_rejects_duplicate_confusion_chapters() -> None:
    with pytest.raises(ValidationError, match="duplicat"):
        EvalCase(**{**VALID_FIELDS, "confusion_chapters": [20, 20]})


# ---------------------------------------------------------------------------
# Data guard — both real files load cleanly under the single schema
# ---------------------------------------------------------------------------


def test_real_v1_file_loads() -> None:
    data = json.loads(V1_PATH.read_text(encoding="utf-8"))
    suite = EvalSuite.model_validate(data)
    assert len(suite.cases) == 30
    assert suite.corpus_chapters == [22]


def test_real_v2_file_loads() -> None:
    data = json.loads(V2_PATH.read_text(encoding="utf-8"))
    suite = EvalSuite.model_validate(data)
    assert len(suite.cases) == 350
    assert {c.answer_chapter for c in suite.cases} == {20, 21, 22}


# ---------------------------------------------------------------------------
# CaseResult — predicted_ncms length invariant
# ---------------------------------------------------------------------------


def _case_result(predicted: list[str]) -> dict:
    return {
        "case_id": "case-001",
        "expected_ncm": "2203.00.00",
        "predicted_ncms": predicted,
        "top_1_hit": False,
        "top_3_hit": False,
    }


def test_case_result_predicted_ncms_must_be_length_three() -> None:
    with pytest.raises(ValidationError, match="3"):
        CaseResult(**_case_result(["2203.00.00", "2202.10.00"]))


def test_case_result_accepts_exactly_three_predicted_ncms() -> None:
    result = CaseResult(**_case_result(["2203.00.00", "2202.10.00", "2201.10.00"]))
    assert len(result.predicted_ncms) == 3


# ---------------------------------------------------------------------------
# EvalReport — accuracy derived from hit counts
# ---------------------------------------------------------------------------


def test_eval_report_accuracy_computed_from_hits() -> None:
    report = EvalReport(total=30, top_1_hits=6, top_3_hits=12, per_case=[])
    assert report.top_1_accuracy == pytest.approx(0.2)
    assert report.top_3_accuracy == pytest.approx(0.4)


def test_eval_report_accuracy_is_zero_when_total_is_zero() -> None:
    report = EvalReport(total=0, top_1_hits=0, top_3_hits=0, per_case=[])
    assert report.top_1_accuracy == 0.0
    assert report.top_3_accuracy == 0.0
