import pytest
from pydantic import ValidationError

from eval.schema import EvalCase, EvalSuite


# ---------------------------------------------------------------------------
# Fixture: campos válidos reutilizáveis
# ---------------------------------------------------------------------------

VALID_FIELDS: dict = {
    "id": "case-001",
    "product_name": "Cerveja Pilsen Lata 350ml",
    "product_description": "Cerveja tipo Pilsen, lata de alumínio 350ml, teor alcoólico 4,9% vol.",
    "expected_ncm": "2203.00.00",
    "answer_chapter": "22",
    "difficulty": "easy",
    "rationale": "Produto claramente identificado como cerveja de malte pelo fabricante",
    "source": "ecommerce",
}

VALID_SUITE_KWARGS: dict = {
    "version": "v1",
    "tipi_version": "tipi_20260608.xlsx",
    "chapter_scope": "22",
    "cases": [],
}


# ---------------------------------------------------------------------------
# EvalSuite — happy path
# ---------------------------------------------------------------------------


def test_loads_valid_minimal_suite() -> None:
    suite = EvalSuite(**VALID_SUITE_KWARGS)
    assert suite.version == "v1"
    assert suite.chapter_scope == "22"
    assert suite.cases == []


def test_loads_valid_suite_with_one_case() -> None:
    suite = EvalSuite(**{**VALID_SUITE_KWARGS, "cases": [EvalCase(**VALID_FIELDS)]})
    assert len(suite.cases) == 1
    assert suite.cases[0].expected_ncm == "2203.00.00"


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
# EvalSuite — escopo do capítulo (out-of-scope agora é legítimo)
# ---------------------------------------------------------------------------


def test_accepts_ncm_within_chapter_scope() -> None:
    suite = EvalSuite(**{**VALID_SUITE_KWARGS, "cases": [EvalCase(**VALID_FIELDS)]})
    assert suite.cases[0].expected_ncm == "2203.00.00"


def test_accepts_out_of_scope_answer_chapter_case() -> None:
    # Caso fronteira: resposta correta vive em outro capítulo (ex.: suco -> Cap.20).
    cross = EvalCase(**{
        **VALID_FIELDS,
        "expected_ncm": "2009.12.00",
        "answer_chapter": "20",
        "confusion_chapters": ["22"],
    })
    suite = EvalSuite(**{**VALID_SUITE_KWARGS, "cases": [cross]})
    assert suite.cases[0].answer_chapter == "20"


# ---------------------------------------------------------------------------
# EvalCase — campo id
# ---------------------------------------------------------------------------


def test_rejects_id_with_wrong_format() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "id": "cap22-001"})


def test_rejects_id_without_leading_zeros() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "id": "case-1"})


def test_accepts_id_with_three_digits() -> None:
    case = EvalCase(**{**VALID_FIELDS, "id": "case-042"})
    assert case.id == "case-042"


# ---------------------------------------------------------------------------
# EvalCase — comprimentos
# ---------------------------------------------------------------------------


def test_rejects_product_name_too_long() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "product_name": "x" * 101})


def test_rejects_product_description_too_long() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "product_description": "x" * 301})


def test_rejects_rationale_too_short() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "rationale": "Muito curto"})


# ---------------------------------------------------------------------------
# EvalCase — answer_chapter
# ---------------------------------------------------------------------------


def test_answer_chapter_is_required() -> None:
    fields = {k: v for k, v in VALID_FIELDS.items() if k != "answer_chapter"}
    with pytest.raises(ValidationError):
        EvalCase(**fields)


def test_rejects_answer_chapter_single_digit() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "answer_chapter": "2"})


def test_rejects_answer_chapter_with_letters() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "answer_chapter": "AB"})


def test_rejects_answer_chapter_not_matching_ncm_prefix() -> None:
    with pytest.raises(ValidationError, match="answer_chapter"):
        EvalCase(**{**VALID_FIELDS, "expected_ncm": "2009.12.00", "answer_chapter": "22"})


def test_accepts_answer_chapter_matching_ncm_prefix() -> None:
    case = EvalCase(**{
        **VALID_FIELDS,
        "expected_ncm": "2009.12.00",
        "answer_chapter": "20",
    })
    assert case.answer_chapter == "20"


# ---------------------------------------------------------------------------
# EvalCase — confusion_chapters
# ---------------------------------------------------------------------------


def test_confusion_chapters_defaults_to_empty_list() -> None:
    case = EvalCase(**VALID_FIELDS)
    assert case.confusion_chapters == []


def test_confusion_chapters_default_is_not_shared_between_instances() -> None:
    a = EvalCase(**VALID_FIELDS)
    b = EvalCase(**{**VALID_FIELDS, "id": "case-002"})
    a.confusion_chapters.append("20")
    assert b.confusion_chapters == []


def test_accepts_confusion_chapters_list() -> None:
    case = EvalCase(**{**VALID_FIELDS, "confusion_chapters": ["20", "21"]})
    assert case.confusion_chapters == ["20", "21"]


def test_rejects_confusion_chapter_containing_answer_chapter() -> None:
    with pytest.raises(ValidationError, match="answer_chapter"):
        EvalCase(**{**VALID_FIELDS, "answer_chapter": "22", "confusion_chapters": ["22"]})


def test_rejects_duplicate_confusion_chapters() -> None:
    with pytest.raises(ValidationError, match="duplicat"):
        EvalCase(**{**VALID_FIELDS, "confusion_chapters": ["20", "20"]})


def test_rejects_confusion_chapter_with_single_digit() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "confusion_chapters": ["2"]})


def test_rejects_confusion_chapter_with_letters() -> None:
    with pytest.raises(ValidationError):
        EvalCase(**{**VALID_FIELDS, "confusion_chapters": ["AB"]})
