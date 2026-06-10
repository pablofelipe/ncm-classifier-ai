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
    count = index_entries(memory_collection, real_entries, embedding_fn)
    assert count == len(real_entries) == memory_collection.count()


def test_rebuild_index_is_idempotent(
    real_entries: list[dict], memory_collection: Collection
) -> None:
    embedding_fn = E5EmbeddingFunction(encoder=SpyEncoder())
    index_entries(memory_collection, real_entries, embedding_fn)
    index_entries(memory_collection, real_entries, embedding_fn)
    assert memory_collection.count() == len(real_entries)
