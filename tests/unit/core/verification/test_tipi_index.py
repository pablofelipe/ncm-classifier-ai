from src.core.verification.deterministic import TIPIIndex, VerificationStatus


def _codes() -> dict[str, dict[str, str]]:
    return {
        "22030000": {"chapter": "22", "heading": "22.03", "description": "Cervejas de malte"},
        "20091100": {"chapter": "20", "heading": "20.09", "description": "Suco de laranja"},
        "21069010": {
            "chapter": "21",
            "heading": "22.03",
            "description": "hierarquia inconsistente",
        },
    }


def test_passes_for_existing_code_with_consistent_hierarchy() -> None:
    result = TIPIIndex(_codes()).verify("22030000")
    assert result.status == VerificationStatus.PASSED


def test_passes_for_code_from_different_chapter_within_same_multi_chapter_index() -> None:
    # ADR-0014: the index spans Ch.20/21/22 (NCM_CHAPTER=beverage); a code from
    # any covered chapter passes as long as it exists and its hierarchy is consistent.
    result = TIPIIndex(_codes()).verify("20091100")
    assert result.status == VerificationStatus.PASSED


def test_rejects_code_not_found_in_index() -> None:
    result = TIPIIndex(_codes()).verify("99999999")
    assert result.status == VerificationStatus.CODE_NOT_FOUND


def test_rejects_code_with_inconsistent_hierarchy() -> None:
    result = TIPIIndex(_codes()).verify("21069010")
    assert result.status == VerificationStatus.INVALID_HIERARCHY


def test_wrong_chapter_status_no_longer_exists() -> None:
    # ADR-0014: chapter-coherence check dropped — a fixed expected_chapter
    # doesn't fit a multi-chapter corpus. Existence + hierarchy only.
    assert not hasattr(VerificationStatus, "WRONG_CHAPTER")


def test_verify_takes_only_code_no_expected_chapter() -> None:
    result = TIPIIndex(_codes()).verify("22030000")
    assert result.code == "22030000"
