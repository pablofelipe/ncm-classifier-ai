import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from src.config import settings
from src.core.use_cases.classify_product import ClassifyProduct
from src.llm.passthrough_adapter import PassthroughRerankAdapter
from src.retrieval.naive_adapter import NaiveRetrievalAdapter


@lru_cache
def get_tipi_entries() -> list[dict[str, object]]:
    """Load the latest TIPI JSON for the configured chapter (cached)."""
    data_dir = Path(settings.tipi_data_dir)
    files = sorted(
        data_dir.glob(f"tipi_{settings.ncm_chapter}_*.json"), reverse=True
    )
    if not files:
        raise FileNotFoundError(
            f"No tipi_{settings.ncm_chapter}_*.json found in {data_dir}. "
            "Run: python scripts/ingest_tipi.py"
        )
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    entries: list[dict[str, object]] = payload["entries"]
    return entries


def build_classify_use_case(entries: list[dict[str, object]]) -> ClassifyProduct:
    """Pure composition root: wire the walking-skeleton adapters into the use case.

    No FastAPI. Consumed both by the HTTP dependency below and by
    eval/run_eval.py (measurement layer), which calls the use case directly.

    Substitute NaiveRetrievalAdapter/PassthroughRerankAdapter for the real
    Chroma/Gemini adapters when ADR-0003 (embedding model selection) lands.
    """
    return ClassifyProduct(
        NaiveRetrievalAdapter(entries),
        PassthroughRerankAdapter(),
        confidence_threshold=settings.confidence_threshold,
    )


def get_classify_use_case(
    entries: Annotated[list[dict[str, object]], Depends(get_tipi_entries)],
) -> ClassifyProduct:
    """FastAPI driving-adapter wrapper: resolve entries via Depends, then
    delegate wiring to build_classify_use_case."""
    return build_classify_use_case(entries)
