"""Cross-validation of the eval set against the indexed TIPI data.

Two layers:
  * Pure unit tests of ``cross_validate_against_tipi`` with synthetic suites.
  * A data-guard test that wires the real eval/v1_cases.json against the real
    data/tipi/tipi_22_*.json and fails if an in-scope expected_ncm is absent.

In-scope rule: a case is in-scope when ``answer_chapter == suite.chapter_scope``.
  * in-scope  → expected_ncm must exist in the TIPI index (hard failure)
  * any case  → expected_ncm must start with answer_chapter (hard ValueError)
  * out-of-scope absent from TIPI → informational warning only
"""
import json
import warnings
from pathlib import Path

import pytest

from eval.run_eval import cross_validate_against_tipi, load_eval_suite, main
from eval.schema import EvalCase, EvalSuite

ROOT = Path(__file__).resolve().parents[3]
EVAL_PATH = ROOT / "eval" / "v1_cases.json"
TIPI_PATH = ROOT / "data" / "tipi" / "tipi_22_20260608.json"


# ---------------------------------------------------------------------------
# helpers — build minimal *valid* synthetic suites
# ---------------------------------------------------------------------------

def _case(
    case_id: str,
    ncm: str,
    answer_chapter: str = "22",
    confusion: list[str] | None = None,
) -> EvalCase:
    return EvalCase(
        id=case_id,
        product_name="produto",
        product_description="descricao do produto",
        expected_ncm=ncm,
        answer_chapter=answer_chapter,
        confusion_chapters=confusion or [],
        difficulty="easy",
        rationale="rationale com mais de vinte caracteres",
        source="synthetic",
    )


def _suite(*cases: EvalCase, chapter_scope: str = "22") -> EvalSuite:
    return EvalSuite(
        version="test",
        tipi_version="test",
        chapter_scope=chapter_scope,
        cases=list(cases),
    )


# ---------------------------------------------------------------------------
# cross_validate_against_tipi — pure logic
# ---------------------------------------------------------------------------

def test_in_scope_present_is_not_missing() -> None:
    report = cross_validate_against_tipi(
        _suite(_case("case-001", "2203.00.00")), {"2203.00.00"}
    )
    assert report.in_scope_missing == []


def test_in_scope_missing_ncm_fails() -> None:
    report = cross_validate_against_tipi(
        _suite(_case("case-001", "2299.99.99")), {"2203.00.00"}
    )
    assert report.in_scope_missing == ["case-001"]


def test_out_of_scope_emits_warning_not_failure() -> None:
    report = cross_validate_against_tipi(
        _suite(_case("case-001", "2009.12.00", answer_chapter="20")), {"2203.00.00"}
    )
    assert report.in_scope_missing == []
    assert report.out_of_scope_warned == ["case-001"]


@pytest.mark.parametrize(
    "answer_chapter, valid_ncm, corrupted_ncm",
    [
        ("22", "2203.00.00", "2009.12.00"),  # in-scope:  prefix 20 != 22
        ("20", "2009.12.00", "2203.00.00"),  # out-scope: prefix 22 != 20
    ],
)
def test_prefix_mismatch_always_fails(
    answer_chapter: str, valid_ncm: str, corrupted_ncm: str
) -> None:
    case = _case("case-001", valid_ncm, answer_chapter=answer_chapter)
    # Bypass the schema (which forbids the mismatch) to exercise run_eval's
    # defensive hard check on a hand-built / corrupted suite.
    case.expected_ncm = corrupted_ncm
    with pytest.raises(ValueError, match="answer_chapter"):
        cross_validate_against_tipi(_suite(case), {"2203.00.00", "2009.12.00"})


def test_report_ok_false_when_any_in_scope_missing() -> None:
    report = cross_validate_against_tipi(
        _suite(_case("case-001", "2203.00.00"), _case("case-002", "2299.99.99")),
        {"2203.00.00"},
    )
    assert report.ok is False


