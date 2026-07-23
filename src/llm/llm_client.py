"""LLM provider factory (ADR-0016).

The LLMClient Protocol itself lives in src/core/ports.py -- it's a port, not
an adapter-internal detail (see the hexagonal-boundaries review, 2026-07).
This module only holds the infrastructure-side concern: picking a concrete
LLMClient implementation by provider name.
"""

from collections.abc import Callable

from src.core.ports import LLMClient
from src.llm.gemini_client import GeminiClient

# Provider name (settings.llm_provider / the LLM-Provider header) -> a
# constructor accepting an optional api_key and returning an LLMClient.
# Adding a real second provider is one dict entry here — no change to
# resolve_llm_client's body, dependencies.py, or core/.
_PROVIDERS: dict[str, Callable[[str | None], LLMClient]] = {"google": GeminiClient}


def resolve_llm_client(provider: str, api_key: str | None = None) -> LLMClient:
    try:
        factory = _PROVIDERS[provider]
    except KeyError:
        raise ValueError(f"unknown LLM provider: {provider!r}") from None
    return factory(api_key)
