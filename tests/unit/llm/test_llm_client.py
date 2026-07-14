import pytest

from src.llm.gemini_client import GeminiClient
from src.llm.llm_client import resolve_llm_client


def test_resolve_llm_client_returns_gemini_client_for_google() -> None:
    client = resolve_llm_client("google")
    assert isinstance(client, GeminiClient)


def test_resolve_llm_client_raises_value_error_for_unknown_provider() -> None:
    with pytest.raises(ValueError, match="unknown LLM provider"):
        resolve_llm_client("openai")


def test_resolve_llm_client_passes_api_key_to_the_client() -> None:
    client = resolve_llm_client("google", api_key="visitor-key")
    assert isinstance(client, GeminiClient)
    assert client._api_key == "visitor-key"


def test_resolve_llm_client_without_api_key_builds_a_keyless_client() -> None:
    client = resolve_llm_client("google")
    assert isinstance(client, GeminiClient)
    assert client._api_key is None
