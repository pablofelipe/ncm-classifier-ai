"""Provider-agnostic LLM generation contract (ADR-0016).

Represents the capability "ask an LLM to generate text", not any specific
vendor SDK shape. Adapters like ``GenericLLMRerankAdapter`` depend on this
Protocol; concrete implementations (``GeminiClient`` today, others later)
translate ``generate()`` into their own SDK's call shape.
"""

from collections.abc import Callable
from typing import Protocol

from src.llm.gemini_client import GeminiClient


class LLMClient(Protocol):
    def generate(
        self,
        *,
        model: str,
        system_instruction: str,
        prompt: str,
        response_format: str = "application/json",
    ) -> str: ...


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
