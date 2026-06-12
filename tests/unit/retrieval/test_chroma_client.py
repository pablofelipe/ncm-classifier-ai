import json
from pathlib import Path
from uuid import uuid4

import chromadb
import pytest
from chromadb import Collection

from src.retrieval.chroma_client import (
    _find_latest_tipi_json,
    build_document_text,
    index_entries,
)
from src.retrieval.embedding import EMBEDDING_DIM, E5EmbeddingFunction

# ---------------------------------------------------------------------------
# build_document_text — fixtures no novo schema (entries)
# ---------------------------------------------------------------------------


@pytest.fixture
def full_entry() -> dict:
    return {
        "description": "- Águas minerais e águas gaseificadas",
        "heading_description": "Águas, incluindo as águas minerais, naturais ou artificiais",
        "subheading_description": "",
        "ipi_rate": "2.6",
        "ex_tipi": [
            {"ex": "1", "description": "Recipientes < 10 litros", "ipi_rate": "NT"},
            {"ex": "2", "description": "Recipientes >= 10 litros", "ipi_rate": "NT"},
        ],
    }


@pytest.fixture
def entry_no_ex() -> dict:
    return {
        "description": "Cervejas de malte.",
        "heading_description": "",
        "subheading_description": "",
        "ipi_rate": "3.9",
        "ex_tipi": None,
    }


@pytest.fixture
def enriched_entry() -> dict:
    # mirrors 2204.21.00 in the enriched JSON schema
    return {
        "description": "-- Em recipientes de capacidade não superior a 2 l",
        "heading_description": "Vinhos de uvas frescas, incluindo os vinhos enriquecidos com álcool",
        "subheading_description": "Outros vinhos; mostos de uvas",
        "ipi_rate": "6.5",
        "ex_tipi": None,
    }


def test_document_includes_specific_description(full_entry: dict) -> None:
    assert "Águas minerais e águas gaseificadas" in build_document_text(
        full_entry, enrich=True
    )


def test_document_includes_all_ex_tipi_descriptions(full_entry: dict) -> None:
    text = build_document_text(full_entry, enrich=True)
    assert "Recipientes < 10 litros" in text
    assert "Recipientes >= 10 litros" in text


def test_document_labels_ex_tipi_with_ex_number(full_entry: dict) -> None:
    text = build_document_text(full_entry, enrich=True)
    assert "EX 1:" in text
    assert "EX 2:" in text


def test_document_without_ex_tipi_has_no_ex_label(entry_no_ex: dict) -> None:
    assert "EX" not in build_document_text(entry_no_ex, enrich=True)


def test_enrich_true_composes_hierarchy(enriched_entry: dict) -> None:
    assert build_document_text(enriched_entry, enrich=True) == (
        "Vinhos de uvas frescas, incluindo os vinhos enriquecidos com álcool. "
        "Outros vinhos; mostos de uvas. "
        "Em recipientes de capacidade não superior a 2 l"
    )


def test_enrich_false_uses_only_description(enriched_entry: dict) -> None:
    # ADR-0004 baseline byte-for-byte: raw description, no parent context,
    # no cleaning of the "-- " level marker.
    assert build_document_text(enriched_entry, enrich=False) == (
        "-- Em recipientes de capacidade não superior a 2 l"
    )


def test_skips_empty_heading_and_subheading(entry_no_ex: dict) -> None:
    assert build_document_text(entry_no_ex, enrich=True) == "Cervejas de malte"


def test_cleans_description_marker(enriched_entry: dict) -> None:
    assert "--" not in build_document_text(enriched_entry, enrich=True)


def test_no_double_separator_when_field_empty(full_entry: dict) -> None:
    # full_entry has an empty subheading_description between two present fields
    assert ". ." not in build_document_text(full_entry, enrich=True)


def test_enrich_false_preserves_ex_tipi_suffix(full_entry: dict) -> None:
    text = build_document_text(full_entry, enrich=False)
    assert text.startswith("- Águas minerais")
    assert "EX 1: Recipientes < 10 litros" in text


def test_anchor_terms_present_in_document() -> None:
    path = _find_latest_tipi_json(Path("data/tipi"), "22")
    entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
    by_ncm = {e["ncm"]: e for e in entries}
    anchors = {"2204.21.00": "vinhos", "2205.10.00": "vermutes", "2208.30.20": "uísques"}
    for ncm, term in anchors.items():
        assert term in build_document_text(by_ncm[ncm], enrich=True).lower(), ncm


# ---------------------------------------------------------------------------
# _find_latest_tipi_json (no schema changes)
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


# ---------------------------------------------------------------------------
# index_entries — against an in-memory ChromaDB collection
# ---------------------------------------------------------------------------


class SpyEncoder:
    """Returns dummy vectors of the expected dimension; loads no model."""

    def encode(self, sentences: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIM for _ in sentences]


@pytest.fixture
def real_entries() -> list[dict]:
    path = _find_latest_tipi_json(Path("data/tipi"), "22")
    return json.loads(path.read_text(encoding="utf-8"))["entries"]


@pytest.fixture
def memory_collection() -> Collection:
    client = chromadb.EphemeralClient()
    return client.create_collection(
        name=f"test_tipi_{uuid4().hex}", metadata={"hnsw:space": "cosine"}
    )


def test_rebuild_index_creates_collection_with_all_entries(
    real_entries: list[dict], memory_collection: Collection
) -> None:
    embedding_fn = E5EmbeddingFunction(encoder=SpyEncoder())
    count = index_entries(memory_collection, real_entries, embedding_fn, enrich=False)
    assert count == len(real_entries) == memory_collection.count()


def test_rebuild_index_is_idempotent(
    real_entries: list[dict], memory_collection: Collection
) -> None:
    embedding_fn = E5EmbeddingFunction(encoder=SpyEncoder())
    index_entries(memory_collection, real_entries, embedding_fn, enrich=False)
    index_entries(memory_collection, real_entries, embedding_fn, enrich=False)
    assert memory_collection.count() == len(real_entries)


# ---------------------------------------------------------------------------
# enrich flag <-> index agreement (ADR-0005)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("enrich", [True, False])
def test_index_records_enrich_metadata(
    real_entries: list[dict], memory_collection: Collection, enrich: bool
) -> None:
    embedding_fn = E5EmbeddingFunction(encoder=SpyEncoder())
    index_entries(memory_collection, real_entries, embedding_fn, enrich=enrich)
    assert memory_collection.metadata["enrich_documents"] is enrich
