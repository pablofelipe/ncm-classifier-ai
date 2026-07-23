import re
from dataclasses import dataclass

from src.core.domain.ncm import NCM_CODE_RE

_LEVEL_DASH_RE = re.compile(r"^-+\s*")
_OUTROS_RE = re.compile(r"\boutr[oa]s\b", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def clean_level_text(text: str) -> str:
    """Normalize a hierarchical-level description for context composition.

    Internal newlines become spaces, level dashes ("- ", "-- ") and trailing
    ":"/"." are stripped; separators are the composer's responsibility.
    """
    cleaned = _WS_RE.sub(" ", text).strip()
    cleaned = _LEVEL_DASH_RE.sub("", cleaned)
    return cleaned.rstrip(".:").strip()


def is_substantive(cleaned: str) -> bool:
    """True when content remains after discarding "Outros"/"Outras" filler."""
    residue = _OUTROS_RE.sub("", cleaned)
    return bool(re.sub(r"[\W_]+", "", residue))


@dataclass
class RawRow:
    ncm: str | None
    ex: str | None
    description: str | None
    ipi_rate: str | None
    row_number: int


@dataclass
class ExTIPI:
    ex: str
    description: str
    ipi_rate: str


@dataclass
class TIPIEntry:
    ncm: str
    section: str
    chapter: str
    heading: str
    subheading: str
    description: str
    ipi_rate: str
    ex_tipi: list[ExTIPI] | None
    raw_row: int
    heading_description: str = ""
    subheading_description: str = ""


def parse_tipi_rows(
    rows: list[RawRow],
    chapter: str = "22",
    section: str = "IV",
) -> list[TIPIEntry]:
    """Parse raw TIPI rows into NCM entries with hierarchical context.

    Rows are classified chapter-agnostically by digit count (dots stripped):
    4 = heading, 5-6 = subheading, 7 = partial item, 8 = full NCM. Hierarchical
    rows are consumed to build heading_description / subheading_description on
    the NCM entries that follow them — they never become entries themselves.
    """
    result: list[TIPIEntry] = []
    current: TIPIEntry | None = None
    current_ex: list[ExTIPI] = []
    heading_digits = ""
    heading_desc = ""
    # (digits, cleaned_desc) of substantive intermediate levels under the
    # current heading; pruned by digit-prefix match at each NCM, so stacked
    # siblings never leak into cousins.
    intermediates: list[tuple[str, str]] = []

    def _flush() -> None:
        nonlocal current
        if current is not None:
            current.ex_tipi = current_ex if current_ex else None
            result.append(current)
            current = None

    for row in rows:
        ncm = (row.ncm or "").strip()

        if not ncm.startswith(chapter):
            continue

        ex = (row.ex or "").strip()
        desc = (row.description or "").strip()
        rate = row.ipi_rate or ""

        if ex:
            if current is not None and current.ncm == ncm:
                current_ex.append(ExTIPI(ex=ex, description=desc, ipi_rate=rate))
            continue

        digits = ncm.replace(".", "")
        if not digits.isdigit():
            continue

        if len(digits) == 4:
            heading_digits = digits
            heading_desc = clean_level_text(desc)
            intermediates = []
        elif len(digits) in (5, 6, 7):
            cleaned = clean_level_text(desc)
            if is_substantive(cleaned):
                intermediates.append((digits, cleaned))
        elif len(digits) == 8 and NCM_CODE_RE.match(ncm):
            _flush()
            ancestors = sorted(
                (lvl for lvl in intermediates if digits.startswith(lvl[0])),
                key=lambda lvl: len(lvl[0]),
            )
            current = TIPIEntry(
                ncm=ncm,
                section=section,
                chapter=chapter,
                heading=f"{ncm[0:2]}.{ncm[2:4]}",
                subheading=ncm[0:7],
                description=desc,
                ipi_rate=rate,
                ex_tipi=None,
                raw_row=row.row_number,
                heading_description=heading_desc if digits[:4] == heading_digits else "",
                subheading_description=". ".join(text for _, text in ancestors),
            )
            current_ex = []
        # FUTURE: chapters 01-09 leading-zero handling (Excel strips the zero:
        # "1.01", "101.2" → 3-digit patterns); skipped without crashing.

    _flush()
    return result
