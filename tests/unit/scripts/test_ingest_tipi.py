import json
import re
from pathlib import Path

import pytest

from src.core.domain.tipi_parsing import RawRow, parse_tipi_rows


def _row(
    ncm: str | None,
    ex: str | None = None,
    desc: str = "descrição válida de teste",
    ipi: str = "0",
    row_num: int = 1,
) -> RawRow:
    return RawRow(ncm=ncm, ex=ex, description=desc, ipi_rate=ipi, row_number=row_num)


# ---------------------------------------------------------------------------
# Filtering: which rows are kept
# ---------------------------------------------------------------------------


def test_extracts_valid_full_ncm() -> None:
    rows = [_row("2201.10.00", desc="Águas minerais", ipi="2.6", row_num=1926)]
    entries = parse_tipi_rows(rows)
    assert len(entries) == 1
    assert entries[0].ncm == "2201.10.00"


def test_discards_two_level_heading_row() -> None:
    rows = [_row("22.01"), _row("2201.10.00", ipi="2.6")]
    entries = parse_tipi_rows(rows)
    assert len(entries) == 1
    assert entries[0].ncm == "2201.10.00"


def test_discards_short_subheading_without_second_dot() -> None:
    rows = [_row("2202.9"), _row("2208.3"), _row("2202.91.00")]
    entries = parse_tipi_rows(rows)
    assert len(entries) == 1


def test_discards_heading_without_any_dot() -> None:
    # e.g. "2206" — 4 chars, no dot
    rows = [_row("2206"), _row("2206.00.10")]
    entries = parse_tipi_rows(rows)
    assert len(entries) == 1
    assert entries[0].ncm == "2206.00.10"


def test_discards_deeper_partial_subheading() -> None:
    # e.g. "2207.20.1" — 9 chars, missing last digit
    rows = [_row("2207.20.1"), _row("2207.20.11")]
    entries = parse_tipi_rows(rows)
    assert len(entries) == 1
    assert entries[0].ncm == "2207.20.11"


def test_discards_rows_outside_target_chapter() -> None:
    rows = [_row("2201.10.00"), _row("2301.10.10"), _row("2202.99.00")]
    entries = parse_tipi_rows(rows, chapter="22")
    assert len(entries) == 2
    assert all(e.ncm.startswith("22") for e in entries)


def test_returns_empty_list_when_no_matching_rows() -> None:
    rows = [_row("22.01"), _row("2202.9"), _row("23.01")]
    entries = parse_tipi_rows(rows, chapter="22")
    assert entries == []


# ---------------------------------------------------------------------------
# Grouping of ex-tariff entries
# ---------------------------------------------------------------------------


def test_groups_ex_tipi_with_parent_ncm() -> None:
    rows = [
        _row("2201.10.00", ipi="2.6"),
        _row("2201.10.00", ex="1", desc="Recipientes < 10 litros", ipi="NT"),
        _row("2201.10.00", ex="2", desc="Recipientes >= 10 litros", ipi="NT"),
    ]
    entries = parse_tipi_rows(rows)
    assert len(entries) == 1
    assert entries[0].ex_tipi is not None
    assert len(entries[0].ex_tipi) == 2


def test_ex_tipi_entry_preserves_ex_number_description_and_rate() -> None:
    rows = [
        _row("2203.00.00", ipi="3.9"),
        _row("2203.00.00", ex="1", desc="Chope", ipi="3.9"),
    ]
    entries = parse_tipi_rows(rows)
    ex = entries[0].ex_tipi[0]  # type: ignore[index]
    assert ex.ex == "1"
    assert ex.description == "Chope"
    assert ex.ipi_rate == "3.9"


def test_entry_without_ex_has_null_ex_tipi() -> None:
    rows = [_row("2203.00.00", ipi="3.9")]
    entries = parse_tipi_rows(rows)
    assert entries[0].ex_tipi is None


def test_multiple_ncms_keep_independent_ex_tipi_lists() -> None:
    rows = [
        _row("2201.10.00", ipi="2.6"),
        _row("2201.10.00", ex="1", desc="Ex A"),
        _row("2202.10.00", ipi="2.6"),
        _row("2202.10.00", ex="1", desc="Ex B"),
    ]
    entries = parse_tipi_rows(rows)
    assert len(entries) == 2
    assert entries[0].ex_tipi is not None and len(entries[0].ex_tipi) == 1
    assert entries[1].ex_tipi is not None and len(entries[1].ex_tipi) == 1
    assert entries[0].ex_tipi[0].description == "Ex A"
    assert entries[1].ex_tipi[0].description == "Ex B"


