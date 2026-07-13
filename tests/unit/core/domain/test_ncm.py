import pytest

from src.core.domain.ncm import (
    ClassificationCandidate,
    ClassificationResult,
    candidate_metadata_from_entry,
)


def _full_entry() -> dict[str, object]:
    return {
        "ncm": "2201.10.00",
        "section": "IV",
        "chapter": "22",
        "heading": "22.01",
        "subheading": "2201.10",
        "description": "Aguas minerais e aguas gaseificadas",
        "ipi_rate": "2.6",
        "ex_tipi": [{"ex": "1", "description": "natural", "ipi_rate": "NT"}],
        "raw_row": 1926,
    }


def test_candidate_metadata_includes_expected_keys() -> None:
    meta = candidate_metadata_from_entry(_full_entry())
    assert set(meta.keys()) == {
        "ncm_dotted",
        "chapter",
        "heading",
        "subheading",
        "description",
        "ipi_rate",
    }


def test_candidate_metadata_maps_ncm_to_ncm_dotted() -> None:
    meta = candidate_metadata_from_entry(_full_entry())
    assert meta["ncm_dotted"] == "2201.10.00"


def test_candidate_metadata_excludes_raw_row() -> None:
    meta = candidate_metadata_from_entry(_full_entry())
    assert "raw_row" not in meta


def test_candidate_metadata_excludes_ex_tipi() -> None:
    meta = candidate_metadata_from_entry(_full_entry())
    assert "ex_tipi" not in meta


def test_candidate_metadata_values_are_str_or_float_only() -> None:
    meta = candidate_metadata_from_entry(_full_entry())
    assert all(isinstance(v, (str, float)) for v in meta.values())


def _candidate(ncm_code: str = "2202.10.00") -> ClassificationCandidate:
    return ClassificationCandidate(
        ncm_code=ncm_code,
        description="bebida",
        score=0.0,
        metadata={},
    )


def _candidates(n: int) -> list[ClassificationCandidate]:
    return [_candidate() for _ in range(n)]


@pytest.mark.parametrize("n", [0, 1, 2, 4, 5])
def test_rejects_top_candidates_not_length_three(n: int) -> None:
    with pytest.raises(ValueError):
        ClassificationResult(top_candidates=_candidates(n), confidence_label="needs_review")


def test_accepts_exactly_three_candidates() -> None:
    result = ClassificationResult(top_candidates=_candidates(3), confidence_label="needs_review")
    assert len(result.top_candidates) == 3


@pytest.mark.parametrize("label", ["high", "needs_review"])
def test_accepts_valid_confidence_label(label: str) -> None:
    result = ClassificationResult(top_candidates=_candidates(3), confidence_label=label)
    assert result.confidence_label == label


@pytest.mark.parametrize("label", ["confident", "low", "", "HIGH", "needs review"])
def test_rejects_invalid_confidence_label(label: str) -> None:
    with pytest.raises(ValueError):
        ClassificationResult(top_candidates=_candidates(3), confidence_label=label)


def test_escalation_reason_defaults_to_none() -> None:
    result = ClassificationResult(top_candidates=_candidates(3), confidence_label="high")
    assert result.escalation_reason is None


def test_escalation_reason_is_settable() -> None:
    result = ClassificationResult(
        top_candidates=_candidates(3),
        confidence_label="needs_review",
        escalation_reason="code_not_found",
    )
    assert result.escalation_reason == "code_not_found"
