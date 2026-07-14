"""Release Polish: the OpenAPI schema is part of the public contract — a
visitor using only Swagger UI must find descriptions and examples, not bare
field names. These tests guard that contract against regressing back to
undocumented, not just check today's snapshot."""

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def _schema() -> dict:
    return client.get("/openapi.json").json()


def test_app_has_a_top_level_description() -> None:
    assert _schema()["info"]["description"].strip() != ""


def test_root_route_has_a_summary() -> None:
    assert _schema()["paths"]["/"]["get"]["summary"].strip() != ""


def test_classify_route_has_a_description() -> None:
    assert _schema()["paths"]["/classify"]["post"]["description"].strip() != ""


def test_health_version_info_routes_have_descriptions() -> None:
    schema = _schema()
    for path in ["/health", "/version", "/info"]:
        assert schema["paths"][path]["get"]["description"].strip() != ""


def test_classify_route_documents_the_byok_headers() -> None:
    params = _schema()["paths"]["/classify"]["post"]["parameters"]
    by_name = {p["name"]: p for p in params}
    assert by_name["X-LLM-Api-Key"]["description"].strip() != ""
    assert by_name["LLM-Provider"]["description"].strip() != ""
    assert by_name["LLM-Model"]["description"].strip() != ""


def test_classify_request_fields_have_descriptions() -> None:
    props = _schema()["components"]["schemas"]["ClassifyRequest"]["properties"]
    assert props["product_name"]["description"].strip() != ""
    assert props["description"]["description"].strip() != ""


def test_classify_request_has_a_worked_example() -> None:
    classify_schema = _schema()["components"]["schemas"]["ClassifyRequest"]
    assert "examples" in classify_schema or "example" in classify_schema


def test_ncm_candidate_fields_have_descriptions() -> None:
    props = _schema()["components"]["schemas"]["NCMCandidate"]["properties"]
    assert props["ncm"]["description"].strip() != ""
    assert props["score"]["description"].strip() != ""


def test_classify_response_fields_have_descriptions() -> None:
    props = _schema()["components"]["schemas"]["ClassifyResponse"]["properties"]
    assert props["confidence_label"]["description"].strip() != ""
    assert props["escalation_reason"]["description"].strip() != ""