def test_report_ok_true_when_only_out_of_scope_absent() -> None:
    report = cross_validate_against_tipi(
        _suite(_case("case-001", "2009.12.00", answer_chapter="20")), {"2203.00.00"}
    )
    assert report.ok is True


def test_report_structure_complete() -> None:
    report = cross_validate_against_tipi(
        _suite(
            _case("case-001", "2203.00.00"),                       # in-scope present
            _case("case-002", "2299.99.99"),                       # in-scope missing
            _case("case-003", "2009.12.00", answer_chapter="20"),  # out-of-scope warned
        ),
        {"2203.00.00"},
    )
    assert (
        report.total,
        report.in_scope,
        report.in_scope_present,
        report.in_scope_missing,
        report.out_of_scope,
        report.out_of_scope_warned,
        report.ok,
    ) == (3, 2, 1, ["case-002"], 1, ["case-003"], False)


# ---------------------------------------------------------------------------
# data guard — real eval set vs real TIPI index
# (RED until Checkpoint 3 migrates v1_cases.json to the new schema)
# ---------------------------------------------------------------------------

def _load_tipi_ncms(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {entry["ncm"] for entry in payload["entries"]}


@pytest.fixture(scope="module")
def real_report():
    suite = load_eval_suite(EVAL_PATH)
    return cross_validate_against_tipi(suite, _load_tipi_ncms(TIPI_PATH))


def test_every_in_scope_expected_ncm_exists_in_tipi(real_report) -> None:
    assert real_report.in_scope_missing == [], (
        f"in-scope case(s) reference NCMs absent from the TIPI index: "
        f"{real_report.in_scope_missing}"
    )


def test_out_of_scope_cases_emit_warning_only(real_report) -> None:
    for cid in real_report.out_of_scope_warned:
        warnings.warn(
            f"out-of-scope case {cid}: expected_ncm fora do Cap.22 "
            "(esperado — classificação correta em outro capítulo)",
            stacklevel=2,
        )
    assert real_report.out_of_scope >= len(real_report.out_of_scope_warned)


# ---------------------------------------------------------------------------
# main() — CI gate (exit code + report formatting)
#
# The gate under test is cross-validation; the measurement layer is faked so
# the unit tier never needs the Chroma index or the real embedding model.
# ---------------------------------------------------------------------------

class _FakeUseCase:
    def execute(self, query) -> object:
        from src.core.domain.ncm import ClassificationCandidate, ClassificationResult

        candidates = [
            ClassificationCandidate(ncm_code=f"2203.00.0{i}", description="x", score=0.0)
            for i in range(3)
        ]
        return ClassificationResult(
            top_candidates=candidates, confidence_label="needs_review"
        )


def test_main_exits_zero_when_ok(capsys) -> None:
    code = main(
        eval_path=EVAL_PATH, tipi_dir=TIPI_PATH.parent, use_case_factory=_FakeUseCase
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Status: OK" in out


def test_main_exits_one_when_missing(tmp_path, capsys) -> None:
    # forged suite: one in-scope case whose NCM is absent from the real TIPI
    bad = {
        "version": "test",
        "tipi_version": "test",
        "chapter_scope": "22",
        "cases": [
            {
                "id": "case-001",
                "product_name": "x",
                "product_description": "y",
                "expected_ncm": "2299.99.99",
                "answer_chapter": "22",
                "confusion_chapters": [],
                "difficulty": "easy",
                "rationale": "rationale com mais de vinte caracteres",
                "source": "synthetic",
            }
        ],
    }
    p = tmp_path / "bad_cases.json"
    p.write_text(json.dumps(bad), encoding="utf-8")

    code = main(eval_path=p, tipi_dir=TIPI_PATH.parent, use_case_factory=_FakeUseCase)
    out = capsys.readouterr().out
    assert code == 1
    assert "Status: FAIL" in out
    assert "case-001" in out and "2299.99.99" in out
