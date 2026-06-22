import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb import Collection

from src.config import settings
from src.core.domain.enrichment import EnrichStrategy
from src.core.domain.tipi_parsing import clean_level_text, is_substantive
from src.retrieval.embedding import EmbedderModel, EmbeddingFunction, make_embedding_function


def build_document_text(
    entry: dict[str, Any],
    strategy: EnrichStrategy,
    synonyms: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """Build the text to embed for a TIPI entry.

    ``strategy`` is explicit (no default) so every call site chooses
    consciously. OFF uses the raw description verbatim — the ADR-0004 baseline,
    byte-for-byte. Any enrich mode cleans the leaf description (drops the "-- "
    level marker) and prepends parent context, general → specific, empty levels
    skipped:

    - FULL (ADR-0005): heading + subheading + leaf.
    - SUBHEADING_ONLY (ADR-0006, Form B): subheading + leaf, and only when the
      subheading is substantive; the heading is never injected.

    ``synonyms`` is corpus enrichment (ADR-0010): a NCM → terms mapping of brands
    and colloquial names absent from the official nomenclature. When the entry's
    NCM has terms, they are appended ``"{text} | term, term"``. This enriches the
    *corpus*, not the document-text strategy, so it composes with the OFF baseline
    only — never with FULL/SUBHEADING_ONLY (which are closed experiments). An
    absent/empty mapping leaves the text unchanged (graceful when no file exists).

    Prefixing (if any) is the embedder's concern, not this function's: the
    shipping e5-small embedder adds "passage: " to documents (ADR-0004); the
    opt-in bge-m3 adds none (ADR-0008, rejected and not in the production path).
    """
    if strategy is EnrichStrategy.OFF:
        body = entry["description"]
    else:
        leaf = clean_level_text(entry["description"])
        if strategy is EnrichStrategy.FULL:
            levels = [
                entry.get("heading_description", ""),
                entry.get("subheading_description", ""),
                leaf,
            ]
        else:  # SUBHEADING_ONLY (Form B): inject the substantive subheading
            # (the 6-digit product level); the 4-digit heading is never added.
            subheading = entry.get("subheading_description", "")
            levels = [subheading if is_substantive(subheading) else "", leaf]
        body = ". ".join(level for level in levels if level)
    parts = [body]
    for ex in entry.get("ex_tipi") or []:
        parts.append(f"EX {ex['ex']}: {ex['description']}")
    text = " | ".join(parts)
    if strategy is EnrichStrategy.OFF and synonyms:
        terms = synonyms.get(entry.get("ncm", ""))
        if terms:
            text = f"{text} | {', '.join(terms)}"
    return text


def load_synonyms(path: Path) -> dict[str, list[str]]:
    """Load the NCM → synonyms mapping for corpus enrichment (ADR-0010).

    Returns an empty mapping when the file is absent so indexing proceeds
    gracefully on a corpus without a synonyms file. The path is configurable
    (``Settings.synonyms_path``) and the loaded mapping is injected into
    ``index_entries``/``build_document_text``, so tests use a fixture instead.
    """
    if not path.exists():
        return {}
    return cast(dict[str, list[str]], json.loads(path.read_text(encoding="utf-8")))


def _synonyms_for_chapter(chapter: str, path: Path) -> dict[str, list[str]]:
    """Return corpus-enrichment synonyms for ``chapter``, gated to beverage (v2).

    Corpus enrichment (ADR-0010) is a v2 experiment over the beverage corpus.
    The v1/cap22 production baseline is frozen at 63.3% top-3 (ADR-0004), so it
    must never be enriched — even with the synonyms file present on disk. Any
    chapter other than ``beverage`` gets an empty mapping (no enrichment).
    """
    if chapter != "beverage":
        return {}
    return load_synonyms(path)


def _find_latest_tipi_json(data_dir: Path, chapter: str) -> Path:
    """Return the most recent tipi_<chapter>_*.json in data_dir."""
    files = sorted(data_dir.glob(f"tipi_{chapter}_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(
            f"No tipi_{chapter}_*.json found in {data_dir}. Run: python scripts/ingest_tipi.py"
        )
    return files[0]


def _collection_name() -> str:
    return f"tipi_cap{settings.ncm_chapter}"


def get_collection() -> Collection:
    client = chromadb.PersistentClient(path=settings.chroma_path)
    return client.get_or_create_collection(
        name=_collection_name(),
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection(client: chromadb.api.ClientAPI, name: str) -> Collection:
    """Delete the named collection if present, then create it fresh.

    A dimension change (e5 384 -> bge-m3 1024, ADR-0008) makes the persisted
    collection incompatible: ``get_or_create_collection`` would return the stale
    384-dim collection and an upsert of 1024-dim vectors would raise
    ``InvalidDimensionException``. Dropping and recreating is the only safe
    rebuild. The fresh collection carries only ``hnsw:space``; ``index_entries``
    re-writes ``enrich_strategy`` so the adapter guard stays satisfied.
    """
    if name in {c.name for c in client.list_collections()}:
        client.delete_collection(name=name)
    return client.create_collection(name=name, metadata={"hnsw:space": "cosine"})


def index_entries(
    collection: Collection,
    entries: list[dict[str, Any]],
    embedding_fn: EmbeddingFunction,
    strategy: EnrichStrategy,
    embedder: EmbedderModel,
    synonyms: Mapping[str, Sequence[str]] | None = None,
) -> int:
    """Embed and upsert TIPI entries into the collection, returning the count.

    Idempotent: ids are the dotless NCM codes, so re-running replaces rather
    than duplicates. Embeddings are computed via the injected embedding function;
    the default Chroma embedder is never invoked.
    ``strategy`` selects the document-text strategy (see build_document_text)
    and is recorded on the collection so the adapter can detect an
    index<->strategy mismatch. ``synonyms`` is optional corpus enrichment
    (ADR-0010), appended to OFF documents only (see build_document_text).
    """
    ids = [e["ncm"].replace(".", "") for e in entries]
    documents = [build_document_text(e, strategy, synonyms) for e in entries]
    metadatas = [
        {
            "ncm_dotted": e["ncm"],
            "chapter": e["chapter"],
            "heading": e["heading"],
            "subheading": e["subheading"],
            "description": e["description"],
            "ipi_rate": e["ipi_rate"],
        }
        for e in entries
    ]
    embeddings = embedding_fn.embed_documents(documents)

    collection.upsert(
        ids=ids,
        embeddings=cast(Any, embeddings),
        metadatas=cast(Any, metadatas),
        documents=documents,
    )
    # Record provenance so the adapter can detect an index<->config mismatch:
    # the embedder (ADR-0008) and the document-text strategy (ADR-0005/0006),
    # both in a single write. Chroma rejects re-stating the immutable
    # "hnsw:space" key in modify(), so this overwrites the metadata dict with
    # these two keys alone; the cosine distance function is unaffected.
    collection.modify(metadata={"enrich_strategy": strategy.value, "embedder": embedder.value})
    return len(ids)


def rebuild_index() -> None:
    """Rebuild ChromaDB collection from the latest tipi_<chapter>_*.json.

    Drops and recreates the collection (ADR-0008): switching embedder can change
    the vector dimension (e5 384 -> bge-m3 1024), so reusing the persisted
    collection would fail. The drop is unconditional — a rebuild always starts
    from a clean, correctly-dimensioned collection. The embedder is selected from
    settings (default e5, the production baseline; bge-m3 opt-in via EMBEDDER).
    """
    data_dir = Path(settings.tipi_data_dir)
    json_path = _find_latest_tipi_json(data_dir, settings.ncm_chapter)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = payload["entries"]

    client = chromadb.PersistentClient(path=settings.chroma_path)
    col = reset_collection(client, _collection_name())
    embedding_fn = make_embedding_function(settings.embedder)
    synonyms = _synonyms_for_chapter(settings.ncm_chapter, Path(settings.synonyms_path))
    count = index_entries(
        col, entries, embedding_fn, settings.enrich_strategy, settings.embedder, synonyms
    )

    source = payload.get("source", json_path.name)
    print(f"Indexed {count} entries from {source} into '{col.name}'")


def snapshot() -> None:
    """Version current embeddings for eval reproducibility.

    Not implemented and not exposed as a CLI command (no `make snapshot`); kept
    as a placeholder for the planned reproducibility-snapshot work.
    """
    raise NotImplementedError


if __name__ == "__main__":
    commands: dict[str, object] = {"rebuild": rebuild_index}
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in commands:
        print(f"Usage: python -m src.retrieval.chroma_client [{' | '.join(commands)}]")
        sys.exit(1)
    commands[cmd]()  # type: ignore[operator]
