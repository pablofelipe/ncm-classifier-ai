# I/O adapter — parsing logic lives in src/core/domain/tipi_parsing.py.
# openpyxl chosen over pandas: precise row-number tracking (raw_row field),
# cell-level control for detecting partial subheadings, already in deps.
#
# Usage:
#   python scripts/ingest_tipi.py [chapter]   (default: 22)
#   Output: data/tipi/tipi_<chapter>_YYYYMMDD.json
import json
import re
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.domain.tipi_parsing import RawRow, parse_tipi_rows  # noqa: E402

_BASE_DECREE_RE = re.compile(
    r"Decreto\s+n[º°.]\s*(\d+[\.\d]*),\s*de\s+\d+\s+de\s+\w+\s+de\s+(\d{4})"
)


def _fmt_rate(v: object) -> str:
    """Normalize openpyxl cell value to a clean rate string."""
    if v is None or v == "":
        return ""
    if isinstance(v, float):
        return f"{round(v, 6):g}"   # 3.9000000000000004 -> "3.9"
    return str(v).strip()


def _extract_tipi_version(ws) -> str:  # type: ignore[no-untyped-def]
    """Build a human-readable version string from worksheet header rows."""
    row2_val = ws.cell(row=2, column=1).value or ""
    row3_val = ws.cell(row=3, column=1).value or ""

    base_match = _BASE_DECREE_RE.search(str(row2_val))
    base = (
        f"Decreto {base_match.group(1)}/{base_match.group(2)}"
        if base_match
        else "Decreto desconhecido"
    )

    update_lines = [ln.strip() for ln in str(row3_val).splitlines() if ln.strip()]
    last_update = update_lines[-1] if update_lines else ""

    return f"{base} (última atualização: {last_update})" if last_update else base


def _find_latest_xlsx(raw_dir: Path) -> Path:
    files = sorted(raw_dir.glob("tipi_*.xlsx"), reverse=True)
    if not files:
        raise FileNotFoundError(f"No tipi_*.xlsx found in {raw_dir}")
    return files[0]


def _load_raw_rows(xlsx_path: Path, chapter: str) -> tuple[list[RawRow], str]:
    """Open XLSX, walk rows, return (raw_rows_for_chapter, tipi_version)."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.active

    tipi_version = _extract_tipi_version(ws)
    rows: list[RawRow] = []
    in_chapter = False

    for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        ncm_cell = str(row[0]).strip() if row[0] is not None else ""

        if not ncm_cell or ncm_cell.upper().startswith("NCM"):
            continue

        if ncm_cell.startswith(chapter):
            in_chapter = True
        elif in_chapter:
            break   # past chapter boundary

        if not in_chapter:
            continue

        ex_raw = row[1]
        ex = str(ex_raw).strip() if ex_raw is not None else None

        rows.append(
            RawRow(
                ncm=ncm_cell,
                ex=ex if ex else None,
                description=str(row[2]).strip() if row[2] is not None else None,
                ipi_rate=_fmt_rate(row[3]),
                row_number=row_idx,
            )
        )

    wb.close()
    return rows, tipi_version


def ingest(raw_dir: Path, output_dir: Path, chapter: str = "22") -> Path:
    xlsx_path = _find_latest_xlsx(raw_dir)
    print(f"Lendo: {xlsx_path.name}")

    raw_rows, tipi_version = _load_raw_rows(xlsx_path, chapter)
    print(f"Linhas brutas Cap. {chapter}: {len(raw_rows)}")

    entries = parse_tipi_rows(raw_rows, chapter=chapter)
    print(f"Entradas NCM extraídas: {len(entries)}")

    date_tag = datetime.now(UTC).strftime("%Y%m%d")
    output_path = output_dir / f"tipi_{chapter}_{date_tag}.json"

    payload = {
        "tipi_version": tipi_version,
        "extracted_at": datetime.now(UTC).isoformat(),
        "chapter": chapter,
        "source": xlsx_path.name,
        "entries": [asdict(e) for e in entries],
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Escrito: {output_path.relative_to(ROOT)}  ({len(entries)} entradas)")

    version_file = ROOT / "eval" / "tipi_version.txt"
    version_file.write_text(xlsx_path.name + "\n", encoding="utf-8")

    return output_path


if __name__ == "__main__":
    chapter = sys.argv[1] if len(sys.argv) > 1 else "22"
    ingest(
        raw_dir=ROOT / "data" / "tipi" / "raw",
        output_dir=ROOT / "data" / "tipi",
        chapter=chapter,
    )
