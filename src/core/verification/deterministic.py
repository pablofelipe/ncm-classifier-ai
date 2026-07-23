"""Deterministic TIPI verification (ADR-0002, wired in ADR-0014).

``TIPIIndex.verify`` checks existence + hierarchy consistency and is called by
``ClassifyProduct`` after rerank, when a ``TIPIIndex`` is injected. Chapter
coherence is not checked here (ADR-0014): the index can span multiple
chapters (``NCM_CHAPTER=beverage`` covers Ch.20/21/22), so a fixed expected
chapter doesn't fit — existence against the loaded index is the equivalent
check for codes outside its scope.
"""

from dataclasses import dataclass
from enum import StrEnum

from src.core.domain.ncm import NCMCode


class VerificationStatus(StrEnum):
    PASSED = "passed"
    CODE_NOT_FOUND = "code_not_found"
    INVALID_HIERARCHY = "invalid_hierarchy"


@dataclass
class VerificationResult:
    status: VerificationStatus
    code: NCMCode
    message: str

    @property
    def passed(self) -> bool:
        return self.status == VerificationStatus.PASSED


class TIPIIndex:
    """In-memory index of valid NCM codes and their hierarchy.

    No I/O here — receives an already-loaded ``codes`` dict (whoever wires this
    in is responsible for building it from the parsed TIPI entries).

    Expected schema: {NCMCode("2203.00.00"): {"chapter": "22", "heading": "22.03", ...}}
    heading uses dotted format (e.g. "22.03") as produced by tipi_parsing.parse_tipi_rows.
    """

    def __init__(self, codes: dict[NCMCode, dict[str, str]]) -> None:
        self._codes = codes

    def verify(self, code: NCMCode) -> VerificationResult:
        if code not in self._codes:
            return VerificationResult(
                status=VerificationStatus.CODE_NOT_FOUND,
                code=code,
                message=f"NCM {code} not found in TIPI index",
            )
        if not _hierarchy_consistent(code, self._codes[code]):
            return VerificationResult(
                status=VerificationStatus.INVALID_HIERARCHY,
                code=code,
                message=f"NCM {code} digit hierarchy inconsistent with TIPI metadata",
            )
        return VerificationResult(status=VerificationStatus.PASSED, code=code, message="OK")


def _hierarchy_consistent(code: NCMCode, entry: dict[str, str]) -> bool:
    heading = entry.get("heading", "")
    if not heading:
        return True
    return code.matches_heading(heading)
