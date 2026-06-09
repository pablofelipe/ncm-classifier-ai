import re
from dataclasses import dataclass

_NCM_FULL_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


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


def parse_tipi_rows(
    rows: list[RawRow],
    chapter: str = "22",
    section: str = "IV",
) -> list[TIPIEntry]:
    result: list[TIPIEntry] = []
    current: TIPIEntry | None = None
    current_ex: list[ExTIPI] = []

    for row in rows:
        ncm = (row.ncm or "").strip()

        if not ncm.startswith(chapter):
            continue
        if not _NCM_FULL_RE.match(ncm):
            continue

        ex = (row.ex or "").strip()
        desc = (row.description or "").strip()
        rate = row.ipi_rate or ""

        if not ex:
            if current is not None:
                current.ex_tipi = current_ex if current_ex else None
                result.append(current)
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
            )
            current_ex = []
        elif current is not None and current.ncm == ncm:
            current_ex.append(ExTIPI(ex=ex, description=desc, ipi_rate=rate))

    if current is not None:
        current.ex_tipi = current_ex if current_ex else None
        result.append(current)

    return result
