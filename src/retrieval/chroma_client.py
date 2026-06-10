import json
import sys
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb import Collection

from src.config import settings
from src.retrieval.embedding import E5EmbeddingFunction


def build_document_text(entry: dict[str, Any]) -> str:
    """Build the text to embed for a TIPI entry."""
    parts = [entry["description"]]
    for ex in entry.get("ex_tipi") or []:
        parts.append(f"EX {ex['ex']}: {ex['description']}")
    return " | ".join(parts)


def _find_latest_tipi_json(data_dir: Path, chapter: str) -> Path:
    """Return the most recent tipi_<chapter>_*.json in data_dir."""
    files = sorted(data_dir.glob(f"tipi_{chapter}_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(
            f"No tipi_{chapter}_*.json found in {data_dir}. "
            "Run: python scripts/ingest_tipi.py"
        )
    return files[0]


def get_collection() -> Collection:
    client = chromadb.PersistentClient(path=settings.chroma_path)
    return client.get_or_create_collection(
        name=f"tipi_cap{settings.ncm_chapter}",
        metadata={"hnsw:space": "cosine"},
    )


def index_entries(
    collection: Collection,
    entries: list[dict[str, Any]],
    embedding_fn: E5EmbeddingFunction,
) -> int:
    """Embed and upsert TIPI entries into the collection, returning the count.

    Idempotent: ids are the dotless NCM codes, so re-running replaces rather
    than duplicates. Embeddings are computed via the injected embedding function
    (passage-prefixed); the default Chroma embedder is never invoked.
    """
    ids = [e["ncm"].replace(".", "") for e in entries]
    documents = [build_document_text(e) for e in entries]
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
    return len(ids)


def rebuild_index() -> None:
    """Rebuild ChromaDB collection from the latest tipi_<chapter>_*.json."""
    data_dir = Path(settings.tipi_data_dir)
    json_path = _find_latest_tipi_json(data_dir, settings.ncm_chapter)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = payload["entries"]

    col = get_collection()
    count = index_entries(col, entries, E5EmbeddingFunction())

    source = payload.get("source", json_path.name)
    print(f"Indexed {count} entries from {source} into '{col.name}'")


def snapshot() -> None:
    """Version current embeddings for eval reproducibility."""
    raise NotImplementedError


if __name__ == "__main__":
    commands: dict[str, object] = {"rebuild": rebuild_index, "snapshot": snapshot}
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in commands:
        print(f"Usage: python -m src.retrieval.chroma_client [{' | '.join(commands)}]")
        sys.exit(1)
    commands[cmd]()  # type: ignore[operator]
