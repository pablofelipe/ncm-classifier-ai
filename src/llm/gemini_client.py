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


class LLMProviderError(Exception):
    """Raised when the LLM provider itself rejects or fails a request (Etapa 7).

    Carries a fixed, generic message per error class — never the raw provider
    response body — so nothing the provider returns can leak into an HTTP
    response. `status_code` is what src/main.py's exception handler returns:
    422 for a client-side problem (e.g. an invalid visitor-supplied API key),
    502 for a provider-side outage. Closes the gap flagged in ADR-0016
    Consequences, where this previously surfaced as an unhandled 500 with a
    full stack trace.
    """

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


# Etapa 7 hardening: the SDK sets no timeout of its own, so a stuck upstream
# connection could hold a request (and, given the current sync-in-async route,
# the whole worker) open indefinitely. Bounded, not tuned via env — this is a
# safety net, not a knob callers are expected to need.
_REQUEST_TIMEOUT_MS = 15_000


def _build_client(api_key: str) -> "genai.Client":
    import google.genai as genai
    from google.genai import types

    return genai.Client(
        api_key=api_key, http_options=types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS)
    )


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
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "system_instruction": system_instruction,
                    "response_mime_type": response_format,
                },
            )
        except Exception as exc:
            import google.genai.errors as genai_errors

            # ServerError before ClientError: ServerError subclasses APIError
            # directly, same as ClientError — order matters for isinstance,
            # not inheritance, since neither is a subclass of the other.
            if isinstance(exc, genai_errors.ServerError):
                raise LLMProviderError(
                    502, "LLM provider is currently unavailable — try again shortly."
                ) from exc
            if isinstance(exc, genai_errors.ClientError):
                raise LLMProviderError(
                    422,
                    "LLM provider rejected the request — check the API key, provider, or model.",
                ) from exc
            raise
        return (response.text or "").strip()
