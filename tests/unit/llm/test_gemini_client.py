import pytest

from src.llm.gemini_client import ConfigurationError, GeminiClient

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
