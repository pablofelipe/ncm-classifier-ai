"""Gemini implementation of LLMClient (ADR-0016).

``google-genai`` is an optional dependency (the ``llm`` extra), imported
lazily so this module can be imported without the package installed.
"""

from typing import TYPE_CHECKING

from src.config import settings

if TYPE_CHECKING:
    import google.genai as genai


class ConfigurationError(RuntimeError):
    """Raised when a required setting is missing at the point it is needed."""


def _build_client(api_key: str) -> "genai.Client":
    import google.genai as genai

    return genai.Client(api_key=api_key)


class GeminiClient:
    """LLMClient implementation backed by the google-genai SDK.

    ``api_key`` (when given) is used to build a dedicated client, ignoring
    ``settings.gemini_api_key`` entirely — this is the per-request "bring
    your own credentials" path (ADR-0016). ``client`` is an injection seam
    for tests. With neither, falls back to the maintainer's own
    ``settings.gemini_api_key`` (local dev / CI / server-side default rerank).
    """

    def __init__(self, api_key: str | None = None, client: "genai.Client | None" = None) -> None:
        self._api_key = api_key
        self._override = client
        self._cached: genai.Client | None = None

    def _get_client(self) -> "genai.Client":
        if self._override is not None:
            return self._override
        if self._cached is None:
            api_key = self._api_key or settings.gemini_api_key
            if not api_key:
                raise ConfigurationError(
                    "No Gemini API key available: pass api_key= (per-request "
                    "credential) or set GEMINI_API_KEY (maintainer's own key)."
                )
            self._cached = _build_client(api_key)
        return self._cached

    def generate(
        self,
        *,
        model: str,
        system_instruction: str,
        prompt: str,
        response_format: str = "application/json",
    ) -> str:
        client = self._get_client()
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "system_instruction": system_instruction,
                "response_mime_type": response_format,
            },
        )
        return (response.text or "").strip()
