import pytest
from google.genai import errors as genai_errors

from src.llm.gemini_client import ConfigurationError, GeminiClient, LLMProviderError

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeModels:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []

    def generate_content(self, **kwargs) -> "_FakeResponse":
        self.calls.append(kwargs)
        return _FakeResponse(self._text)


class _FakeGeminiSdkClient:
    """Synchronous test double: returns a preset text from generate_content."""

    def __init__(self, text: str) -> None:
        self.models = _FakeModels(text)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModelsRaising:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate_content(self, **kwargs: object) -> "_FakeResponse":
        raise self._exc


class _FakeGeminiSdkClientRaising:
    """Test double whose generate_content raises a real google.genai error."""

    def __init__(self, exc: Exception) -> None:
        self.models = _FakeModelsRaising(exc)


# ---------------------------------------------------------------------------
# generate() — happy path
# ---------------------------------------------------------------------------


def test_generate_returns_stripped_text_from_injected_client() -> None:
    client = GeminiClient(client=_FakeGeminiSdkClient('  {"ranked": []}  \n'))
    result = client.generate(model="gemini-2.5-flash", system_instruction="sys", prompt="hello")
    assert result == '{"ranked": []}'


def test_generate_forwards_model_system_instruction_and_response_format() -> None:
    fake_sdk = _FakeGeminiSdkClient("ok")
    client = GeminiClient(client=fake_sdk)
    client.generate(
        model="gemini-2.5-pro",
        system_instruction="você é um classificador",
        prompt="produto: agua mineral",
        response_format="application/json",
    )
    call = fake_sdk.models.calls[0]
    assert call["model"] == "gemini-2.5-pro"
    assert call["contents"] == "produto: agua mineral"
    assert call["config"]["system_instruction"] == "você é um classificador"
    assert call["config"]["response_mime_type"] == "application/json"


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------


def test_injected_api_key_builds_own_client_ignoring_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.llm.gemini_client as mod

    monkeypatch.setattr(mod.settings, "gemini_api_key", "settings-key")

    built_with: list[str] = []

    def _fake_build_client(api_key: str) -> _FakeGeminiSdkClient:
        built_with.append(api_key)
        return _FakeGeminiSdkClient("ok")

    monkeypatch.setattr(mod, "_build_client", _fake_build_client)

    client = GeminiClient(api_key="request-key")
    client.generate(model="gemini-2.5-flash", system_instruction="sys", prompt="p")

    assert built_with == ["request-key"]


def test_missing_client_and_api_key_and_settings_key_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.llm.gemini_client as mod

    monkeypatch.setattr(mod.settings, "gemini_api_key", None)
    client = GeminiClient()
    with pytest.raises(ConfigurationError):
        client.generate(model="gemini-2.5-flash", system_instruction="sys", prompt="p")


# ---------------------------------------------------------------------------
# Provider error hardening (Etapa 7): a rejected/failed call to the real
# provider must surface as a clean LLMProviderError, not an unhandled
# exception with a full stack trace (ADR-0016 Consequences — known gap this
# closes). Built with real google.genai.errors classes, not a bespoke fake,
# so the isinstance checks in GeminiClient.generate() are exercised for real.
# ---------------------------------------------------------------------------


def test_generate_raises_llm_provider_error_for_client_error() -> None:
    exc = genai_errors.ClientError(
        code=400, response_json={"error": {"message": "API key not valid"}}
    )
    client = GeminiClient(client=_FakeGeminiSdkClientRaising(exc))
    with pytest.raises(LLMProviderError) as exc_info:
        client.generate(model="gemini-2.5-flash", system_instruction="sys", prompt="p")
    assert exc_info.value.status_code == 422


def test_generate_raises_llm_provider_error_for_server_error() -> None:
    exc = genai_errors.ServerError(code=503, response_json={"error": {"message": "UNAVAILABLE"}})
    client = GeminiClient(client=_FakeGeminiSdkClientRaising(exc))
    with pytest.raises(LLMProviderError) as exc_info:
        client.generate(model="gemini-2.5-flash", system_instruction="sys", prompt="p")
    assert exc_info.value.status_code == 502


def test_build_client_sets_a_bounded_request_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.llm.gemini_client import _REQUEST_TIMEOUT_MS, _build_client

    captured: dict[str, object] = {}

    class _FakeClientCtor:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("google.genai.Client", _FakeClientCtor)
    _build_client("some-key")
    assert captured["http_options"].timeout == _REQUEST_TIMEOUT_MS


def test_llm_provider_error_message_never_includes_raw_provider_response() -> None:
    exc = genai_errors.ClientError(
        code=400, response_json={"error": {"message": "some-internal-provider-detail"}}
    )
    client = GeminiClient(client=_FakeGeminiSdkClientRaising(exc))
    with pytest.raises(LLMProviderError) as exc_info:
        client.generate(model="gemini-2.5-flash", system_instruction="sys", prompt="p")
    assert "some-internal-provider-detail" not in exc_info.value.message
