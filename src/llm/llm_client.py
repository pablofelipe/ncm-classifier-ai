"""Provider-agnostic LLM generation contract (ADR-0016).

Represents the capability "ask an LLM to generate text", not any specific
vendor SDK shape. Adapters like ``GenericLLMRerankAdapter`` depend on this
Protocol; concrete implementations (``GeminiClient`` today, others later)
translate ``generate()`` into their own SDK's call shape.
"""

from typing import Protocol


class LLMClient(Protocol):
    def generate(
        self,
        *,
        model: str,
        system_instruction: str,
        prompt: str,
        response_format: str = "application/json",
    ) -> str: ...
