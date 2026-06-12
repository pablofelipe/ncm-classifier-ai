from typing import Any

import google.genai as genai

from src.config import settings


def _client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def rank_candidates(
    product_name: str,
    description: str,
    candidates: list[dict[str, Any]],
    *,
    use_pro: bool = False,
) -> list[dict[str, Any]]:
    """Re-rank NCM candidates and generate rationale via Gemini."""
    raise NotImplementedError("LLM ranking not yet implemented")
