import pytest
from pathlib import Path

from src.retrieval.chroma_client import build_document_text, _find_latest_tipi_json


# ---------------------------------------------------------------------------
# build_document_text — fixtures no novo schema (entries)
# ---------------------------------------------------------------------------

@pytest.fixture
def full_entry() -> dict:
    return {
        "description": "- Águas minerais e águas gaseificadas",
        "ipi_rate": "2.6",
        "ex_tipi": [
            {"ex": "1", "description": "Recipientes < 10 litros", "ipi_rate": "NT"},
            {"ex": "2", "description": "Recipientes >= 10 litros", "ipi_rate": "NT"},
        ],
    }


@pytest.fixture
def entry_no_ex() -> dict:
    return {
        "description": "Cervejas de malte",
        "ipi_rate": "3.9",
        "ex_tipi": None,
    }


def test_document_includes_specific_description(full_entry: dict) -> None:
    assert "- Águas minerais e águas gaseificadas" in build_document_text(full_entry)


def test_document_includes_all_ex_tipi_descriptions(full_entry: dict) -> None:
    text = build_document_text(full_entry)
    assert "Recipientes < 10 litros" in text
    assert "Recipientes >= 10 litros" in text


def test_document_labels_ex_tipi_with_ex_number(full_entry: dict) -> None:
    text = build_document_text(full_entry)
    assert "EX 1:" in text
    assert "EX 2:" in text


def test_document_without_ex_tipi_has_no_ex_label(entry_no_ex: dict) -> None:
    assert "EX" not in build_document_text(entry_no_ex)


def test_document_starts_with_description(full_entry: dict) -> None:
    text = build_document_text(full_entry)
    assert text.startswith("- Águas minerais")


# ---------------------------------------------------------------------------
# _find_latest_tipi_json (sem alterações de schema)
# ---------------------------------------------------------------------------

def test_returns_most_recent_json_when_multiple_exist(tmp_path: Path) -> None:
    (tmp_path / "tipi_22_20240101.json").write_text("{}")
    (tmp_path / "tipi_22_20260608.json").write_text("{}")
    result = _find_latest_tipi_json(tmp_path, "22")
    assert result.name == "tipi_22_20260608.json"


def test_raises_when_no_json_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="tipi_22"):
        _find_latest_tipi_json(tmp_path, "22")


def test_ignores_json_from_wrong_chapter(tmp_path: Path) -> None:
    (tmp_path / "tipi_33_20260608.json").write_text("{}")
    with pytest.raises(FileNotFoundError):
        _find_latest_tipi_json(tmp_path, "22")
