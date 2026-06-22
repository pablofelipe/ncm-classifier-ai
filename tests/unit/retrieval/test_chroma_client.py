import json
from pathlib import Path
from uuid import uuid4

import chromadb
import pytest
from chromadb import Collection

from src.core.domain.enrichment import EnrichStrategy
from src.retrieval.chroma_client import (
    _find_latest_tipi_json,
    _synonyms_for_chapter,
    build_document_text,
    index_entries,
    load_synonyms,
    reset_collection,
)
from src.retrieval.embedding import (
    BGE_EMBEDDING_DIM,
    EMBEDDING_DIM,
    BGEEmbeddingFunction,
    E5EmbeddingFunction,
    EmbedderModel,
)

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
        full_entry, EnrichStrategy.FULL
    )


def test_document_includes_all_ex_tipi_descriptions(full_entry: dict) -> None:
    text = build_document_text(full_entry, EnrichStrategy.FULL)
    assert "Recipientes < 10 litros" in text
    assert "Recipientes >= 10 litros" in text


def test_document_labels_ex_tipi_with_ex_number(full_entry: dict) -> None:
    text = build_document_text(full_entry, EnrichStrategy.FULL)
    assert "EX 1:" in text
    assert "EX 2:" in text


def test_document_without_ex_tipi_has_no_ex_label(entry_no_ex: dict) -> None:
    assert "EX" not in build_document_text(entry_no_ex, EnrichStrategy.FULL)


def test_full_composes_hierarchy(enriched_entry: dict) -> None:
    assert build_document_text(enriched_entry, EnrichStrategy.FULL) == (
        "Vinhos de uvas frescas, incluindo os vinhos enriquecidos com álcool. "
        "Outros vinhos; mostos de uvas. "
        "Em recipientes de capacidade não superior a 2 l"
    )


def test_off_uses_only_description(enriched_entry: dict) -> None:
    # ADR-0004 baseline byte-for-byte: raw description, no parent context,
    # no cleaning of the "-- " level marker.
    assert build_document_text(enriched_entry, EnrichStrategy.OFF) == (
        "-- Em recipientes de capacidade não superior a 2 l"
    )


def test_skips_empty_heading_and_subheading(entry_no_ex: dict) -> None:
    assert build_document_text(entry_no_ex, EnrichStrategy.FULL) == "Cervejas de malte"


def test_cleans_description_marker(enriched_entry: dict) -> None:
    assert "--" not in build_document_text(enriched_entry, EnrichStrategy.FULL)


def test_no_double_separator_when_field_empty(full_entry: dict) -> None:
    # full_entry has an empty subheading_description between two present fields
    assert ". ." not in build_document_text(full_entry, EnrichStrategy.FULL)


def test_off_preserves_ex_tipi_suffix(full_entry: dict) -> None:
    text = build_document_text(full_entry, EnrichStrategy.OFF)
    assert text.startswith("- Águas minerais")
    assert "EX 1: Recipientes < 10 litros" in text


def test_anchor_terms_present_in_document() -> None:
    by_ncm = _entries_by_ncm()
    anchors = {"2204.21.00": "vinhos", "2205.10.00": "vermutes", "2208.30.20": "uísques"}
    for ncm, term in anchors.items():
        assert term in build_document_text(by_ncm[ncm], EnrichStrategy.FULL).lower(), ncm


# ---------------------------------------------------------------------------
# SUBHEADING_ONLY (ADR-0006, Form B): inject the 6-digit subheading when
# substantive; never the 4-digit heading; no fallback to heading.
# ---------------------------------------------------------------------------


def _entries_by_ncm() -> dict[str, dict]:
    path = _find_latest_tipi_json(Path("data/tipi"), "22")
    return {e["ncm"]: e for e in json.loads(path.read_text(encoding="utf-8"))["entries"]}


def test_subheading_only_injects_substantive_subheading() -> None:
    # 2208.30.20: the product name "Uísques" lives at the 6-digit subheading,
    # absent from the leaf ("Em embalagens..."). B must inject it.
    entry = _entries_by_ncm()["2208.30.20"]
    assert "Uísques" in build_document_text(entry, EnrichStrategy.SUBHEADING_ONLY)


def test_subheading_only_never_injects_heading() -> None:
    # 2205.10.00: heading "Vermutes..." must NOT appear — B never injects the
    # 4-digit family. The accepted ADR-0006 cost (cases 018/019/020/022).
    entry = _entries_by_ncm()["2205.10.00"]
    text = build_document_text(entry, EnrichStrategy.SUBHEADING_ONLY)
    assert "vermute" not in text.lower()


def test_subheading_only_drops_heading_even_when_present() -> None:
    # 2208.30.20 has a non-empty heading_description; B drops it entirely.
    entry = _entries_by_ncm()["2208.30.20"]
    assert "Álcool etílico" not in build_document_text(entry, EnrichStrategy.SUBHEADING_ONLY)


