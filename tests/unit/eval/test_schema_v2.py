"""Schema tests for the v2 eval suite (EvalCaseV2 / EvalSuiteV2).

The v2 contract is deliberately distinct from v1 (frozen): a single `query`
field instead of product_name/description, integer chapters, a `mode`
dimension, and a multi-chapter corpus (no single `chapter_scope`). v1 stays
untouched; these classes live side by side in eval/schema.py.
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.schema import EvalCaseV2, EvalSuiteV2

ROOT = Path(__file__).resolve().parents[3]
V2_PATH = ROOT / "eval" / "v2_cases.json"

VALID_FIELDS: dict = {
    "id": "c001",
    "query": "Água mineral com gás, 500 ml",
    "expected_ncm": "2201.10.00",
    "difficulty": "easy",
    "mode": "direct",
    "chapter": 22,
    "answer_chapter": 22,
}

VALID_SUITE_KWARGS: dict = {
    "version": "v2",
    "description": "test suite",
    "corpus_chapters": [20, 21, 22],
    "cases": [],
}


# ---------------------------------------------------------------------------
# EvalCaseV2 — happy path
# ---------------------------------------------------------------------------


def test_loads_valid_case() -> None:
    case = EvalCaseV2(**VALID_FIELDS)
    assert case.id == "c001"
    assert case.query == "Água mineral com gás, 500 ml"
    assert case.answer_chapter == 22
    assert case.mode == "direct"


def test_answer_chapter_is_int() -> None:
    case = EvalCaseV2(**VALID_FIELDS)
    assert isinstance(case.answer_chapter, int)
    assert isinstance(case.chapter, int)


# ---------------------------------------------------------------------------
# id format
# ---------------------------------------------------------------------------


def test_rejects_v1_style_id() -> None:
    with pytest.raises(ValidationError):
        EvalCaseV2(**{**VALID_FIELDS, "id": "case-001"})


def test_rejects_id_without_three_digits() -> None:
    with pytest.raises(ValidationError):
        EvalCaseV2(**{**VALID_FIELDS, "id": "c1"})


# ---------------------------------------------------------------------------
# expected_ncm format
# ---------------------------------------------------------------------------


def test_rejects_undotted_ncm() -> None:
    with pytest.raises(ValidationError):
        EvalCaseV2(**{**VALID_FIELDS, "expected_ncm": "22011000"})


# ---------------------------------------------------------------------------
# mode literal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode", ["direct", "colloquial", "poverty", "negation", "frontier", "multi_attr"]
)
def test_accepts_all_six_modes(mode: str) -> None:
    case = EvalCaseV2(**{**VALID_FIELDS, "mode": mode})
    assert case.mode == mode


def test_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        EvalCaseV2(**{**VALID_FIELDS, "mode": "sarcastic"})


# ---------------------------------------------------------------------------
# answer_chapter must match expected_ncm prefix (strict — guards data bugs)
# ---------------------------------------------------------------------------


def test_rejects_answer_chapter_not_matching_ncm_prefix() -> None:
    # The c161 bug class: vinegar 2209.00.00 (Ch.22) tagged answer_chapter 20.
    with pytest.raises(ValidationError, match="answer_chapter"):
        EvalCaseV2(**{**VALID_FIELDS, "expected_ncm": "2209.00.00", "answer_chapter": 20})


def test_accepts_answer_chapter_matching_ncm_prefix() -> None:
    case = EvalCaseV2(
        **{**VALID_FIELDS, "expected_ncm": "2009.12.00", "chapter": 20, "answer_chapter": 20}
    )
    assert case.answer_chapter == 20


# ---------------------------------------------------------------------------
# EvalSuiteV2
# ---------------------------------------------------------------------------


def test_loads_minimal_suite() -> None:
    suite = EvalSuiteV2(**VALID_SUITE_KWARGS)
    assert suite.version == "v2"
    assert suite.corpus_chapters == [20, 21, 22]
    assert suite.cases == []


def test_rejects_duplicate_case_ids() -> None:
    case = EvalCaseV2(**VALID_FIELDS)
    with pytest.raises(ValidationError, match="unique"):
        EvalSuiteV2(**{**VALID_SUITE_KWARGS, "cases": [case, case]})


# ---------------------------------------------------------------------------
# Data guard — the real v2 file loads cleanly under the v2 schema
# ---------------------------------------------------------------------------


def test_real_v2_file_loads() -> None:
    data = json.loads(V2_PATH.read_text(encoding="utf-8"))
    suite = EvalSuiteV2.model_validate(data)
    assert len(suite.cases) == 350
    assert {c.answer_chapter for c in suite.cases} == {20, 21, 22}
