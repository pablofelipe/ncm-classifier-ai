from src.core.domain.tipi_parsing import ExTIPI, RawRow, TIPIEntry, parse_tipi_rows


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