# ---------------------------------------------------------------------------
# Field derivation
# ---------------------------------------------------------------------------


def test_heading_derived_from_ncm() -> None:
    entries = parse_tipi_rows([_row("2202.10.00")])
    assert entries[0].heading == "22.02"


def test_subheading_derived_from_ncm() -> None:
    entries = parse_tipi_rows([_row("2202.10.00")])
    assert entries[0].subheading == "2202.10"


def test_heading_and_subheading_work_for_any_chapter() -> None:
    entries = parse_tipi_rows([_row("0101.21.00")], chapter="01", section="I")
    assert entries[0].heading == "01.01"
    assert entries[0].subheading == "0101.21"


def test_raw_row_number_preserved() -> None:
    entries = parse_tipi_rows([_row("2201.10.00", row_num=1926)])
    assert entries[0].raw_row == 1926


def test_section_and_chapter_set_on_all_entries() -> None:
    rows = [_row("2201.10.00"), _row("2202.10.00")]
    entries = parse_tipi_rows(rows, chapter="22", section="IV")
    assert all(e.section == "IV" for e in entries)
    assert all(e.chapter == "22" for e in entries)


def test_description_and_ipi_rate_preserved() -> None:
    entries = parse_tipi_rows([_row("2201.10.00", desc="Águas minerais", ipi="2.6")])
    assert entries[0].description == "Águas minerais"
    assert entries[0].ipi_rate == "2.6"


# ---------------------------------------------------------------------------
# Hierarchical context (ADR-0005): heading_description / subheading_description
# ---------------------------------------------------------------------------


def test_heading_description_attached_to_following_ncm() -> None:
    rows = [
        _row("22.01", desc="Águas, incluindo as águas minerais, naturais ou artificiais"),
        _row("2201.10.00", desc="- Águas minerais e águas gaseificadas"),
    ]
    entries = parse_tipi_rows(rows)
    assert entries[0].heading_description == (
        "Águas, incluindo as águas minerais, naturais ou artificiais"
    )


def test_heading_without_dot_classified_as_heading() -> None:
    # "2206" — the XLSX omits the dot on this heading
    rows = [
        _row("2206", desc="Outras bebidas fermentadas (por exemplo, sidra, perada)"),
        _row("2206.00.10", desc="Sidra"),
    ]
    entries = parse_tipi_rows(rows)
    assert "bebidas fermentadas" in entries[0].heading_description


def test_multi_level_chain_concatenated_general_to_specific() -> None:
    rows = [
        _row("22.04", desc="Vinhos de uvas frescas"),
        _row("2204.2", desc="- Outros vinhos; mostos de uvas:"),
        _row("2204.22", desc="-- Em recipientes de capacidade superior a 2 l"),
        _row("2204.22.1", desc="Vinhos"),
        _row("2204.22.11", desc="Em recipientes de capacidade não superior a 5 l"),
    ]
    entries = parse_tipi_rows(rows)
    assert entries[0].subheading_description == (
        "Outros vinhos; mostos de uvas. Em recipientes de capacidade superior a 2 l. Vinhos"
    )


def test_sibling_subheading_does_not_leak_into_cousin_ncm() -> None:
    rows = [
        _row("22.04", desc="Vinhos de uvas frescas"),
        _row("2204.2", desc="- Outros vinhos; mostos de uvas"),
        _row("2204.22", desc="-- Em recipientes de 2 a 10 l"),
        _row("2204.22.1", desc="Vinhos"),
        _row("2204.22.11", desc="Em recipientes de até 5 l"),
        _row("2204.29", desc="-- Outros"),
        _row("2204.29.10", desc="Vinhos"),
    ]
    entries = parse_tipi_rows(rows)
    cousin = next(e for e in entries if e.ncm == "2204.29.10")
    assert cousin.subheading_description == "Outros vinhos; mostos de uvas"


def test_skips_empty_other_levels() -> None:
    rows = [
        _row("22.02", desc="Águas adicionadas de açúcar"),
        _row("2202.9", desc="- Outras:"),
        _row("2202.91.00", desc="-- Cerveja sem álcool"),
    ]
    entries = parse_tipi_rows(rows)
    assert entries[0].subheading_description == ""


def test_keeps_levels_with_substantive_content_despite_outros_word() -> None:
    rows = [
        _row("22.04", desc="Vinhos de uvas frescas"),
        _row("2204.2", desc="- Outros vinhos; mostos de uvas"),
        _row("2204.21.00", desc="-- Em recipientes de capacidade não superior a 2 l"),
    ]
    entries = parse_tipi_rows(rows)
    assert entries[0].subheading_description == "Outros vinhos; mostos de uvas"


