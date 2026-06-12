import re
from dataclasses import dataclass
from enum import StrEnum

_NCM_FORMAT_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


def validate_ncm_format(code: str) -> bool:
    """Return True if code matches the XXXX.XX.XX NCM dot-notation format."""
    return bool(_NCM_FORMAT_RE.fullmatch(code))


class VerificationStatus(StrEnum):
    PASSED = "passed"
    CODE_NOT_FOUND = "code_not_found"
    WRONG_CHAPTER = "wrong_chapter"
    INVALID_HIERARCHY = "invalid_hierarchy"


@dataclass
class VerificationResult:
    status: VerificationStatus
    code: str
    message: str

    @property
    def passed(self) -> bool:
        return self.status == VerificationStatus.PASSED


class TIPIIndex:
    """In-memory index of valid NCM codes and their hierarchy.

    Populated by the retrieval adapter (src/retrieval/tipi_loader.py), never
    by this module. No I/O here — receives an already-loaded dict.

    Expected schema: {"22030000": {"chapter": "22", "heading": "22.03", "description": "..."}}
    heading uses dotted format (e.g. "22.03") as produced by tipi_parsing.parse_tipi_rows.
    """

    def __init__(self, codes: dict[str, dict[str, str]]) -> None:
        self._codes = codes

    def verify(self, code: str, expected_chapter: str) -> VerificationResult:
        if code not in self._codes:
            return VerificationResult(
                status=VerificationStatus.CODE_NOT_FOUND,
                code=code,
                message=f"NCM {code} not found in TIPI index",
            )
        if not code.startswith(expected_chapter):
            return VerificationResult(
                status=VerificationStatus.WRONG_CHAPTER,
                code=code,
                message=f"NCM {code} belongs to chapter {code[:2]}, expected {expected_chapter}",
            )
        if not _hierarchy_consistent(code, self._codes[code]):
            return VerificationResult(
                status=VerificationStatus.INVALID_HIERARCHY,
                code=code,
                message=f"NCM {code} digit hierarchy inconsistent with TIPI metadata",
            )
        return VerificationResult(status=VerificationStatus.PASSED, code=code, message="OK")


def _hierarchy_consistent(code: str, entry: dict[str, str]) -> bool:
    if len(code) != 8:
        return False
    heading = entry.get("heading", "")
    if not heading:
        return True
    # Normalize dotted format ("22.03") or plain ("2203") before comparing
    heading_digits = heading.replace(".", "")
    return code.startswith(heading_digits)
