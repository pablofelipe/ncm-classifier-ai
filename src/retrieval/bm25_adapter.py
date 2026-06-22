import re
from typing import Any, cast

from chromadb import Collection
from rank_bm25 import BM25Okapi

from src.core.domain.ncm import ClassificationCandidate, ProductQuery

_TOKEN = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric. Keeps accented letters and digits
    (``\\w`` is Unicode-aware), so ``cachaça`` / ``750`` survive intact."""
    return _TOKEN.findall(text.lower())


class BM25RetrievalAdapter:
    """Lexical retrieval (BM25) over the same documents as the dense index.

    Built in memory at construction from the Chroma collection's stored
    ``documents`` — the exact ``build_document_text`` output (with ADR-0010
    synonyms), so the lexical and dense sides see identical text without rereading
    the source JSON. The collection's vectors are ignored; only ``documents`` and
    ``metadatas`` are read. No embedder is involved, so the e5 "query: " prefix is
    never applied — BM25 matches the raw query terms.
    """

    def __init__(self, collection: Collection) -> None:
        got = collection.get(include=cast(Any, ["documents", "metadatas"]))
        documents = got["documents"] or []
        metadatas = got["metadatas"] or []
        self._metadatas: list[dict[str, Any]] = [dict(m) for m in metadatas]
        self._bm25 = BM25Okapi([_tokenize(doc) for doc in documents])

    def retrieve_candidates(self, query: ProductQuery, k: int) -> list[ClassificationCandidate]:
        parts = [query.product_name]
        if query.description:
            parts.append(query.description)
        scores = self._bm25.get_scores(_tokenize(" ".join(parts)))

        order = sorted(range(len(self._metadatas)), key=lambda i: scores[i], reverse=True)
        candidates: list[ClassificationCandidate] = []
        for i in order[:k]:
            meta = self._metadatas[i]
            metadata: dict[str, str | float] = {key: str(value) for key, value in meta.items()}
            candidates.append(
                ClassificationCandidate(
                    ncm_code=str(meta["ncm_dotted"]),
                    description=str(meta["description"]),
                    score=float(scores[i]),
                    metadata=metadata,
                )
            )
        return candidates
