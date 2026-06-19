"""Gemini LLM client — STUB.

Not yet wired into the pipeline: the system ships with Passthrough rerank, so
no Gemini call is made and no API key is required. ``google-genai`` is an
optional dependency (the ``llm`` extra), imported lazily here so this module
can be imported without the package installed. The real rerank arrives with the
LLM-rerank ADR.
"""

from typing import TYPE_CHECKING, Any

from src.config import settings

if TYPE_CHECKING:
    import google.genai as genai


class ConfigurationError(RuntimeError):
    """Raised when a required setting is missing at the point it is needed."""


def _client() -> "genai.Client":
    if not settings.gemini_api_key:
        raise ConfigurationError(
            "GEMINI_API_KEY is not set. The Gemini rerank path requires a key; "
            "set it in the environment and install the 'llm' extra."
        )
    import google.genai as genai

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