def test_strips_level_dashes() -> None:
    rows = [
        _row("22.08", desc="Aguardentes, licores e outras bebidas espirituosas"),
        _row("2208.3", desc="- Uísques"),
        _row("2208.30.20", desc="Em embalagens de capacidade inferior ou igual a 2 l"),
    ]
    entries = parse_tipi_rows(rows)
    assert entries[0].subheading_description == "Uísques"


def test_normalizes_internal_newline() -> None:
    rows = [
        _row("22.04", desc="Vinhos de uvas frescas, excluindo os da\nposição 20.09"),
        _row("2204.10.10", desc="Tipo champanha"),
    ]
    entries = parse_tipi_rows(rows)
    assert "\n" not in entries[0].heading_description
    assert "da posição 20.09" in entries[0].heading_description


def test_strips_trailing_colon() -> None:
    rows = [
        _row("22.04", desc="Vinhos de uvas frescas"),
        _row("2204.2", desc="- Outros vinhos; mostos de uvas:"),
        _row("2204.21.00", desc="-- Em recipientes"),
    ]
    entries = parse_tipi_rows(rows)
    assert entries[0].subheading_description.endswith("mostos de uvas")


def test_strips_trailing_period() -> None:
    rows = [
        _row("22.05", desc="Vermutes e outros vinhos aromatizados por substâncias aromáticas."),
        _row("2205.10.00", desc="- Em recipientes de capacidade não superior a 2 l"),
    ]
    entries = parse_tipi_rows(rows)
    assert entries[0].heading_description.endswith("aromáticas")


def test_heading_description_empty_when_position_has_no_heading_row() -> None:
    # 2203/2209: the 4-digit position has no row of its own — the 8-digit NCM
    # line carries the position text itself. Must yield "" (never None).
    rows = [
        _row("22.02", desc="Águas adicionadas de açúcar"),
        _row("2202.10.00", desc="- Águas com açúcar"),
        _row("2203.00.00", desc="Cervejas de malte."),
    ]
    entries = parse_tipi_rows(rows)
    beer = next(e for e in entries if e.ncm == "2203.00.00")
    assert beer.heading_description == ""
    assert beer.subheading_description == ""


def test_subheading_before_heading_does_not_crash() -> None:
    # Defensive for future chapters with different structure: an orphan
    # intermediate before any heading must not break the parser.
    rows = [
        _row("2202.9", desc="- Outras bebidas especiais"),
        _row("2203.00.00", desc="Cervejas de malte."),
    ]
    entries = parse_tipi_rows(rows)
    assert len(entries) == 1
    assert entries[0].heading_description == ""


# ---------------------------------------------------------------------------
# Data guard — latest generated data/tipi/tipi_22_*.json
# Pins the bidirectional-completeness invariant (34 base NCMs, 15 with
# ex-tarifário) and catches the "hierarchical line leaked into entries"
# failure mode directly.
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[3]
_NCM_8DIGIT = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


@pytest.fixture(scope="module")
def latest_entries() -> list[dict]:
    files = sorted((_ROOT / "data" / "tipi").glob("tipi_22_*.json"))
    assert files, "no tipi_22_*.json found — run: python scripts/ingest_tipi.py"
    payload = json.loads(files[-1].read_text(encoding="utf-8"))
    return payload["entries"]


def test_chapter22_has_exactly_34_base_ncms(latest_entries: list[dict]) -> None:
    assert len(latest_entries) == 34


def test_chapter22_has_15_entries_with_ex_tipi(latest_entries: list[dict]) -> None:
    assert sum(1 for e in latest_entries if e["ex_tipi"]) == 15


def test_no_hierarchical_line_leaked_into_entries(latest_entries: list[dict]) -> None:
    assert all(_NCM_8DIGIT.match(e["ncm"]) for e in latest_entries)


@pytest.mark.parametrize(
    "ncm, term",
    [
        ("2204.21.00", "vinhos"),  # ADR-0004 anchor: wine absent from own text
        ("2205.10.00", "vermutes"),  # ADR-0004 anchor: vermouth absent
        ("2208.30.20", "uísques"),  # ADR-0004 anchor: whisky absent
    ],
)
def test_anchor_ncm_gains_parent_context_term(
    latest_entries: list[dict], ncm: str, term: str
) -> None:
    entry = next(e for e in latest_entries if e["ncm"] == ncm)
    context = entry.get("heading_description", "") + " " + entry.get("subheading_description", "")
    assert term in context.lower()