def test_subheading_only_leaf_only_when_subheading_empty() -> None:
    # 2205.10.00: empty subheading_description -> cleaned leaf only, no fallback.
    entry = _entries_by_ncm()["2205.10.00"]
    assert build_document_text(entry, EnrichStrategy.SUBHEADING_ONLY) == (
        "Em recipientes de capacidade não superior a 2 l"
    )


def test_subheading_only_skips_non_substantive_subheading() -> None:
    # Non-empty but filler subheading ("Outras") is dropped; heading never enters.
    entry = {
        "description": "-- Outras",
        "heading_description": "Família ampla compartilhada",
        "subheading_description": "Outras",
        "ipi_rate": "0",
        "ex_tipi": None,
    }
    assert build_document_text(entry, EnrichStrategy.SUBHEADING_ONLY) == "Outras"


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
    count = index_entries(
        memory_collection, real_entries, embedding_fn, EnrichStrategy.OFF, EmbedderModel.E5_SMALL
    )
    assert count == len(real_entries) == memory_collection.count()


def test_rebuild_index_is_idempotent(
    real_entries: list[dict], memory_collection: Collection
) -> None:
    embedding_fn = E5EmbeddingFunction(encoder=SpyEncoder())
    index_entries(
        memory_collection, real_entries, embedding_fn, EnrichStrategy.OFF, EmbedderModel.E5_SMALL
    )
    index_entries(
        memory_collection, real_entries, embedding_fn, EnrichStrategy.OFF, EmbedderModel.E5_SMALL
    )
    assert memory_collection.count() == len(real_entries)


# ---------------------------------------------------------------------------
# enrich strategy <-> index agreement (ADR-0005/0006)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "strategy", [EnrichStrategy.OFF, EnrichStrategy.FULL, EnrichStrategy.SUBHEADING_ONLY]
)
def test_index_records_enrich_metadata(
    real_entries: list[dict], memory_collection: Collection, strategy: EnrichStrategy
) -> None:
    embedding_fn = E5EmbeddingFunction(encoder=SpyEncoder())
    index_entries(memory_collection, real_entries, embedding_fn, strategy, EmbedderModel.E5_SMALL)
    assert memory_collection.metadata["enrich_strategy"] == strategy.value


def test_index_records_embedder_metadata(
    real_entries: list[dict], memory_collection: Collection
) -> None:
    # ADR-0008 guard: the embedder is stored alongside enrich_strategy in the
    # same metadata write, so the adapter can detect an index<->embedder mismatch.
    index_entries(
        memory_collection,
        real_entries,
        BGEEmbeddingFunction(encoder=BgeSpyEncoder()),
        EnrichStrategy.OFF,
        EmbedderModel.BGE_M3,
    )
    assert memory_collection.metadata["embedder"] == EmbedderModel.BGE_M3.value


# ---------------------------------------------------------------------------
# reset_collection — drop+recreate for the e5 384 -> bge-m3 1024 dim change
# (ADR-0008). get_or_create would return the stale 384-dim collection and an
# upsert of 1024-dim vectors would raise InvalidDimensionException, so rebuild
# must drop and recreate.
# ---------------------------------------------------------------------------


