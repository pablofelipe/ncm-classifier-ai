from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_index_info
from src.api.schemas import IndexInfo
from src.config import RerankMode, RetrievalMode, settings
from src.main import app


def _fake_index_info() -> IndexInfo:
    return IndexInfo(
        collection="tipi_capbeverage",
        source="tipi_beverage_20260618.json",
        entries=64,
        embedder="e5_small",
        enrich_strategy="off",
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_index_info] = _fake_index_info
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_version_returns_200(client: TestClient) -> None:
    response = client.get("/version")
    assert response.status_code == 200


def test_version_returns_the_apps_own_version_string(client: TestClient) -> None:
    response = client.get("/version")
    assert response.json()["version"] == app.version


def test_info_returns_200(client: TestClient) -> None:
    response = client.get("/info")
    assert response.status_code == 200


def test_info_returns_version(client: TestClient) -> None:
    response = client.get("/info")
    assert response.json()["version"] == app.version


def test_info_returns_index_metadata_from_dependency(client: TestClient) -> None:
    response = client.get("/info")
    assert response.json()["index"] == {
        "collection": "tipi_capbeverage",
        "source": "tipi_beverage_20260618.json",
        "entries": 64,
        "embedder": "e5_small",
        "enrich_strategy": "off",
    }


def test_info_returns_configured_retrieval_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "retrieval_mode", RetrievalMode.HYBRID)
    response = client.get("/info")
    assert response.json()["retrieval_mode"] == "hybrid"


def test_info_returns_configured_rerank_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rerank_mode", RerankMode.PASSTHROUGH)
    response = client.get("/info")
    assert response.json()["rerank_mode"] == "passthrough"


def test_info_returns_default_llm_provider_and_model_from_settings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_provider", "google")
    monkeypatch.setattr(settings, "llm_model", "gemini-2.5-flash")
    response = client.get("/info")
    assert response.json()["llm"]["default_provider"] == "google"
    assert response.json()["llm"]["default_model"] == "gemini-2.5-flash"


def test_info_reports_byok_supported(client: TestClient) -> None:
    response = client.get("/info")
    assert response.json()["llm"]["byok_supported"] is True


def test_info_reports_byok_header_names(client: TestClient) -> None:
    response = client.get("/info")
    assert response.json()["llm"]["byok_headers"] == [
        "X-LLM-Api-Key",
        "LLM-Provider",
        "LLM-Model",
    ]


def test_info_never_exposes_gemini_api_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "maintainers-own-secret-key")
    response = client.get("/info")
    assert "maintainers-own-secret-key" not in response.text


# ---------------------------------------------------------------------------
# GET / (Release Polish): landing page for a first-time visitor — orients
# without duplicating what GET /info already reports in full.
# ---------------------------------------------------------------------------


def test_root_returns_200(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200


def test_root_returns_project_name(client: TestClient) -> None:
    response = client.get("/")
    assert response.json()["name"] == "NCM Classifier"


def test_root_returns_the_apps_own_version_string(client: TestClient) -> None:
    response = client.get("/")
    assert response.json()["version"] == app.version


def test_root_points_to_swagger_docs(client: TestClient) -> None:
    response = client.get("/")
    assert response.json()["docs"] == "/docs"


def test_root_lists_the_classify_endpoint(client: TestClient) -> None:
    response = client.get("/")
    assert response.json()["endpoints"]["classify"] == "POST /classify"


def test_root_lists_the_health_endpoint(client: TestClient) -> None:
    response = client.get("/")
    assert response.json()["endpoints"]["health"] == "GET /health"


def test_root_lists_the_info_endpoint(client: TestClient) -> None:
    response = client.get("/")
    assert response.json()["endpoints"]["info"] == "GET /info"


def test_root_does_not_duplicate_infos_index_details(client: TestClient) -> None:
    # GET /info is the full diagnostic snapshot (collection, retrieval_mode,
    # rerank_mode, LLM defaults) — the landing page only points to it.
    response = client.get("/")
    assert "index" not in response.json()
    assert "retrieval_mode" not in response.json()