class BgeSpyEncoder:
    """Returns dummy vectors of the bge-m3 dimension; loads no model."""

    def encode(self, sentences: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
        return [[0.1] * BGE_EMBEDDING_DIM for _ in sentences]


def test_reset_collection_allows_new_dimension_after_drop() -> None:
    client = chromadb.EphemeralClient()
    name = f"test_tipi_{uuid4().hex}"
    old = client.create_collection(name=name, metadata={"hnsw:space": "cosine"})
    old.add(ids=["e5"], embeddings=[[0.1] * EMBEDDING_DIM], documents=["old 384-dim doc"])

    fresh = reset_collection(client, name)
    # The 1024-dim upsert must neither raise (silent dimension clash) nor mix
    # with the dropped 384-dim entry.
    fresh.add(ids=["bge"], embeddings=[[0.2] * BGE_EMBEDDING_DIM], documents=["new 1024-dim doc"])

    assert fresh.count() == 1
    assert fresh.get(ids=["e5"])["ids"] == []


def test_reset_collection_drops_stale_enrich_strategy() -> None:
    client = chromadb.EphemeralClient()
    name = f"test_tipi_{uuid4().hex}"
    client.create_collection(name=name, metadata={"hnsw:space": "cosine", "enrich_strategy": "off"})

    fresh = reset_collection(client, name)

    assert "enrich_strategy" not in (fresh.metadata or {})


def test_rebuild_rewrites_enrich_metadata_after_drop(real_entries: list[dict]) -> None:
    # CRITICAL: after drop+recreate the collection has no enrich_strategy, so
    # index_entries must re-write it — otherwise the adapter guard raises a
    # mismatch RuntimeError on the next startup.
    client = chromadb.EphemeralClient()
    name = f"test_tipi_{uuid4().hex}"
    client.create_collection(name=name, metadata={"hnsw:space": "cosine"})

    fresh = reset_collection(client, name)
    index_entries(
        fresh,
        real_entries,
        BGEEmbeddingFunction(encoder=BgeSpyEncoder()),
        EnrichStrategy.OFF,
        EmbedderModel.BGE_M3,
    )

    assert fresh.metadata["enrich_strategy"] == EnrichStrategy.OFF.value


# ---------------------------------------------------------------------------
# corpus enrichment — synonyms (ADR-0010)
#
# Brands and colloquial names absent from the official nomenclature are appended
# to the OFF baseline document. This enriches the *corpus*, not the document-text
# strategy: injection composes with OFF only (no new EnrichStrategy variant), and
# the synonym source is injected (a mapping / a file path) so tests never touch
# the real beverage_synonyms.json.
# ---------------------------------------------------------------------------


@pytest.fixture
def synonyms() -> dict[str, list[str]]:
    return {"2208.60.00": ["vodca", "Smirnoff", "Absolut"]}


@pytest.fixture
def vodka_entry() -> dict:
    # mirrors 2208.60.00 (- Vodca) in the enriched JSON schema, with the ncm key
    # that build_document_text needs to look a synonym list up.
    return {
        "ncm": "2208.60.00",
        "description": "- Vodca",
        "heading_description": "Álcool etílico; aguardentes, licores e outras bebidas espirituosas",
        "subheading_description": "",
        "ipi_rate": "19.5",
        "ex_tipi": None,
    }


def test_off_appends_synonyms_for_known_ncm(vodka_entry: dict, synonyms: dict) -> None:
    # OFF text, then " | " and the comma-separated synonyms for that NCM.
    assert build_document_text(vodka_entry, EnrichStrategy.OFF, synonyms) == (
        "- Vodca | vodca, Smirnoff, Absolut"
    )


def test_off_leaves_text_unchanged_for_unknown_ncm(synonyms: dict) -> None:
    # 2201.10.00 is not in the synonyms mapping -> the OFF text is untouched.
    entry = {"ncm": "2201.10.00", "description": "- Águas minerais", "ex_tipi": None}
    assert build_document_text(entry, EnrichStrategy.OFF, synonyms) == "- Águas minerais"


def test_off_unchanged_when_synonyms_empty(vodka_entry: dict) -> None:
    # Graceful: an empty mapping (the file-absent case) leaves OFF byte-for-byte.
    assert build_document_text(vodka_entry, EnrichStrategy.OFF, {}) == build_document_text(
        vodka_entry, EnrichStrategy.OFF
    )


def test_synonyms_not_injected_for_non_off_strategy(vodka_entry: dict, synonyms: dict) -> None:
    # Corpus enrichment rides on the OFF baseline only; never on FULL/SUBHEADING.
    assert "Smirnoff" not in build_document_text(vodka_entry, EnrichStrategy.FULL, synonyms)


def test_load_synonyms_returns_empty_when_file_absent(tmp_path: Path) -> None:
    # File-absent -> empty mapping, so rebuild proceeds (graceful, no synonyms).
    assert load_synonyms(tmp_path / "missing.json") == {}


def test_load_synonyms_reads_mapping_from_file(tmp_path: Path) -> None:
    path = tmp_path / "syn.json"
    path.write_text(json.dumps({"2208.60.00": ["vodca", "Smirnoff"]}), encoding="utf-8")
    assert load_synonyms(path) == {"2208.60.00": ["vodca", "Smirnoff"]}


def test_index_entries_threads_synonyms_into_documents(memory_collection: Collection) -> None:
    entries = [
        {
            "ncm": "2208.60.00",
            "chapter": "22",
            "heading": "22.08",
            "subheading": "2208.60",
            "description": "- Vodca",
            "ipi_rate": "19.5",
            "ex_tipi": None,
        }
    ]
    index_entries(
        memory_collection,
        entries,
        E5EmbeddingFunction(encoder=SpyEncoder()),
        EnrichStrategy.OFF,
        EmbedderModel.E5_SMALL,
        {"2208.60.00": ["Smirnoff"]},
    )
    assert "Smirnoff" in memory_collection.get(ids=["22086000"])["documents"][0]


# ---------------------------------------------------------------------------
# baseline blindagem (ADR-0010): corpus synonyms apply to the beverage (v2)
# corpus only. The v1/cap22 production baseline (frozen at 63.3% top-3) must
# never be enriched, even if the synonyms file exists on disk.
# ---------------------------------------------------------------------------


def test_synonyms_gated_off_for_non_beverage_chapter(tmp_path: Path) -> None:
    # cap22 (production v1): synonyms suppressed even though the file is present.
    path = tmp_path / "syn.json"
    path.write_text(json.dumps({"2208.60.00": ["Smirnoff"]}), encoding="utf-8")
    assert _synonyms_for_chapter("22", path) == {}


def test_synonyms_loaded_for_beverage_chapter(tmp_path: Path) -> None:
    path = tmp_path / "syn.json"
    path.write_text(json.dumps({"2208.60.00": ["Smirnoff"]}), encoding="utf-8")
    assert _synonyms_for_chapter("beverage", path) == {"2208.60.00": ["Smirnoff"]}
